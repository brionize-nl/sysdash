create extension if not exists pg_cron;
select cron.schedule('metrics-retention-purge','0 3 * * *',$$delete from public.metrics where ts < now() - interval '30 days'$$);
select cron.schedule('action-log-retention','15 3 * * *',$$delete from public.action_log where ts < now() - interval '90 days'$$);
