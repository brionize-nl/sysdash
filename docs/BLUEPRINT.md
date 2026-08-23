# SysDash v12 — Blauwdruk (v1.2)

*From-scratch, schoon, modulair-maar-samenhangend. Deze publieke template volgt de architectuur
van de private werkversie; jouw eigen voortgangslogboek hoort in je eigen (private) repo.*

---

## 1. Doel

Eén net monitoring-systeem, gebouwd zodat alles strak en voorspelbaar is:

- **Meerdere machines, verschillende diepgang**: één hub-machine (Linux) + optioneel extra Linux-
  machines met de volledige agent (temps, updates, actie-laag). Windows-machines krijgen een lichte
  agent (alleen kernmetingen, bewust geen temps/updates/actie-laag, zie §3). Een telefoon is kijker.
- **Werkt overal**: Supabase is de bron — webpagina en meldingen lezen daaruit, ook buiten Tailscale.
- **Zelf-registrerend**: een nieuwe machine hoeft geen handmatige Supabase-rij meer — de agent
  maakt 'm zelf aan bij de eerste push (zie §3, §6).
- **Kant-en-klaar**: één download + een installer die je door de laatste stappen loodst.
- **Twee sporen**: publieke kale template + jouw private ingevulde versie.
- **Modulair, maar één geheel**: elk onderdeel is een module (map), samen één pakket.

---

## 2. Wat er anders is dan de oude opzet (= minder gedoe)

| Oud probleem | Nu opgelost door |
|---|---|
| "Waar staat welk script?" | Vaste mappenstructuur |
| Secret op meerdere plekken | Eén `.env` per machine, `EnvironmentFile=`, nooit `Environment=` met geheimen |
| Handmatig hardware checken | De installer **probet** zichzelf automatisch |
| Botsen met oude troep | Schone opzet, oude losse installaties opgeruimd |
| Machine viel weg (wifi-powersave) | Installer maakt elke machine "monitoring-klaar" |
| Nieuwe machine = handmatige Supabase-rij | Agent registreert zichzelf (upsert, zie §3) |
| Dashboard schreef direct naar Supabase (anon-key, publiek lek) | actions-gateway: Tailscale-only, service-key, whitelist (zie §9) |

**Eerlijk:** de allereerste run legt altijd íets bloot — dat is opstarten, geen audit.

---

## 3. Architectuur (het geheel, in modules)

```
   HUB-machine (Linux)  extra machine (Linux) extra machine (Windows)  machines met een AGENT
        │  push metrics      │  push metrics      │  push metrics  (psutil, auto-detect)
        └──────────┬─────────┴──────────┬─────────┘
                    ▼                    │  eerste push: registreert zichzelf
              SUPABASE  ← bron van waarheid (metrics·machines·config·action_log·update_holds)
              read│                     │write (service-key, whitelist-only)
                  ▼                     │
      WEB dashboard ──BEHEER-acties──► actions-gateway (per machine, Tailscale-IP-only, poort 7072)
      (kijken + sturen,                      │
       telefoon/PWA)                          ▼
                                     systemd (herstart dienst/PC, opschoning) + Supabase-write
                  │
                  ▼
              n8n workflows ── spec ──► RENDER (HUD-kaart, cairosvg) ──► Discord
              (meldingen, 3 lagen, 1 webhook-variabele)
```

**Kennis-van-nu:**
- De agent **pusht** zelf naar Supabase én **registreert zichzelf** (upsert op `machines`, met
  auto-gedetecteerde `kind`/`has_battery`) — machine erbij = agent draaien, klaar. Geen handmatige
  Supabase-rij meer nodig (een vroegere opzet gaf zo een stil-falend gat bij een nieuwe machine).
- Het dashboard schrijft **niet meer rechtstreeks** naar Supabase voor BEHEER-acties — dat ging tot
  gebeurde met de publiek meegestuurde anon-key, een echt beveiligingslek. Nu via `actions-gateway.py`:
  bindt alleen op het eigen Tailscale-IP, whitelist-only, schrijft met de service-key.
- **Lichte agent-variant** (`windows/agent_windows.py`) voor niet-Linux-machines: alleen cpu/mem/
  swap/disk/net/uptime/accu — bewust geen temps (geen ingebouwde sensor-toegang op Windows), geen
  updates-telling (fundamenteel ander model dan apt), geen actie-laag (geen Tailscale-gateway nodig
  voor een kijk-alleen-machine).

