-- Dedicated Supabase project; private by default.
BEGIN;
-- ============================================================
--  SysDash v12 · Supabase schema  (bron van waarheid)
--  Draai dit ÉÉN keer in de Supabase SQL Editor.
--  Idempotent (veilig opnieuw te draaien). Read-only voor de web-app via RLS.
-- ============================================================

-- ---------- MACHINES (register) ----------
create table if not exists public.machines (
  machine      text primary key,                 -- korte naam, bv. 'laptop' of 'pro'
  label        text not null default '',          -- weergavenaam, bv. 'Laptop' of 'Bureau-pc'
  kind         text not null default 'desktop',   -- 'laptop' | 'desktop'
  tailscale_ip text,
  has_battery  boolean not null default false,
  thresholds   jsonb,                             -- per-machine overrides (null = defaults)
  hardware     jsonb,                             -- cpu/ram/schijf-model, verandert nooit tussen
                                                    -- twee reboots — bewust NIET in metrics (zou
                                                    -- elke 30s dubbel opgeslagen worden)
  first_seen   timestamptz not null default now(),
  last_seen    timestamptz
);

-- ---------- METRICS (tijdreeks) ----------
create table if not exists public.metrics (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null default now(),
  machine     text not null references public.machines(machine) on delete cascade,
  cpu         real, mem real, swap real, disk real,
  load1       real, load5 real, load15 real,
  temp        real, freq real,
  net_rx      real, net_tx real, net_up boolean,
  battery     real, bat_plugged boolean, bat_health real, bat_status text,
  updates     int,  uptime bigint,
  cores       jsonb, core_temps jsonb, temps jsonb, fans jsonb,
  disks       jsonb, top_procs jsonb, gpu jsonb, extra jsonb
);
create index if not exists metrics_machine_ts on public.metrics (machine, ts desc);
create index if not exists metrics_ts          on public.metrics (ts desc);

-- ---------- CONFIG (één rij, gedeeld door dashboard + n8n) ----------
create table if not exists public.config (
  id         int primary key default 1,
  thresholds jsonb not null default '{}'::jsonb,
  settings   jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  constraint config_single_row check (id = 1)
);

-- ---------- BASELINES (voor trends/anomalie, later gevuld) ----------
create table if not exists public.baselines (
  machine      text not null references public.machines(machine) on delete cascade,
  metric       text not null,
  hour_of_week smallint not null,
  mean real, stddev real, n int not null default 0,
  updated_at   timestamptz not null default now(),
  primary key (machine, metric, hour_of_week)
);

-- ---------- MACHINE_ACTIONS (energieprofiel-wens, door de action-runner toegepast) ----------
create table if not exists public.machine_actions (
  machine         text primary key references public.machines(machine) on delete cascade,
  power_profile   text,
  applied_profile text,
  updated_at      timestamptz not null default now()
);

-- ---------- ACTION_LOG (trede 2/3: opschoning/herstart vanaf het dashboard, met bevestiging) ----------
create table if not exists public.action_log (
  id        bigint generated always as identity primary key,
  machine   text not null references public.machines(machine) on delete cascade,
  action    text not null,                          -- bv. 'cleanup-safe', 'restart-render'
  status    text not null,                           -- 'ok' | 'fout'
  detail    text,
  ts        timestamptz not null default now()
);
create index if not exists action_log_machine_ts on public.action_log (machine, ts desc);

-- ---------- UPDATE_HOLDS ("overslaan"-vinkjes per pakket, gerespecteerd door de auto-update) ----------
create table if not exists public.update_holds (
  machine    text not null references public.machines(machine) on delete cascade,
  package    text not null,
  created_at timestamptz not null default now(),
  primary key (machine, package)
);

-- live_control: dode rest uit een losgelaten opzet om live-modus via Supabase te sturen (de
-- échte live-modus loopt via systemctl start/stop sysdash-live). Bevestigd ongebruikt (geen
-- code-referentie) tijdens de beveiligingsaudit — hier expliciet opgeruimd i.p.v. stil laten staan.
drop table if exists public.live_control cascade;

