# SysDash — Aan de slag

Deze gids is voor iemand die SysDash voor het eerst installeert en de losse onderdelen (Supabase,
Discord, n8n) nog nooit heeft gebruikt. Voor de technische details, zie [`SETUP.md`](SETUP.md) en
[`BLUEPRINT.md`](BLUEPRINT.md).

## Eerst: welke smaak wil je?

| | 🔵 Basis | 🟣 Advanced |
|---|---|---|
| Live dashboard bekijken | ✅ | ✅ |
| Zelf diensten herstarten/opschonen/rebooten vanaf het dashboard | ❌ | ✅ |
| Discord-meldingen (schijf vol, te heet, updates...) | ❌ | ✅ |
| Wat moet je aanmaken? | Alleen een Supabase-account | Supabase + Discord-webhook + n8n |
| Tijd | ~5 minuten | ~20-30 minuten |

Twijfel je? Begin met **Basis** — je kunt later, met één klik op het dashboard, altijd upgraden
naar Advanced. Niets gaat daarbij verloren.

---

## Stap 1 · Supabase-account (verplicht, beide smaken)

Supabase is de plek waar je meetdata terechtkomt — SysDash's "geheugen".

1. Ga naar **[supabase.com](https://supabase.com)** en klik rechtsboven op **Start your project**.
2. Log in (bijvoorbeeld met een GitHub-account) en klik op **New project**.
3. Geef het een naam (bijvoorbeeld "SysDash"), kies een wachtwoord voor de database (bewaar dit
   ergens veilig, je hebt het zelden nodig) en een regio bij jou in de buurt. Klik **Create new
   project**. Dit duurt ongeveer een minuut.
4. Zodra het project klaar is: ga naar **Project Settings** (tandwiel-icoon, linksonder) →
   **API**. Daar vind je drie dingen die je zo nodig hebt:
   - **Project URL** (ziet eruit als `https://xxxxx.supabase.co`)
   - **anon / public key** (een lange tekst die begint met `eyJ...`)
   - **service_role key** (ook een lange `eyJ...`-tekst — deze is **geheim**, deel 'm met niemand)
5. Ga naar **SQL Editor** (linkermenu) → **New query**. Open het bestand `db/schema.sql` uit deze
   SysDash-map, kopieer de hele inhoud, plak 'm in de SQL Editor, en klik **Run**. Herhaal dit voor
   `db/live.sql`. Dat zet de tabellen klaar — dit hoef je maar één keer te doen.

Bewaar de URL en de twee sleutels ergens bij de hand — de installer vraagt er zo naar.

---

## Stap 2 · De installer draaien

Open een terminal in de SysDash-map en draai:

```bash
./install/setup.sh
```

De installer vraagt om de Supabase-gegevens van stap 1, en daarna:

> **Basis of Advanced?**

Kies wat bij je past (zie de tabel hierboven). Bij **Basis** ben je na een paar minuten klaar — de
installer laat aan het eind het dashboard-adres zien (bijvoorbeeld `http://100.x.x.x:9000`).

Bij **Advanced** vraagt de installer ook meteen om een Discord-webhook — zie stap 3 hieronder als je
die nog niet hebt.

---

## Stap 3 · Discord-webhook (alleen nodig voor Advanced)

Een webhook is een adres waar SysDash berichten naartoe kan sturen, zonder dat het een echt
Discord-account nodig heeft.

1. Open Discord, ga naar het kanaal waar je de meldingen wil ontvangen (of maak een nieuw kanaal
   aan, bijvoorbeeld `#sysdash`).
2. Klik op het tandwiel-icoon naast het kanaal (**Kanaal bewerken**) → **Integraties** →
   **Webhooks** → **Nieuwe webhook**.
3. Geef 'm eventueel een naam/avatar, en klik **Webhook-URL kopiëren**.
4. Plak die URL wanneer de installer erom vraagt (of later in `.env` bij `DISCORD_WEBHOOK=`).

---

## Stap 4 · n8n (alleen nodig voor Advanced)

n8n is de "meldingen-motor" — het bepaalt wannéér er iets naar Discord gestuurd wordt. Dit is de
enige stap die de installer niet voor je doet, omdat n8n een losstaand programma is.

1. Installeer n8n op dezelfde machine als de SysDash-hub — de makkelijkste manier:
   ```bash
   npx n8n
   ```
   (De eerste keer download je hiermee n8n; daarna kun je 'm ook als systemd-dienst laten draaien,
   zie `SETUP.md` voor een productie-opzet.)
2. Open n8n in je browser (meestal `http://localhost:5678`) en maak een account aan (blijft lokaal
   op jouw machine).
3. Maak één **Credential** aan voor Supabase: naam bijvoorbeeld "SysDash", vul de Project-URL en de
   **service_role key** in (níet de anon key — die is voor het dashboard, niet voor n8n).
4. **Importeer** de workflows uit de map `n8n/` van SysDash (`report.json`, `alerts.json`,
   `battery.json`, `updates.json`, en `heartbeat.json` als je stap 5 ook doet) via **Import from
   File** in n8n, en koppel bij elke workflow de zojuist aangemaakte Supabase-credential.
5. **Publiceer** elke workflow (schakelaar rechtsboven in de workflow-editor).

---

## Stap 5 · Dead-man's-switch (optioneel, aanbevolen bij Advanced)

Dit zorgt dat je ook een melding krijgt als SysDash zélf (of je hele netwerk) onbereikbaar wordt —
zonder dit blijft zo'n storing onzichtbaar, want de normale meldingen lopen via dezelfde keten die
dan stuk is.

1. Gratis account op **[healthchecks.io](https://healthchecks.io)**.
2. **Add Check** → naam bijvoorbeeld "SysDash Heartbeat" → **Period 10 minutes / Grace 10 minutes**.
3. Kopieer de ping-URL die je te zien krijgt (ziet eruit als `https://hc-ping.com/xxxxx...`).
4. Zet die in `.env` bij `HEALTHCHECK_PING_URL=`.
5. Herstart n8n zodat de nieuwe waarde wordt ingelezen.

---

## Klaar — en daarna?

- **Dashboard bekijken:** het adres dat de installer aan het eind toonde, ook vanaf je telefoon
  (zelfde wifi/tailnet).
- **Later upgraden van Basis naar Advanced:** klik op het dashboard (tabblad BEHEER) op
  **"Upgrade naar Advanced"** — geen terminal nodig.
- **Iets vastlopen?** Zie de sectie "Handige commando's" in [`SETUP.md`](SETUP.md).