---

## 4. Mappenstructuur (één pakket)

```
sysdash/
├─ README.md
├─ .env.example              # sjabloon voor secrets (LEEG)
├─ .gitignore                # beschermt .env → nooit online
├─ CLAUDE.md                 # projectgeheugen (publiek: geen gevoelige info)
├─ install/
│   ├─ setup.sh              # HUB-installer (draait op je hoofdmachine: alles)
│   ├─ install-agent.sh      # extra-machine-installer (agent + actie-laag)
│   ├─ prepare-machine.sh    # maakt machine 'monitoring-klaar' (powersave/suspend/autoconnect)
│   └─ probe.py              # losse, read-only recon-tool (handmatig, niet meer door setup.sh aangeroepen)
├─ agent/        agent.py · sysdash-agent.service · sysdash-live.service
├─ render/       render.py · sysdash-render.service        (HUD-kaart, cairosvg, geen chromium)
├─ web/          index.html · app.js · style.css · manifest.webmanifest · assets/
├─ n8n/          alerts.json (incl. connectiviteit) · updates.json · battery.json · report.json
├─ actions/      action-runner.py (trede 1 zelf-herstel) · actions-gateway.py (trede 2-4, Tailscale-
│                only) · sudoers.example · audit.log (lokaal)
├─ overview/     sysdash-overview.py · overview-template.py · .service · .timer  (2×-daags HUD-overzicht)
├─ tunnel/       sysdash-tunnel.sh · .service            (trycloudflare quick tunnel)
├─ boot-notify/  sysdash-boot-notify.sh · .service        (melding bij opstarten)
├─ updater/      sysdash-update.sh · .service · .timer    (dagelijkse apt-update, hold-respect)
├─ windows/      agent_windows.py · install-windows.ps1 · .env.example · README.md  (lichte agent)
├─ db/           schema.sql   (tabellen + RLS) · live.sql (live-modus-tabel, overschrijvende rij per machine)
└─ docs/         SETUP.md · BLUEPRINT.md · PROGRESS.md
```

---

## 5. Twee sporen: publieke template + jouw eigen private versie

- **Deze repo** (public) — kale template, `.env.example`, **nul secrets**.
- **Jouw eigen fork/kopie** (private aanbevolen) — `.env` ingevuld, jouw machines/drempels. Dit is
  de repo waar je dagelijks in werkt/pusht.
- `.env` op `.gitignore` → secrets komen **nooit** in een repo, in geen van beide.

---

## 6. Installer-flow

**Hub-machine:** `./install/setup.sh` — installeert alles: agent, render, web, actie-laag
(action-runner + actions-gateway), tunnel, boot-notify, updater, overview. Idempotent, zet `.env`
op `600`.

**Extra machine (Linux, volledige diepgang):** `./install/install-agent.sh` — agent +
prepare-machine + actie-laag (action-runner + actions-gateway + sudoers). Geen render/web/tunnel
(die draaien alleen op de hub).

**Extra machine, lichte variant (Windows):** `windows/install-windows.ps1` —
Taakplanner in plaats van systemd, alleen `agent_windows.py`. Geen actie-laag.

Bij élke variant: de agent registreert bij de eerste push zichzelf in `machines` (zie §3) — geen
losse Supabase-stap meer nodig.

---

## 6a. Basis vs. Advanced (installatiemodus, hub-only)

Niet iedereen die SysDash uitprobeert wil meteen n8n installeren en een Discord-webhook aanmaken.
De hub-installer (`setup.sh`) biedt daarom twee niveaus:

- **Basis — alleen kijken.** Agent + live-heartbeat + dashboard + tunnel + een **minimale**
  actions-gateway (whitelist van precies één actie: upgraden). Geen sudoers voor herstart/opschonen/
  reboot, geen Discord/n8n, geen render/overview/boot-notify/updater (die zijn stuk voor stuk
  Discord-afhankelijk en dus zinloos zonder Advanced).
- **Advanced — kijken + sturen + meldingen.** Alles: de volledige actie-laag (§9) + n8n/Discord.

