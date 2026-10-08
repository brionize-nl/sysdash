# Herstelcontrole SysDash

Herstelbranch na de audit van basiscommit `1aa37a8b1b63312c5849fdc5c4e1f9bfcf22765a`. Deze controle gaat over de code en geïsoleerde testopstellingen. Het is geen verklaring dat een bestaande productie-installatie al gemigreerd of getest is.

## Uitgevoerde controles

| Controle | Uitkomst en grens |
|---|---|
| Python 3.12: 17 tests | Geslaagd. Configuratie, sleutelformaten, tokentransport, identiteit, bindadres, paginering, updater-fouten/holds, dry-run, foutcodes, PNG-rendering en HTML-escaping. Drie tests gebruiken echte lokale HTTP-verzoeken; identiteit en databaseverkeer blijven testfixtures. |
| JavaScript/dashboard/workflows | Geslaagd. Oude livewaarden, hubnavigatie, tijdgaten, kleinere pagina-cap, mounts, machine-overrides, aanhoudende hitte, ontbrekende machine en heartbeatvoorwaarden. Workflow-Code draait met testdata; dit bewijst geen Discord-bezorging. |
| Echte Chromium-browser | Basis, Windows en Advanced geslaagd; alleen ondersteunde knoppen, oude livewaarde genegeerd, alle tabs op mobiel formaat, geen JavaScript-fouten. Netwerk gebruikt fixtures. |
| PostgreSQL 17 | Installatie op lege database, machinegebonden RPC, fout token, vervalste machinenaam, server-timestamps en verboden directe anon-reads/writes geslaagd. Een oudere permissieve policy is aangemaakt en verdwijnt bij herhaalde migratie. |
| n8n 2.37.10 | Alle vijf workflows succesvol geïmporteerd in een tijdelijke container. Supabase-nodeparameters gecontroleerd aan de geïnstalleerde connector. Workflows niet tegen echte accounts uitgevoerd. |
| Syntax en timers | Python-compilatie, JavaScript- en shellsyntax, diffcontrole en systemd-kalender met Europe/Amsterdam geslaagd. Dit is geen volledige systemd-installatietest. |

De CI-workflow herhaalt Python-, JavaScript-, browser- en databasetests bij pushes en pull requests. De lokale n8n-import is hierboven afzonderlijk vastgelegd.

## Verwerking auditbevindingen

| Audit-ID | Codewijziging |
|---|---|
| A01 | Root-owned code onder /opt, vaste root-helper, afgeschermde padketen en aparte servicegebruiker. Basis heeft geen sudoacties. |
| A02–A03 | Updater stopt bij onbetrouwbare blokkeerlijst, bewaart externe holds, controleert commandofouten en bevestigt pas voltooide runs. Updates standaard uit; gedeelde systeemacties hebben een root-only lockbestand. |
| A04–A05 | Gateway en dashboard controleren Tailscale-identiteit tegen expliciete operators. Bindadres moet het echte Tailscale-adres zijn; Origin en doelmachine worden gecontroleerd. |
| A06 | Oude policies van dedicated SysDash-tabellen worden verwijderd; agent-RPC met token per machine vervangt projectbrede agentrechten. |
| A07 | Heartbeat vereist inventaris, verse metingen, renderer en recent bevestigde rapportbezorging. Discord-uitval kan tot 12 uur onopgemerkt blijven; niet als directe bezorgingsbewaking gepresenteerd. |
| A08 | Windows-configvoorbeeld en overdracht van een eigen machineconfig; echte eerste push vóór registratie van de inlogtaak. |
| A09–A10 | Live timestamps en versheidscontrole; extra machines blijven op het hubdashboard. |
| A11–A14 | Eén begeleide installer voor hub/agent en Basis/Advanced; lokale moduswissels, gecontroleerde dependencies, veilige configuratieparser, services herstart en eerste push gecontroleerd. Installer weigert een wissel tijdens een actieve SysDash-update. Geen automatische package-rollback beloofd. |
| A15–A17 | Gepagineerde historie, inventaris als uitgangspunt, offlinekaarten, machine-overrides en mountalarms. Claims over niet-bestaande baselines verwijderd. Temperatuuralarm gebruikt aanhoudende workflowwaarnemingen; geen echte sensorduurmeting. |
| A18–A20 | Acties volgen OS/rol/capabilities; langere actie-timeout en gelijktijdige acties geweigerd. Historie ververst; weergavepauze tijdens bediening is zichtbaar en data blijft opgehaald. |
| A21–A24 | Frequentiedaling zonder temperatuurdiagnose; tijdgaten tellen niet als sessie. Dry-run schrijft niet, --once meldt pushfalen. HTML-escaping, privé tijdelijke renderbestanden en juiste hardwarebron. |
| A25–A26 | Privé hubproxy zonder browsersleutels; geen service-key op agents. UTC-timestamps, Amsterdam-timers, gedeelde environmentparser. Nieuwe Supabase-sleutels uitsluitend in apikey-header; legacy JWT ook als Bearer. |
| A27 | Werkelijke architectuur, installatie/migratiehandleiding, regressietests en CI toegevoegd. Oude netwerkgegevens kunnen nog in Git-historie staan; geschiedenis is niet herschreven. |

De nieuwe sleutelformaten volgen de [officiële Supabase-migratiehandleiding](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys). De geteste n8n-connector stuurt zijn credential nog als Bearer: gebruik daar een legacy service_role JWT of pas die connector aan, zoals beschreven in SETUP.md.

## Resterende acceptatie vóór productie

1. Installeer Basis op een schone ondersteunde Linux-VM met eigen test-Supabase en Tailscale. Controleer ontvangst, dashboardtoegang, bestandsrechten, sudoers en herstart van de VM.
2. Voeg een tweede Linux-machine en een Windows-machine toe. Controleer eerste push, unieke tokens en de Windows-inlogtaak na opnieuw inloggen.
3. Doorloop Basis → Advanced → Basis → Advanced. Controleer services, timers, beperkte sudoacties en knoppen. Test toegestaan/ander Tailscale-account én verkeerde Origin met echte Tailscale-identiteiten.
4. Test updater op een wegwerp-VM: externe hold, eigen hold toevoegen/verwijderen, API-uitval, apt-/Flatpak-fout en herstartvereiste. De huidige tests vervangen packagecommands; deze machine is niet geüpdatet.
5. Verbind n8n met een test-Discord-kanaal. Controleer alle workflowpaden, meerdere machines/berichten, juiste afbeeldingen en foutpaden. Test de gekozen Docker-netwerkopzet en heartbeatonderbrekingen.
6. Activeer en controleer pg_cron-retentie in het test-Supabase-project. Maak vóór migratie van bestaande data een back-up en verifieer behoud van relevante machines/historie.

Deze productieacceptatie vereist echte configuratie en hardware. Zonder die controles kan de branch worden beoordeeld, maar is “alles werkt op jouw machines” nog niet bevestigd.
