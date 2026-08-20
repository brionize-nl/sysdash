# SysDash

Zelf-gehost systeem-monitoring voor meerdere machines. Metrics via Supabase,
meldingen via n8n → Discord, live webdashboard (ook installeerbaar als PWA).

## Kenmerken
- Lichte metrics-agent (Python + psutil) die naar Supabase pusht
- Webdashboard met live-modus per machine
- 3-laags alerting (vitaal · trend · info) via n8n → Discord
- Zelf-herstel voor eigen diensten — vaste whitelist, geen losse commando's
- Installer-scripts voor de hub en extra machines

## Snel starten
Zie [`docs/SETUP.md`](docs/SETUP.md).

## Architectuur
Zie [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md).

## Licentie
MIT — zie [`LICENSE`](LICENSE).
