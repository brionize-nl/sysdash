-- ============================================================
--  SysDash v12 · Supabase schema  (bron van waarheid)
--  Draai dit ÉÉN keer in de Supabase SQL Editor.
--  Idempotent (veilig opnieuw te draaien). Read-only voor de web-app via RLS.
-- ============================================================

-- ---------- MACHINES (register) ----------
create table if not exists public.machines (
  machine      text primary key,                 -- korte naam: 'delli5', 'pro'
  label        text not null default '',          -- weergavenaam: 'Laptop', 'Asus'
  kind         text not null default 'desktop',   -- 'laptop' | 'desktop'
  tailscale_ip text,
  has_battery  boolean not null default false,
  thresholds   jsonb,                             -- per-machine overrides (null = defaults)
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

-- ---------- View: laatste meting per machine ----------
create or replace view public.v_latest
  with (security_invoker = true) as
  select distinct on (machine) *
  from public.metrics
  order by machine, ts desc;

-- ============================================================
--  RLS: web-app (anon key) mag ALLEEN LEZEN. Agent schrijft met service-key.
-- ============================================================
alter table public.machines  enable row level security;
alter table public.metrics   enable row level security;
alter table public.config    enable row level security;
alter table public.baselines enable row level security;

drop policy if exists read_machines  on public.machines;
drop policy if exists read_metrics   on public.metrics;
drop policy if exists read_config    on public.config;
drop policy if exists read_baselines on public.baselines;

create policy read_machines  on public.machines  for select to anon, authenticated using (true);
create policy read_metrics   on public.metrics   for select to anon, authenticated using (true);
create policy read_config    on public.config    for select to anon, authenticated using (true);
create policy read_baselines on public.baselines for select to anon, authenticated using (true);

grant select on public.machines, public.metrics, public.config, public.baselines to anon, authenticated;
grant select on public.v_latest to anon, authenticated;

-- De agent schrijft met de service-key: volledige rechten (Supabase geeft die standaard al;
-- expliciet voor de zekerheid, ook bij hergebruik elders).
grant all on public.machines, public.metrics, public.config, public.baselines to service_role;

-- ============================================================
--  Seed: de twee machines + verstandige default-drempels
-- ============================================================
insert into public.machines (machine, label, kind, tailscale_ip, has_battery) values
  ('delli5', 'Laptop', 'laptop',  '100.108.6.24', true),
  ('pro',    'Asus',   'desktop', '100.96.40.22', false)
on conflict (machine) do update
  set label = excluded.label, kind = excluded.kind,
      tailscale_ip = excluded.tailscale_ip, has_battery = excluded.has_battery;

insert into public.config (id, thresholds, settings) values (1,
  jsonb_build_object('default', jsonb_build_object(
      'disk_warn',80,'disk_alarm',90,'temp_alarm',90,'bat_min',15,
      'updates_many',20,'offline_min',10,'disk_forecast_days',14)),
  jsonb_build_object('report_cron','0 7-23/2 * * *','push_interval_sec',30,'timezone','Europe/Amsterdam')
) on conflict (id) do nothing;
