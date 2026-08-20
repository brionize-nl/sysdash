# SysDash v12 — Blauwdruk (v1.1)

*From-scratch, schoon, modulair-maar-samenhangend. Met de kennis van nu.*

---

## 1. Doel

Eén net monitoring-systeem, opnieuw opgebouwd zodat alles strak en voorspelbaar is:

- **Meerdere machines**: `delli5` (laptop) + `pro` (Asus) worden bemeten; `s22-ultra` (telefoon) is kijker.
- **Werkt overal**: Supabase is de bron — webpagina en meldingen lezen daaruit, ook buiten Tailscale.
- **Kant-en-klaar**: één download + een installer die je door de laatste stappen loodst.
- **Twee sporen**: publieke kale template + jouw private ingevulde versie.
- **Modulair, maar één geheel**: elk onderdeel is een module (map), samen één pakket.

---

## 2. Wat er anders is dan de oude opzet (= minder gedoe)

| Oud probleem | Nu opgelost door |
|---|---|
| "Waar staat welk script?" | Vaste mappenstructuur |
| Secret op 4 plekken (het lek van vandaag) | Eén `.env`, alles leest daaruit |
| Handmatig hardware checken | De installer **probet** zichzelf automatisch |
| Botsen met oude troep | Schone opzet = niks om mee te botsen |
| Machine viel weg (wifi-powersave) | Installer maakt elke machine "monitoring-klaar" |

**Eerlijk:** de allereerste run legt altijd íets bloot — dat is opstarten, geen audit.

---

## 3. Architectuur (het geheel, in modules)

```
   delli5 (laptop)     pro (Asus)        machines met een AGENT
        │  push metrics  │               (psutil + /sys, auto-detect)
        └───────┬────────┘
                ▼
          SUPABASE  ← bron van waarheid (metrics·machines·config·rollups·historie)
          read│        │read
              ▼        ▼
      WEB dashboard   n8n workflows ── spec ──► RENDER (HUD-kaart) ──► Discord
      (kijken, ook    (meldingen, 3 lagen,
       telefoon/PWA)   1 webhook-variabele)
```

**Kennis-van-nu-verbetering:** de agent **pusht** zelf naar Supabase. Machine erbij = agent draaien, klaar.

---

## 4. Mappenstructuur (één pakket)

```
sysdash/
├─ README.md
├─ .env.example              # sjabloon voor secrets (LEEG)
├─ .gitignore                # beschermt .env → nooit online
├─ install/
│   ├─ setup.sh              # hoofd-installer (checkt·configureert·verifieert)
│   ├─ install-agent.sh      # alleen-agent (voor extra machine: pro)
│   ├─ prepare-machine.sh    # maakt machine 'monitoring-klaar' (powersave/suspend/autoconnect)
│   └─ probe.py              # hardware-recon (draait de installer automatisch)
├─ agent/        agent.py · config.example.json · sysdash-agent.service
├─ render/       render.py · sysdash-render.service
├─ web/          index.html · app.js · style.css · manifest.webmanifest · assets/
├─ n8n/          alerts.json · updates.json · battery.json · report.json · connectivity.json
├─ actions/      action-runner.py · sysdash-actions.service · sudoers.example   (actie-laag)
├─ db/           schema.sql   (tabellen + RLS read-only)
└─ docs/         SETUP.md · BLUEPRINT.md · PROGRESS.md
```

---

## 5. Twee repo's onder brionize

- **`sysdash`** (public) — kale template, `.env.example`, **nul secrets**.
- **`sysdash-brionize`** (private) — jóuw versie, `.env` ingevuld, jouw machines/drempels.
- `.env` op `.gitignore` → secrets komen **nooit** in een repo.

---

## 6. Installer-flow

**Hub-machine (delli5):** `./install/setup.sh`
1. Dependencies checken.
2. `.env` invullen (Supabase URL + keys, Discord webhook).
3. `probe.py` → auto-detect hardware → agent-config.
4. **`prepare-machine.sh`** → wifi-powersave uit, suspend uit, autoconnect check. *(nieuw — precies het probleem dat we vandaag vonden)*
5. Agent + render-service installeren (systemd), starten.
6. n8n-workflows + DB-schema aanleveren.
7. Verifiëren + klaar-melding.

