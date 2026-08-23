# SysDash — Draaiboek (SETUP)

Van download tot draaiend systeem. De installer doet het meeste; jij vult de secrets in en zet,
bij Advanced-modus, ook Supabase + n8n op. Nieuw in SysDash en nog nooit met die onderdelen
gewerkt? Begin liever bij [`AAN_DE_SLAG.md`](AAN_DE_SLAG.md) — dat legt ook uit hoe je de
benodigde accounts aanmaakt.

**Opzet:** één machine is de **hub** (dashboard-web + agent, en bij Advanced-modus ook n8n +
render + actie-laag). Extra machines draaien alleen de agent (met of zonder actie-laag). Een
telefoon of ander apparaat is puur kijker.

---

## Wat je nodig hebt

- Een Supabase-project — URL, **service-key**, **anon-key** (Project Settings → API).
- *(Alleen voor Advanced-modus)* Een Discord-webhook.
- Als je meerdere machines wilt: allemaal in hetzelfde (Tailscale-)netwerk voor de BEHEER-acties
  en de dashboard-tunnel.

---

## Stap 1 · Supabase klaarzetten (één keer)
1. Open je Supabase-project → **SQL Editor**.
2. Plak de inhoud van **`db/schema.sql`** (en `db/live.sql` voor de live-modus) en **Run**.
3. Klaar: tabellen `machines · metrics · config · baselines` + view `v_latest` + RLS (web-app leest alleen).

## Stap 2 · De hub installeren
1. Zet de map `sysdash/` op je hoofdmachine (bijv. `~/Projecten/sysdash`).
2. Terminal in die map: `./install/setup.sh`
3. De installer vraagt je secrets (Supabase URL + service-key + anon-key) en een machine-naam, en
   dan: **Basis (alleen kijken) of Advanced (kijken + sturen + meldingen)?** — zie
   [`AAN_DE_SLAG.md`](AAN_DE_SLAG.md) voor het verschil. Bij Advanced vraagt 'm ook meteen om je
   Discord-webhook.
4. De installer zet daarna alles neer: dependencies (incl. Playwright + Chromium), Orbitron,
   agent + dashboard-webserver (+ bij Advanced: render + actie-laag + 2x-daags overzicht),
   systemd-diensten, sudoers, en machine-klaar.
5. Aan het eind zie je het **dashboard-adres**: `http://<jouw-tailscale-ip>:9000`.

**Later alsnog upgraden van Basis naar Advanced?** Geen terminal nodig — klik op het dashboard
(tabblad BEHEER) op **"Upgrade naar Advanced"**. Downgraden kan andersom, ook met een knop.

## Stap 3 · n8n (alleen nodig voor Advanced-modus)
1. Installeer n8n op dezelfde machine als de hub (via npm of Docker).
2. n8n leest `DISCORD_WEBHOOK` uit dezelfde `.env` als de rest van SysDash — zet in `n8n.service`
   `EnvironmentFile=<pad-naar-sysdash>/.env` (i.p.v. losse `Environment=`-regels met geheimen erin)
   en `Environment=N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (nodig zodat een Code-node `$env` mag lezen).
3. In n8n:
   - **Credential** "Supabase SysDash" (project-URL + **service-key**). Bij import selecteren in elke Supabase-node (placeholder `REPLACE_ME`).
   - **Importeer** `n8n/report.json`, `alerts.json`, `battery.json`, `updates.json` en **publiceer** ze.

## Stap 3a · Dead-man's-switch (optioneel maar aanbevolen bij Advanced)
Vangt het geval dat SysDash zélf (of n8n, of Supabase) onbereikbaar wordt — zonder dit blijft zo'n
storing onzichtbaar, want de normale meldingen lopen via dezelfde keten die dan stuk is.
1. Gratis account op [healthchecks.io](https://healthchecks.io) (extern, bewust niet iets van SysDash
   zelf — moet buiten je eigen netwerk/stroom blijven werken).
2. Eén check aanmaken, bv. "SysDash Heartbeat", **Period 10 min / Grace 10 min**.
3. De ping-URL in `HEALTHCHECK_PING_URL` zetten (`.env`).
4. **Importeer** `n8n/heartbeat.json` en **publiceer** 'm (pingt elke 5 min; leeg `.env`-veld = doet niets, geen foutmeldingen).
5. `sudo systemctl restart n8n` — leest `.env` alleen bij opstarten in.
6. Testen: `HEALTHCHECK_PING_URL` tijdelijk leegmaken + n8n herstarten + wachten tot Period+Grace
   verstreken is → moet een "down"-mail geven. Waarde terugzetten + herstarten om te herstellen.

## Stap 4 · Extra machine toevoegen (agent-only)
1. Zet `sysdash/` op de extra machine.
2. Terminal in die map: `./install/install-agent.sh`
3. Vul Supabase URL + service-key + een machine-naam in.

## Stap 5 · Controleren
- **Dashboard**: het adres uit stap 2. Elke machine als eigen tab, live data, auto-refresh.
- **Live-modus**: ~2s hartslag per machine, automatisch.
- *(Advanced)* **Discord**: rapport-kaart + alerts bij drempel/verandering.
- *(Advanced)* **2x-daags overzicht**: `sysdash-overview.timer` (08:00 + 20:00) → per machine een plaatje met 12u in 6 blokken van 2u + piek-veroorzaker (zwaarste proces).
- *(Advanced)* **Zelf-herstel**: `sysdash-actions`. Log: `sysdash/actions/audit.log`.

## Stap 6 · Externe toegang op de telefoon
**Standaard:** trycloudflare quick tunnel (draait als `sysdash-tunnel.service`) → een `https://<willekeurig>.trycloudflare.com`-adres. Echte https, wisselt alleen bij herstart. Geen login ervoor — wie de link heeft kan meekijken, maar bij Advanced-modus niet besturen (dat gaat alleen via het Tailscale-netwerk).

**Fullscreen-PWA (optioneel):** de bouwstenen zitten al in de pagina, maar een écht vaste, altijd-stabiele https-link vraagt een eigen domein. Zodra je dat hebt: een named Cloudflare Tunnel + optioneel Cloudflare Access (login) i.p.v. de wisselende trycloudflare-link.

---

## Handige commando's
```
systemctl status sysdash-agent sysdash-render sysdash-actions sysdash-web sysdash-live sysdash-tunnel sysdash-boot-notify sysdash-overview.timer
journalctl -u sysdash-agent -f          # live agent-log
python3 agent/agent.py --dry-run        # test-meting (geen push)
curl -s http://127.0.0.1:7071/health    # render leeft?
sudo systemctl start|stop sysdash-live  # live-modus op een machine handmatig aan/uit
python3 overview/sysdash-overview.py --print   # 2x-daags overzicht testen (rendert, post niet)
sudo systemctl start sysdash-overview.service  # 2x-daags overzicht nu meteen posten
```

## Twee repo's — publiek + jouw eigen private versie
- **Deze repo** — kale template, nul secrets, placeholder-config.
- **Jouw eigen fork/kopie** (private aanbevolen) — `.env` ingevuld, jouw machines/drempels,
  `docs/PROGRESS.md` met je eigen voortgangslogboek. `git clone` hiervan om een machine (opnieuw)
  op te zetten.
