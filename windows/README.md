# SysDash · Windows-agent (lichte versie)

Kernmetingen (CPU, RAM, schijf, netwerk, accu, uptime) vanaf een Windows-pc, in hetzelfde
dashboard als de Linux-machines. Geen Tailscale nodig — de agent pusht rechtstreeks naar
Supabase over internet, net als de Linux-agent.

## Bewust NIET meegenomen (lichte versie)
- **Temperaturen** — Windows heeft geen ingebouwde, betrouwbare sensor-toegang zoals Linux.
  Zou een extra tool (LibreHardwareMonitor + WMI) vergen.
- **Updates-telling** — Windows Update werkt fundamenteel anders dan `apt`, apart uit te werken.
- **Actie-laag** (opschonen/herstarten/reboot vanaf het dashboard) — draait op `sudo`/`systemctl`,
  bestaat niet op Windows. Zou een eigen Windows-specifieke herbouw vergen.

Deze machine verschijnt dus wel op het dashboard met de basistegels (CPU/RAM/SCHIJF/NETWERK/
SYSTEEM), maar zonder CORE TEMP-tegel, updates-melding, of BEHEER-knoppen.

## Installeren
1. Zorg dat [Python](https://python.org/downloads) geïnstalleerd is, met "Add to PATH" aangevinkt.
2. Open PowerShell in deze map (`windows/`).
3. Draai:
   ```powershell
   powershell -ExecutionPolicy Bypass -File install-windows.ps1
   ```
4. Vul de gevraagde Supabase-gegevens in (zelfde project als de rest van SysDash — te vinden in
   het `.env`-bestand van de hub-machine, of in Supabase → Project Settings → API).

Het script installeert psutil, test een meting, en registreert een Taakplanner-taak
(`SysDash-Agent`) die bij inloggen start en zichzelf herstart bij een crash.

## Handmatig testen
```powershell
python agent_windows.py --dry-run   # meet + toont JSON, pusht niet
python agent_windows.py --once      # één echte push
```

## Taak beheren
Taakplanner (`taskschd.msc`) → **SysDash-Agent**. Uitzetten: `Disable-ScheduledTask -TaskName
SysDash-Agent`. Verwijderen: `Unregister-ScheduledTask -TaskName SysDash-Agent`.

## Nieuwe machine? Registreert zichzelf
De agent maakt bij de eerste push zelf een rij aan in de `machines`-tabel (upsert, met
auto-gedetecteerde `kind`/`has_battery`) — geen handmatige Supabase-stap nodig. `label` en
`tailscale_ip` (indien van toepassing) kun je daarna zelf nog aanpassen in Supabase.