**Upgraden/downgraden gaat via een knop op het dashboard** (BEHEER-tab), niet via een losse
installer-aanroep vanaf de knop — bewust, om het whitelist-only-principe (§9) niet te doorbreken:
- `actions/actions-gateway.py` is **mode-aware**: leest `INSTALL_MODE` uit `.env` (ontbreekt dat
  veld — zoals bij elke installatie van vóór dit onderscheid — dan is de aanname `advanced`, zodat
  bestaande rechten nooit stilzwijgend verdwijnen) en bouwt daarop zijn whitelist. Basis kent alleen
  `/upgrade-to-advanced`; Advanced kent alle bestaande acties plus `/downgrade-to-basis`.
- De daadwerkelijke systemd/sudoers-wijzigingen lopen via twee **losse, vaste** root-scripts
  (`install/upgrade-to-advanced.sh`, `install/downgrade-to-basis.sh`) — whitelisted in de sudoers
  als één exact commando, precies zoals elke andere trede-actie. Deze scripts raken `.env` bewust
  nooit aan (root zou eigenaar/rechten van dat 600-bestand kunnen omzetten); de gateway zelf (draait
  als gewone gebruiker) schrijft ervóór/erna naar `.env`.
- Dependencies (cairosvg/playwright/font) staan sinds de eerste installatie altijd al klaar,
  ongeacht modus — de upgrade-routine hoeft dus alleen systemd-units + sudoers te regelen.

---

## 7. Automatisch vs. jij invult

- **Automatisch:** hardware-probe, machine-klaar-maken, mappen, services, checks, zelf-registratie
  in `machines`, verificatie.
- **Jij vult in (kan ik nooit zien):** Supabase URL + sleutels, Discord-webhook. Via `.env`.
- **Jij beslist eenmalig, per machine:** `label` en `tailscale_ip` in de `machines`-tabel (blijven
  bewust buiten de auto-registratie — cosmetisch/netwerk-specifiek, geen agent-taak).

---

## 8. Alert-filosofie — 3 lagen (i.p.v. platte drempels)

Niet "elk getal boven een drempel", maar zinnige lagen. **Drempels per machine instelbaar
(config-tabel), met verstandige defaults.**

**Laag 1 — Vitaal (hard alarm):**
- Machine offline (schrijft > 10 min niet) — per machine
- Schijf (bijna) vol — waarschuwing 80%, alarm 90%, per mount
- Accu kritiek — op accu én < 15%
- Temp echt te heet — > 90°C aanhoudend, met **veroorzaker** (zwaarste proces uit `top_procs`)
- Connectiviteit weg — machine heeft geen internet meer

**Laag 2 — Trend (vroeg signaal):**
- Schijf vol over ~X dagen (`disk_days_left`, lineaire trend t.o.v. 7 dagen terug, seintje < 14 dagen)
- Accu-slijtage (conditie < 30%) — dormant zolang geen enkele accu daaronder zit
- RAM+swap-thrashing (RAM ≥85% ÉN swap ≥50% tegelijk), met **echte** veroorzaker (`top_procs_mem`,
  niet de CPU-lijst — een RAM-vreter met weinig CPU moet ook zichtbaar zijn)
- Herstart nodig (`reboot_required`, eenmalig, lost zichzelf op na de herstart)
- Beveiligingsupdates apart geteld (rode updates wegen zwaarder dan een kaal aantal)

**Laag 3 — Info (rustig, geen alarm):**
- Updates (bij verandering)
- Periodiek rapport (HUD-kaart, elke 2u tussen 07-23) + 2×-daags 12u-overzicht (08:00/20:00)

**Geschrapt:** losse CPU/RAM-piek-alerts → ruis. Structureel hoog vangt de baseline (laag 2).

---

## 8a. Dead-man's-switch — bewaakt de bewaker

Alle bovenstaande lagen melden een probleem via dezelfde keten (agent → Supabase → n8n → Discord).
Valt die keten zelf om (n8n crasht, Supabase onbereikbaar, de hub-machine zelf plat), dan is er **niemand**
om dat te melden — stilte ziet er identiek uit als "niets aan de hand". Dat gat dicht een losse,
externe dienst:

- **n8n-workflow `n8n/heartbeat.json`** ("SysDash Heartbeat"): elke 5 min een kale GET naar
  `HEALTHCHECK_PING_URL` (uit `.env`). Leeg = de workflow doet niets (geen foutmeldingen) — zo kan
  een verse installatie zonder heartbeat-account gewoon draaien.
