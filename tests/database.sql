-- psql -v ON_ERROR_STOP=1; synthetic credentials only.
insert into public.sysdash_agent_tokens(machine,token_hash) values
('fixture',encode(extensions.digest(repeat('a',40),'sha256'),'hex')),
('other',encode(extensions.digest(repeat('b',40),'sha256'),'hex'));
set role anon;
select public.sysdash_agent_api('fixture',repeat('a',40),'register','{"machine":"other","kind":"desktop","os":"linux","role":"agent","capabilities":{},"tailscale_ip":"100.64.0.2"}');
select public.sysdash_agent_api('other',repeat('b',40),'register','{"kind":"desktop","os":"windows"}');
select public.sysdash_agent_api('fixture',repeat('a',40),'metrics','{"machine":"other","cpu":12,"extra":{}}');
select public.sysdash_agent_api('fixture',repeat('a',40),'live','{"machine":"other","cpu":12,"ts":"2000-01-01T00:00:00Z"}');
select public.sysdash_agent_api('fixture',repeat('a',40),'hold-write','{"package":"example-package"}');
select public.sysdash_agent_api('fixture',repeat('a',40),'profile-write','{"power_profile":"balanced"}');
select public.sysdash_agent_api('fixture',repeat('a',40),'log','{"action":"test","status":"ok","detail":"fixture"}');
do $$begin
 begin perform public.sysdash_agent_api('other',repeat('a',40),'metrics','{}');raise exception 'cross-machine write was allowed';exception when insufficient_privilege then null;end;
 begin perform public.sysdash_agent_api('fixture','wrong','metrics','{}');raise exception 'invalid token allowed';exception when insufficient_privilege then null;end;
 begin perform public.sysdash_agent_api('fixture',repeat('a',40),'arbitrary','{}');raise exception 'arbitrary operation allowed';exception when raise_exception then if SQLERRM <> 'unsupported action' then raise;end if;end;
 begin perform * from public.metrics;raise exception 'anon raw read allowed';exception when insufficient_privilege then null;end;
 begin insert into public.metrics(machine,cpu)values('fixture',100);raise exception 'anon direct write allowed';exception when insufficient_privilege then null;end;
end$$;
reset role;
do $$begin
 if (select count(*) from public.metrics where machine='fixture')<>1 then raise exception 'missing metric';end if;
 if exists(select 1 from public.metrics where machine='other') then raise exception 'forged machine';end if;
 if exists(select 1 from public.live where ts<now()-interval '1 minute') then raise exception 'stale live timestamp';end if;
end$$;
-- Legacy policy must disappear when installation is repeated.
create policy legacy_open_write on public.machine_actions for all to anon using(true) with check(true);
