# SysDash installeren — stap voor stap

Je hoeft je computer niet opnieuw te installeren. Je gebruikt een bestaande Linux-machine als **hub**: daar draait het dashboard. Andere machines sturen hun metingen naar dezelfde database. Begin met Basis; Advanced kan later.

## 1. Wat je klaarzet

- Een Debian/Ubuntu-machine met Python 3.12 of nieuwer, systemd en een account met sudo. Andere Linux-distributies zijn nog niet getest.
- Tailscale op de hub en op het apparaat waarop je het dashboard opent. Log ze in op jouw tailnet. Advanced Linux-agents hebben ook Tailscale nodig.
- Een **apart Supabase-project voor SysDash**. Houd bestaande productiegegevens buiten de eerste testinstallatie.
- De SysDash-repository als volledige map, inclusief `common.py`, `db/` en `web/assets/`.

Tailscale en het Supabase-project zijn vereisten die je vooraf instelt; de installer doet geen accountaanmaak of stille wijzigingen aan je netwerkregels. Installeer Tailscale volgens [de officiële handleiding](https://tailscale.com/kb/1017/install).

## 2. De database klaarzetten

Open in Supabase de **SQL Editor** en voer achtereenvolgens uit:

1. De volledige inhoud van `db/install.sql`. Die maakt tabellen en de afgeschermde agent-API aan. De tabellen zijn standaard niet rechtstreeks leesbaar met de anon-key.
2. Activeer de Cron-integratie/pg_cron in Supabase en voer `db/retention.sql` uit. Die ruimt oude metingen dagelijks op (30 dagen) en oude actielogs na 90 dagen. Controleer dat beide jobs bestaan.

Gebruik dit uitsluitend voor een SysDash-project: de migratie verwijdert oudere policies van de genoemde SysDash-tabellen. Maak bij een bestaande installatie eerst een databaseback-up.

Zoek vervolgens de **project-URL**, **anon/publishable-key** en **service_role/secret-key** op. De service-key is een geheim dat alleen op de hub en eventueel de beheerde n8n-server hoort. Plak sleutels niet in een chat of Git-commit.

## 3. De hub installeren

Open een terminal in de repositorymap en voer uit:

```bash
sudo bash install/setup.sh --role hub --mode basis
```

De installer vraagt:

- De Supabase-project-URL en beide sleutels; geheimen worden tijdens invoer niet weergegeven.
- Een unieke machinenaam, zoals `bureau-pc`. Gebruik kleine letters, cijfers, `_` of `-`, geen spaties.
- Jouw **Tailscale-login**, bijvoorbeeld het e-mailadres waarmee je inlogt. Alleen opgegeven logins mogen het dashboard openen. Meerdere logins scheid je met een komma.

De code wordt root-owned in `/opt/sysdash` geplaatst. Instellingen staan in `/etc/sysdash/sysdash.env`, niet in de Git-checkout. De services draaien als een aparte `sysdash`-gebruiker. De installer toont pas “gecontroleerd” wanneer de eerste echte meting is verstuurd en de bedoelde services actief zijn.

Open het getoonde adres `http://<Tailscale-IP>:9000` op een apparaat met Tailscale. Gewone HTTP gaat hier door de versleutelde Tailscale-verbinding. Er is geen openbare Cloudflare-link.

## 4. Een extra Linux-machine toevoegen

Maak op de hub een privéconfiguratie aan, met een nieuwe unieke naam:

```bash
sudo /opt/sysdash/.venv/bin/python install/create-agent.py laptop /root/laptop.env
```

Dit commando draai je vanuit de repositorymap op de hub. Breng `laptop.env` via een privéverbinding naar de extra machine. Het bestand bevat een eigen token dat alleen voor `laptop` werkt; geen service-key.

Open op die extra machine een terminal in de volledige repository en voer uit:

```bash
sudo bash install/install-agent.sh --mode basis --config /pad/naar/laptop.env --noninteractive
```

De extra machine krijgt geen dashboardwebserver. Je blijft alle machines via de **hub** bekijken. Behandel de configuratie als een geheim en verwijder losse overdrachtskopieën nadat de installatie is gecontroleerd.

## 5. Een Windows-machine toevoegen

Maak op de hub op dezelfde manier een config aan, bijvoorbeeld `windows-pc.env`. Kopieer die privé naar Windows. Installeer Python met “Add to PATH” en behoud de volledige repositorymap.

Open PowerShell in `windows/`:

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -ConfigPath C:\privé\windows-pc.env
```

Het script controleert een meting en een echte push voordat het een taak bij inloggen registreert. Windows is alleen monitoren: geen Linux-beheeracties of ingebouwde temperatuur-/updatemetingen. Controleer na de eerste installatie en na opnieuw inloggen dat `SysDash-Agent` in Taakplanner actief is. De Windows-praktijktest op echte Windows-hardware is nog vereist.

## 6. Advanced en Discord

Start de installer opnieuw met de expliciete rol en modus:

```bash
sudo bash install/setup.sh --role hub --mode advanced
```

Bestaande instellingen blijven beschikbaar. De installer zet de bij de modus horende services opnieuw klaar en herstart ze met de nieuwe omgeving. Het dashboard kan vaste diensten herstarten, caches/logs opschonen en de machine rebooten. “Opschonen” verwijdert geen pakketten of kernels. Energieprofielen verschijnen alleen als `powerprofilesctl` beschikbaar is.

Voor Discord: zie de n8n-stappen in [SETUP.md](SETUP.md). Een Advanced-installatie zonder n8n geeft nog geen n8n-meldingen. Moduswisselen gebeurt bewust lokaal met de installer; het dashboard kan geen installatiescripts als root starten.

## 7. Automatische updates — alleen als je dat wilt

Schakel updates bewust in:

```bash
sudo bash install/setup.sh --role hub --mode advanced --enable-updates
```

De timer draait dagelijks om **18:50 Europe/Amsterdam**. De updater stopt als de blokkeerlijst niet betrouwbaar is opgehaald. Hij beheert uitsluitend eigen holds en bewaart bestaande externe holds. Geen automatische reboot en geen autoremove. Systeemwijzigingen kunnen nog steeds een herstart of handmatige aandacht nodig hebben.

Extra Linux-agents kunnen updates krijgen door hun installer met `--mode advanced --enable-updates` te draaien; dat vereist een eigen Discord-webhook als je ook updateberichten wilt.

## Als er iets misgaat

Een fout betekent **geen bevestigde installatie**. De installer kan al systeemonderdelen hebben geplaatst; herstel de genoemde oorzaak en voer dezelfde installer opnieuw uit. Er is geen beloofde automatische rollback van geïnstalleerde packages. Bewaar de eerdere instellingen/back-up tot de nieuwe installatie gecontroleerd is.

Controleer lokaal:

```bash
systemctl status sysdash-agent sysdash-live sysdash-web
journalctl -u sysdash-agent -n 50
sudo /opt/sysdash/.venv/bin/python install/setup.py --check --noninteractive --role hub --mode basis
```

Het laatste commando draai je vanuit de repositorymap en verandert niets; het controleert configuratie en Tailscale. Deel geen complete environmentbestanden of sleutels bij foutdiagnose.
