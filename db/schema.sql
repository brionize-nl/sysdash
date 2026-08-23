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

drop policy if exists read_machines  on public.machines;
drop policy if exists read_metrics   on public.metrics;
drop policy if exists read_config    on public.config;
drop policy if exists read_baselines on public.baselines;
drop policy if exists read_machine_actions on public.machine_actions;
drop policy if exists read_action_log      on public.action_log;
drop policy if exists read_update_holds    on public.update_holds;

create policy read_machines  on public.machines  for select to anon, authenticated using (true);
create policy read_metrics   on public.metrics   for select to anon, authenticated using (true);
create policy read_config    on public.config    for select to anon, authenticated using (true);
create policy read_baselines on public.baselines for select to anon, authenticated using (true);
create policy read_machine_actions on public.machine_actions for select to anon, authenticated using (true);
create policy read_action_log      on public.action_log      for select to anon, authenticated using (true);
create policy read_update_holds    on public.update_holds    for select to anon, authenticated using (true);

grant select on public.machines, public.metrics, public.config, public.baselines to anon, authenticated;
grant select on public.machine_actions, public.action_log, public.update_holds to anon, authenticated;
grant select on public.v_latest to anon, authenticated;

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
create extension if not exists pg_cron;
-- cron.schedule() werkt idempotent op jobnaam: een tweede run met dezelfde naam vervangt
-- het bestaande schema/commando i.p.v. een dubbele job aan te maken.
select cron.schedule(
  'metrics-retention-purge',
  '0 3 * * *',
  $$delete from public.metrics where ts < now() - interval '30 days'$$
);

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
