# SysDash

Zelf-gehost, kleurenblind-vriendelijk systeem-monitoringsysteem voor één of meer machines.
Agents pushen metrics naar Supabase; een web-dashboard en (optioneel) Discord-meldingen lezen
daaruit. Twee installatieniveaus: **Basis** (alleen kijken) of **Advanced** (kijken + zelf
diensten herstarten/opschonen/rebooten vanaf het dashboard + Discord-meldingen).

- **Meerdere machines** · **werkt overal** (Supabase als bron) · **kant-en-klare installer**
- Modulair, één geheel. Zie [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) voor de architectuur.

## Snel starten

Nog nooit Supabase/Discord/n8n gebruikt? Begin bij [`docs/AAN_DE_SLAG.md`](docs/AAN_DE_SLAG.md) —
stap voor stap, inclusief hoe je de benodigde accounts aanmaakt.

Al bekend met die onderdelen? Kort:
1. Vul `.env` in (kopie van `.env.example`) en draai `db/schema.sql` + `db/live.sql` één keer in
   de Supabase SQL Editor.
2. `./install/setup.sh` op je hoofdmachine (kiest Basis of Advanced) · `./install/install-agent.sh`
   op elke extra machine.
3. Zie [`docs/SETUP.md`](docs/SETUP.md) voor de volledige technische details.

Geen secrets in deze repo — jouw ingevulde versie (met `.env` en machinenamen) hoort in een eigen
**private** repo.

## Licentie
MIT — zie [`LICENSE`](LICENSE).