- **healthchecks.io** (gratis, open source, **bewust extern** — moet buiten het eigen
  netwerk/stroom/infra draaien, anders valt de wachter tegelijk met wat 'ie bewaakt): jij stelt in
  hoe vaak een ping verwacht wordt (Period) + hoeveel speling (Grace). Blijft die uit, dan sturen
  **zij** jou een melding — stilte wordt zo zelf het alarm, i.p.v. onzichtbaar te blijven.
- Bewust **niet** op een eigen ander apparaat (telefoon/laptop) gebouwd: die delen hetzelfde
  huisnetwerk/dezelfde stroom als de hub-machine én draaien niet gegarandeerd 24/7 — lost het gat
  dus niet echt op.
- Live bewezen in de private werkversie: ping stilgelegd (`HEALTHCHECK_PING_URL` tijdelijk leeg,
  korte Period/Grace) → healthchecks.io stuurde daadwerkelijk een "down"-mail. Ping hersteld →
  weer stil, zoals het hoort.

---

## 9. Actie-laag — op afstand veilig dingen dóen (gefaseerd, ✅ alle tredes gebouwd)

Via de **actions-gateway** (Tailscale-only, service-key, whitelist), niet meer rechtstreeks naar
Supabase vanuit de browser:

- **Trede 1 — Zelf-herstel** (`action-runner.py`, lokale daemon): dienst valt om → automatisch
  herstart. Detecteert per machine welke diensten daadwerkelijk geïnstalleerd zijn (`systemd_active()`),
  probeert nooit blind een dienst te herstellen die op die machine niet bestaat.
- **Trede 2 — Veilige opschoning** (`/cleanup`, bevestiging): `apt autoremove`/`clean` +
  `journalctl --vacuum`.
- **Trede 3 — Dienst herstarten vanaf telefoon** (`/restart`, bevestiging): vaste lijst benoemde
  diensten.
- **Trede 4 — Hele machine herstarten** (`/reboot`, dubbele bevestiging: overtypen in de UI +
  server-side check): `sudo systemctl reboot`. Bewust geen poweroff.

**Nog bewust geparkeerd (aparte beslissing, niet gebouwd):** een "nu updaten"-knop (`apt upgrade`
op aanvraag) — de dagelijkse auto-update (`sysdash-update.timer`) doet dit al ongevraagd 's nachts;
een handmatige trigger is de krachtigste losse actie en is bewust niet automatisch meegenomen.

**Veiligheidsruggengraat (niet-onderhandelbaar):**
- **Whitelist** — alleen vaste, benoemde acties. Nóóit "voer dit commando uit".
- Minimale rechten (smalle sudoers), **bevestiging** bij ingrijpen, **alleen Tailscale**, **logboek**
  (lokaal `audit.log` + Supabase `action_log`, zichtbaar in het dashboard).
- **Expliciet NIET:** automatisch door inlog-/verbind-/captive-portal-schermen klikken. Dat bouwen
  we niet.

---

## 10. Sessie-continuïteit — voortgangs-logboek

`docs/PROGRESS.md`: wat af is · volgend blok · beslissingen. Onderbreking = plak PROGRESS.md, we
gaan naadloos verder. Alles staat tóch als bestand bij jou + op GitHub (privé-repo).

---

## 11. Bouwvolgorde (fases — ✅ alle 7 afgerond opgeleverd)

1. DB-schema + RLS (fundering)
2. Agent (push) + probe + prepare-machine
3. Render-service (HUD-kaart)
4. n8n-meldingen (3 lagen, schoon)
5. Web dashboard (v4-ontwerp, interactief)
6. Actie-laag (trede 1-4, zie §9)
7. Installer + docs + repo-structuur

Elke fase is inmiddels live en bewezen (zie `PROGRESS.md`). Nieuw werk gaat nu via losse,
gerichte verbeteringen — niet meer via deze opbouwvolgorde.

---

## 12. Roadmap

Alle 7 bouwfases (zie §11) zijn af en bewezen in de private werkversie waarop deze template is
gebaseerd. Ideeën voor een volgende stap staan open — denk aan: extra platform-agents, een eigen
domein + Cloudflare Tunnel/Access i.p.v. Tailscale-afhankelijkheid, meer alert-integraties. Houd je
eigen voortgang bij in een eigen `docs/PROGRESS.md` in je private fork — dat bestand is bewust geen
onderdeel van deze publieke template.

---

*Modulair, één geheel, makkelijk te wijzigen. Wordt bewust bijgewerkt zodra de architectuur
wezenlijk verandert — niet bij elke losse fix (dat hoort in `PROGRESS.md`).*
