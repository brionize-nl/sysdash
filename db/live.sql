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
