-- Run after schema.sql/live.sql. Dedicated SysDash project only.
create extension if not exists pgcrypto with schema extensions;
DO $$ BEGIN IF EXISTS (select 1 from pg_extension e join pg_namespace n on n.oid=e.extnamespace where e.extname='pgcrypto' and n.nspname<>'extensions') THEN ALTER EXTENSION pgcrypto SET SCHEMA extensions; END IF; END $$;
alter table public.machines add column if not exists os text;
alter table public.machines add column if not exists role text;
alter table public.machines add column if not exists capabilities jsonb not null default '{}';
create table if not exists public.sysdash_agent_tokens (
 machine text primary key, token_hash text not null, enabled boolean not null default true
);
alter table public.sysdash_agent_tokens enable row level security;
revoke all on public.sysdash_agent_tokens from anon, authenticated;
grant all on public.sysdash_agent_tokens to service_role;

create or replace function public.sysdash_agent_api(p_machine text, p_token text, p_action text, p_body jsonb default '{}') returns jsonb
language plpgsql security definer set search_path = public, extensions, pg_temp as $$
declare m public.metrics; l public.live; result jsonb; pkg text;
begin
 if p_machine !~ '^[a-z0-9][a-z0-9_-]{0,63}$' or length(p_token)<32 or not exists (
   select 1 from public.sysdash_agent_tokens where machine=p_machine and enabled and token_hash=encode(extensions.digest(p_token,'sha256'),'hex')
 ) then raise exception 'invalid agent credentials' using errcode='42501'; end if;
 if jsonb_typeof(p_body)<>'object' then raise exception 'expected object'; end if;
 if p_action='register' then
  insert into public.machines(machine,last_seen,has_battery,kind,os,role,capabilities,tailscale_ip)
  values(p_machine,now(),coalesce((p_body->>'has_battery')::boolean,false),p_body->>'kind',p_body->>'os',p_body->>'role',coalesce(p_body->'capabilities','{}'),p_body->>'tailscale_ip')
  on conflict(machine) do update set last_seen=now(),has_battery=excluded.has_battery,kind=excluded.kind,os=excluded.os,role=excluded.role,capabilities=excluded.capabilities,tailscale_ip=excluded.tailscale_ip;
 elsif p_action='hardware' then
  update public.machines set hardware=p_body->'hardware' where machine=p_machine;
 elsif p_action='metrics' then
  m:=jsonb_populate_record(null::public.metrics,p_body);
  insert into public.metrics(machine,ts,cpu,mem,swap,disk,load1,load5,load15,temp,freq,net_rx,net_tx,net_up,battery,bat_plugged,bat_health,bat_status,updates,uptime,cores,core_temps,temps,fans,disks,top_procs,gpu,extra)
  values(p_machine,now(),m.cpu,m.mem,m.swap,m.disk,m.load1,m.load5,m.load15,m.temp,m.freq,m.net_rx,m.net_tx,m.net_up,m.battery,m.bat_plugged,m.bat_health,m.bat_status,m.updates,m.uptime,m.cores,m.core_temps,m.temps,m.fans,m.disks,m.top_procs,m.gpu,m.extra);
  update public.machines set last_seen=now() where machine=p_machine;
 elsif p_action='live' then
  l:=jsonb_populate_record(null::public.live,p_body);
  insert into public.live(machine,ts,cpu,mem,temp,freq,cores,core_temps,top_procs,net_rx,net_tx)
  values(p_machine,now(),l.cpu,l.mem,l.temp,l.freq,l.cores,l.core_temps,l.top_procs,l.net_rx,l.net_tx)
  on conflict(machine) do update set ts=now(),cpu=excluded.cpu,mem=excluded.mem,temp=excluded.temp,freq=excluded.freq,cores=excluded.cores,core_temps=excluded.core_temps,top_procs=excluded.top_procs,net_rx=excluded.net_rx,net_tx=excluded.net_tx;
 elsif p_action='history' then
  select coalesce(jsonb_agg(to_jsonb(t)),'[]') into result from (select disk,ts from public.metrics where machine=p_machine and ts<=coalesce(nullif(p_body->>'before','')::timestamptz,now()) order by ts desc limit 1)t;
  return result;
 elsif p_action='profile-read' then
  select coalesce(jsonb_agg(to_jsonb(t)),'[]') into result from public.machine_actions t where machine=p_machine;return result;
 elsif p_action='profile-write' then
  if p_body ? 'power_profile' and p_body->>'power_profile' not in ('power-saver','balanced','performance') then raise exception 'invalid profile';end if;
  insert into public.machine_actions(machine,power_profile,applied_profile) values(p_machine,p_body->>'power_profile',p_body->>'applied_profile')
  on conflict(machine) do update set power_profile=coalesce(excluded.power_profile,machine_actions.power_profile), applied_profile=coalesce(excluded.applied_profile,machine_actions.applied_profile),updated_at=now();
 elsif p_action='holds-read' then
  select coalesce(jsonb_agg(to_jsonb(t)),'[]') into result from public.update_holds t where machine=p_machine; return result;
 elsif p_action in ('hold-write','hold-delete') then
  pkg:=p_body->>'package';if pkg is null or pkg !~ '^(flatpak:)?[A-Za-z0-9][A-Za-z0-9.+:_-]{0,199}$' then raise exception 'invalid package';end if;
  if p_action='hold-write' then insert into public.update_holds(machine,package) values(p_machine,pkg) on conflict do nothing;
  else delete from public.update_holds where machine=p_machine and package=pkg;end if;
 elsif p_action='log' then
  insert into public.action_log(machine,action,status,detail) values(p_machine,left(p_body->>'action',100),left(p_body->>'status',20),left(p_body->>'detail',500));
 else raise exception 'unsupported action';
 end if;
 return '[]'::jsonb;
end $$;
revoke all on function public.sysdash_agent_api(text,text,text,jsonb) from public;
grant execute on function public.sysdash_agent_api(text,text,text,jsonb) to anon,authenticated,service_role;

create table if not exists public.sysdash_monitor_state(id int primary key check(id=1),last_delivery timestamptz);
alter table public.sysdash_monitor_state enable row level security;
revoke all on public.sysdash_monitor_state from anon,authenticated;
grant all on public.sysdash_monitor_state to service_role;
insert into public.sysdash_monitor_state(id)values(1)on conflict do nothing;
