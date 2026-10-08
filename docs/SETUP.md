# Technische installatie en migratie

## Ondersteunde opzet

Debian/Ubuntu + systemd, Python 3.12+, Tailscale en een dedicated Supabase-project. Code staat root-owned in `/opt/sysdash`, configuratie root-owned met groep `sysdash` in `/etc/sysdash/sysdash.env`. Services gebruiken de virtualenv in `/opt/sysdash/.venv`. Privileged helpers en hun padketen zijn niet beschrijfbaar door de servicegebruiker.

## Bestaande installatie migreren

1. Maak een back-up van de database, lokale configuratie en de bestaande systemd/sudoers-bestanden. Gebruik eerst een testmachine en testproject.
2. Voer `db/install.sql` uit in het dedicated SysDash-project en controleer de retentiejobs uit `db/retention.sql`.
3. Start de nieuwe hub-installer vanuit de volledige nieuwe repositorymap. Gebruik desgewenst `--config /pad/naar/oude.env`; geef operators op en kies de gewenste rol/modus expliciet.
4. De installer vervangt het oude `/etc/sudoers.d/sysdash` door rechten voor uitsluitend de nieuwe servicegebruiker en vaste root-owned helper. Oude SysDash-services, tunnel en timers worden eerst uitgeschakeld; alleen de gekozen nieuwe onderdelen worden weer gestart.
5. Maak nieuwe individuele machineconfigs aan op de hub. Installeer alle extra agents opnieuw. Oude agents met service-keys kunnen de nieuwe RPC niet automatisch gebruiken; verwijder hun oude keys en overweeg rotatie van de oude gedeelde service-key na volledige migratie.
6. Importeer de nieuwe workflows. Selecteer bij **iedere** Supabase-node de juiste credential; oude open policies mogen niet blijven bestaan. Voer het rapport handmatig uit en verifieer Discord voordat je heartbeat activeert.
7. Controleer alle machines en de gekozen modus. Bewaar de back-up tot installatie- en gedragstests voltooid zijn.

Databaseprivacy is gewijzigd: het oude directe publieke anon-dashboard werkt niet met de nieuwe private policies. Er is in deze versie geen publieke-leesmodus. Dat is een expliciete veiligheidskeuze, geen transparante migratie zonder gedragseffect.

## n8n en Discord

Importeer `n8n/report.json`, `alerts.json`, `battery.json`, `updates.json` en `heartbeat.json` in n8n. De workflows zijn gedeactiveerd bij import. Kies de Supabase-servicecredential in alle Supabase-nodes, inclusief de inventaris- en bezorgingsnodes. Gebruik daarin voor de geteste n8n 2.37.10 een **legacy service_role JWT**: deze connector zet de credential ook in een Bearer-header. De nieuwe `sb_secret_`-key wordt door SysDash zelf ondersteund, maar vereist een aangepaste n8n-credential/connector die uitsluitend `apikey` gebruikt.

- Stel `DISCORD_WEBHOOK` en `HEALTHCHECK_PING_URL` veilig in voor het n8n-proces.
- Bij een lokale systemd-installatie kan `EnvironmentFile=/etc/sysdash/sysdash.env` de omgeving leveren. De systemd-manager leest dit bestand; geef de n8n-gebruiker niet onnodig leesrechten op alle configuratiebestanden.
- Stel `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` in waar n8n anders `$env`-toegang blokkeert. Beperk toegang tot de n8n-editor tot beheerders.
- Renderer draait op `127.0.0.1:7071`. Bij npm/systemd op de hub klopt dat direct.
- Bij Docker gebruik je op Linux een bewust gekozen **host network** voor n8n, of bouw je een afzonderlijk gecontroleerde renderverbinding. In een gewone bridge-container is `127.0.0.1` de container zelf en werkt de huidige workflow-URL niet. Zet de renderer niet zomaar publiek open.

Test ieder workflowpad: alarm, herstel, meerdere machines, meerdere gelijktijdige meldingen, renderfout en Discord-fout. Een geslaagde import bewijst geen bezorging.

## Heartbeat

De heartbeat controleert de inventaris, verse metingen, een werkende renderer en een in de database vastgelegde succesvolle Discord-rapportbezorging van maximaal 12 uur geleden. Daarna pas pingt hij de externe bewaker. Voer het eerste rapport handmatig uit; zonder eerste succesvolle bezorging blijft heartbeat bewust ongezond.

Maak extern een check met Period 10 minuten en Grace 10 minuten. Test onderbreking van Supabase, renderer, metingen en langdurige Discord-uitval. De bezorgingscontrole detecteert Discord-uitval pas wanneer het laatst bevestigde rapport ouder is dan 12 uur; dit is geen onmiddellijke bewaking van Discord. Een laptop die bewust offline is telt in de huidige inventaris ook als niet gezond; verwijder/retireer machines die niet meer bewaakt hoeven te worden.

## Modus en updates

Moduswijzigingen zijn lokale administratorhandelingen. Gebruik telkens expliciete `--role` en `--mode`. Updates staan uit tenzij `--enable-updates` is opgegeven. Basis bevat geen sudoacties, ook niet via een dashboardknop. Advanced geeft de servicegebruiker uitsluitend toegang tot `/usr/local/libexec/sysdash-action`, dat argumenten controleert en alleen vaste acties uitvoert.

Gedeelde n8n-workflows worden door een moduswissel niet verwijderd of uitgezet: beheer hun publicatiestatus in n8n. De nieuwe installer activeert geen oude tunnel-/bootnotificaties. Stop oude losse n8n-configuraties zelf wanneer je meldingen wilt beëindigen.

## Testen

```bash
python3 -m venv work/test-venv
work/test-venv/bin/pip install -r requirements.txt
work/test-venv/bin/python -m unittest discover -s tests -v
node tests/dashboard.cjs
work/test-venv/bin/python -m playwright install chromium
work/test-venv/bin/python tests/browser.py
```

Database-tests draaien in CI met een lege PostgreSQL-instance. De tests controleren onder andere tokenbinding, geweigerde directe anon-reads/writes en het verwijderen van een oude permissieve policy bij een herhaalde migratie. Gebruik `tests/database.sql` uitsluitend op testdata.

De installer is nog niet end-to-end uitgevoerd op een schone echte Linux-VM, en de PowerShell-installer nog niet op echte Windows. Zie VALIDATION.md. Voer die praktijktests uit voordat je deze branch over productie uitrolt.
