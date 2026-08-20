# SysDash v12 — Draaiboek (SETUP)

Van download tot draaiend systeem. De installer doet het meeste; jij vult de secrets in en zet Supabase + n8n op.

**Opzet:** de **Asus (`pro`)** is de hub (n8n + render + actie-laag + agent + dashboard-web). De **laptop (`delli5`)** draait alleen de agent. De telefoon is kijker.

> **Stand nu (19 aug):** dit draaiboek is uitgevoerd — SysDash draait live op de Asus in `~/Downloads/sysdash/`, dashboard op `http://<asus-tailscale-ip>:9000` (tailnet) en extern via een trycloudflare-link. Voor een schone-machine herinstallatie geldt het hele draaiboek hieronder.

---

## Wat je nodig hebt (heb je al)
- Supabase-project ("SysDash-Health") — URL, **service-key**, **anon-key** (Project Settings → API).
- Discord-webhook (kanaal #sysdash-v12 → Integraties → Webhooks).
- Beide machines in je tailnet (`izebrion@`).

---

## Stap 1 · Supabase klaarzetten (één keer)
1. Open je Supabase-project → **SQL Editor**.
2. Plak de inhoud van **`db/schema.sql`** en **Run**.
3. Klaar: tabellen `machines · metrics · config · baselines` + view `v_latest` + RLS (web-app leest alleen).

## Stap 2 · De HUB installeren (op de Asus)
1. Zet de map `sysdash/` op de Asus (git clone van je private repo, of kopieer).
2. Terminal in die map: `./install/setup.sh`
3. De installer vraagt je secrets (Supabase URL + service-key + anon-key + Discord-webhook) en machine-naam (`pro`), en zet daarna alles neer: dependencies, Orbitron, agent + render + actie-laag + dashboard-webserver (systemd), sudoers, en machine-klaar (wifi-powersave uit, sensoren, geen suspend).
4. Aan het eind zie je het **dashboard-adres**: `http://<asus-tailscale-ip>:9000` (nu: `http://<asus-tailscale-ip>:9000`).

## Stap 3 · n8n op de Asus (meldingen-motor)
1. Installeer n8n op de Asus (via npm of Docker).
2. In n8n:
   - **Credential** "Supabase SysDash" (project-URL + **service-key**). Bij import selecteren in elke Supabase-node (placeholder `REPLACE_ME`).
   - **Variable** `DISCORD_WEBHOOK` = je webhook-URL (n8n → Variables). Alle workflows lezen 'm daar (één plek).
   - **Importeer** `n8n/report.json`, `alerts.json`, `battery.json`, `updates.json` en **publiceer** ze.

## Stap 4 · De laptop toevoegen (agent-only)
1. Zet `sysdash/` op de laptop.
2. Terminal in die map: `./install/install-agent.sh`
3. Vul Supabase URL + service-key + machine-naam (`delli5`) in. De agent start en pusht.

## Stap 5 · Controleren
- **Dashboard**: `http://<asus-tailscale-ip>:9000`. Beide machines als tabs, live data, auto-refresh.
- **Live-modus**: ⚡LIVE-knop → ~2s hartslag (alleen de actieve tab). Uit = 30s. Accu-beleid: Asus 24/7 live; laptop-live handmatig (`sudo systemctl start|stop sysdash-live`).
- **Discord**: rapport-kaart verschijnt op het rapport-moment (of test-execute in n8n). Alerts (offline · schijf · temp · geen internet · accu · updates) komen bij een echte drempel/verandering.
- **Zelf-herstel**: draait als `sysdash-actions`. Log: `sysdash/actions/audit.log`.

## Stap 6 · Externe toegang op de telefoon (huidige stand + toekomst)
**Nu:** het dashboard is buitenshuis bereikbaar via een **trycloudflare quick tunnel** op de Asus → een `https://<willekeurig>.trycloudflare.com`-adres. De https is echt (versleuteld). De link is willekeurig en **wisselt alleen bij een herstart**; de verse link wordt automatisch naar Discord gepost, dus je hebt 'm altijd bij de hand. Let op: er zit **geen login** voor — wie de link heeft, kan meekijken (niet besturen; de actie-laag is Tailscale-only).

**Fullscreen-PWA (geparkeerd):** de PWA-onderdelen (manifest, service worker, iconen, meta) zitten al in de pagina. Écht fullscreen op de telefoon (zonder Chrome-adresbalk) vraagt een **vaste** https-URL, en dat vraagt een **eigen domein**. Zodra je ooit een (goedkoop) domein neemt:
```
telefoon → https://sysdash.<jouw-domein> → [Cloudflare Tunnel] → http-server op de Asus (:9000)
```
Dan een **named** Cloudflare Tunnel (domein-nameservers bij Cloudflare, gratis plan) + optioneel Cloudflare Access (gratis login → alleen jij). Zonder domein blijft trycloudflare de gratis route (met de wisselende-link-eigenschap). Tailscale HTTPS is stabiel+gratis maar botst met de VPN → daarom niet gekozen.

---

## Handige commando's
```
systemctl status sysdash-agent sysdash-render sysdash-actions sysdash-web sysdash-live
journalctl -u sysdash-agent -f          # live agent-log
python3 agent/agent.py --dry-run        # test-meting (geen push)
curl -s http://127.0.0.1:7071/health    # render leeft?
sudo systemctl start|stop sysdash-live  # laptop live handmatig aan/uit
```

## Twee repo's (brionize) — nog op te zetten
- **public `sysdash`** — kale template (nul secrets; `.env` op `.gitignore`).
- **private `sysdash-brionize`** — jouw versie mét ingevulde `.env` en `web/config.js`.
- *(GitHub-backup staat nog op de to-do — zie PROGRESS.md.)*

## Opruimen (pas als v12 bewezen draait)
De oude opzet (`custom-monitor`, oude `sysdash-render`, oude n8n-workflows op de laptop, Captain Hook) mag dan uit. Rustig, gecontroleerd.

## Klein aandachtspunt (locatie)
Het pakket leeft nu in `~/Downloads/sysdash` op de Asus. Downloads is bedoeld als tijdelijk doorgeefluik; ooit netjes verplaatsen naar een echte projectmap (bijv. `~/Projecten/sysdash`) — samen met de GitHub-backup.