alter table public.machines add column if not exists hardware jsonb;
alter table public.machines add column if not exists thresholds jsonb;
alter table public.machines add column if not exists tailscale_ip text;
alter table public.machines add column if not exists last_seen timestamptz;
alter table public.metrics add column if not exists extra jsonb;
alter table public.metrics add column if not exists gpu jsonb;
alter table public.metrics add column if not exists core_temps jsonb;
alter table public.metrics add column if not exists top_procs jsonb;

-- ---------- View: laatste meting per machine ----------
create or replace view public.v_latest
  with (security_invoker = true) as
  select distinct on (machine) *
  from public.metrics
  order by machine, ts desc;

-- ============================================================
--  RLS: web-app (anon key) mag ALLEEN LEZEN. Agent schrijft met service-key.
-- ============================================================
alter table public.machines       enable row level security;
alter table public.metrics        enable row level security;
alter table public.config         enable row level security;
alter table public.baselines      enable row level security;
alter table public.machine_actions enable row level security;
alter table public.action_log     enable row level security;
alter table public.update_holds   enable row level security;

-- Dedicated SysDash tables: remove ALL old policies, including permissive legacy writes.
DO $$ DECLARE entry record; BEGIN
 FOR entry IN SELECT schemaname,tablename,policyname FROM pg_policies
 WHERE schemaname='public' AND tablename IN ('machines','metrics','config','baselines','machine_actions','action_log','update_holds','live')
 LOOP EXECUTE format('DROP POLICY %I ON %I.%I',entry.policyname,entry.schemaname,entry.tablename);END LOOP;
END $$;
revoke all on public.machines,public.metrics,public.config,public.baselines,public.machine_actions,public.action_log,public.update_holds from anon,authenticated;
revoke all on public.v_latest from anon,authenticated;
grant select on public.v_latest to service_role;

-- De agent schrijft met de service-key: volledige rechten (Supabase geeft die standaard al;
-- expliciet voor de zekerheid, ook bij hergebruik elders).
-- machine_actions/action_log/update_holds: BEWUST geen anon-schrijfpolicy — het dashboard schrijft
-- NIET meer rechtstreeks naar Supabase, maar via de Tailscale-only actions-gateway op elke machine
-- (die schrijft met de service-key). Zo kan de publieke, login-loze tunnel-link alleen nog
-- MEEKIJKEN, niet meer besturen — dat was tot deze fix niet zo (anon kon vrij schrijven naar
-- machine_actions/update_holds/live_control; die laatste tabel was dode ballast en is verwijderd).
grant all on public.machines, public.metrics, public.config, public.baselines to service_role;
grant all on public.machine_actions, public.action_log, public.update_holds to service_role;

-- ============================================================
--  Retentie: metrics groeit voor altijd (elke 30s, per machine) zonder opschoning.
--  30 dagen op volle resolutie is ruim genoeg om recente gebruikssessies te analyseren
--  (geen downsampling — accuraatheid blijft intact, alleen de horizon is begrensd).
-- ============================================================
-- Retention is installed separately: db/retention.sql requires pg_cron enabled in Supabase.
-- ============================================================
--  Geen machine-seed nodig: elke agent registreert zichzelf zelfstandig bij de
--  eerste meting (upsert op 'machines', zie agent.py/touch_machine()). Alleen
--  verstandige default-drempels hieronder.
-- ============================================================
insert into public.config (id, thresholds, settings) values (1,
  jsonb_build_object('default', jsonb_build_object(
      'disk_warn',80,'disk_alarm',90,'temp_alarm',90,'bat_min',15,
      'updates_many',20,'offline_min',10,'disk_forecast_days',14,
      'ram_alarm',85,'swap_alarm',50)),
  jsonb_build_object('report_cron','0 7-23/2 * * *','push_interval_sec',30,'timezone','Europe/Amsterdam')
) on conflict (id) do nothing;
create table if not exists public.live (
  machine text primary key references public.machines(machine) on delete cascade,
  ts timestamptz not null default now(),
  cpu real, mem real, temp real, freq real,
  cores jsonb, core_temps jsonb, top_procs jsonb,
  net_rx real, net_tx real
);
alter table public.live enable row level security;
revoke all on public.live from anon, authenticated;
grant all on public.live to service_role;
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

COMMIT;