**Extra machine (pro):** `./install/install-agent.sh` — agent + prepare-machine.

---

## 7. Automatisch vs. jij invult

- **Automatisch:** hardware-probe, machine-klaar-maken, mappen, services, checks, backups, verificatie.
- **Jij vult in (kan ik nooit zien):** Supabase URL + sleutels, Discord-webhook. Via `.env`.

---

## 8. Alert-filosofie — 3 lagen (i.p.v. platte drempels)

Niet "elk getal boven een drempel", maar zinnige lagen. **Drempels per machine instelbaar (config-tabel), met verstandige defaults.**

**Laag 1 — Vitaal (hard alarm):**
- Machine offline (schrijft > 10 min niet) — per machine
- Schijf (bijna) vol — waarschuwing 80%, alarm 90%, per mount
- Accu kritiek — op accu én < 15%
- Temp echt te heet — > 90°C aanhoudend
- **Connectiviteit weg** — machine heeft geen internet/Tailscale meer *(nieuw)*

**Laag 2 — Trend (vroeg signaal):**
- Schijf vol over ~X dagen (voorspelling, seintje < 14 dagen)
- Accu-slijtage (conditie zakt verder weg)
- Ongewoon voor dit tijdstip (baseline — heeft historie nodig)

**Laag 3 — Info (rustig, geen alarm):**
- Updates (bij verandering)
- Periodiek rapport (HUD-kaart, elke 2u tussen 07-23)

**Geschrapt:** losse CPU/RAM-piek-alerts → ruis. Structureel hoog vangt de baseline (laag 2).

---

## 9. Actie-laag — op afstand veilig dingen dóen (gefaseerd)

Via Tailscale, zolang de machine internet heeft. Van ongevaarlijk naar krachtiger:

- **Trede 1 — Zelf-herstel:** dienst valt om → automatisch herstart. Lokaal, geen risico.
- **Trede 2 — Veilige opschoning (met bevestiging):** schijf vol → één vast commando (`apt autoremove`, logs/`/tmp`).
- **Trede 3 — Dienst herstarten vanaf telefoon:** één vaste actie per dienst, bevestiging.
- **Trede 4 — "Nu updaten"-knop:** één vast update-commando, bevestiging. Als laatste.

**Veiligheidsruggengraat (niet-onderhandelbaar):**
- **Whitelist** — alleen vaste, benoemde acties. Nóóit "voer dit commando uit".
- Minimale rechten (smalle sudoers), **bevestiging** bij ingrijpen, **alleen Tailscale**, **logboek**.
- **Expliciet NIET:** automatisch door inlog-/verbind-/captive-portal-schermen klikken. Dat bouwen we niet.

---

## 10. Sessie-continuïteit — voortgangs-logboek

`docs/PROGRESS.md`: wat af is · volgend blok · beslissingen. Onderbreking = plak PROGRESS.md, we gaan naadloos verder. Alles staat tóch als bestand bij jou + op GitHub.

---

## 11. Bouwvolgorde (fases — elk blok afgerond opgeleverd)

1. DB-schema + RLS (fundering)
2. Agent (push) + probe + prepare-machine
3. Render-service (HUD-kaart)
4. n8n-meldingen (3 lagen, schoon)
5. Web dashboard (v4-ontwerp, interactief)
6. Actie-laag (trede 1 eerst; 2-4 gefaseerd)
7. Installer + docs + repo-structuur

Na elk blok: `PROGRESS.md` bijgewerkt.

---

## 12. Nu aan zet

Eén **recon-run**: `probe.py` op **delli5** én **pro**, uitvoer plakken. Daarna werk ik alles uit tot een afgerond pakket; jij komt er pas weer bij voor de eindrun.

---

*Modulair, één geheel, makkelijk te wijzigen. Alles wat je vroeg — netjes op een rij.*
