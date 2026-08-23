#!/usr/bin/env bash
# SysDash v12 · HUB-installer (draai op de Asus).
# Zet neer: agent + dashboard-webserver, en (Advanced-modus) render-service + actie-laag + meldingen.
# Idempotent en defensief. Vraagt sudo waar nodig.
#
# Modus:
#   --mode=basis      alleen kijken: agent, live-heartbeat, dashboard, tunnel, minimale gateway.
#   --mode=advanced   alles: + actie-laag (sturen), render/overview/boot-notify/updater (meldingen).
#   Zonder --mode: vraagt het interactief (of leest een reeds bestaande INSTALL_MODE uit .env bij
#   een herinstallatie/upgrade-via-terminal).
#   --noninteractive: sla read-prompts over (verwacht dat .env al gevuld is, of secrets via env-vars).
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
. "$DIR/install/lib.sh"

MODE=""; NONINTERACTIVE=0
for arg in "$@"; do
  case "$arg" in
    --mode=basis) MODE="basis" ;;
    --mode=advanced) MODE="advanced" ;;
    --noninteractive) NONINTERACTIVE=1 ;;
  esac
done

echo "════════════════════════════════════════════════"
echo " SysDash v12 · HUB-installer"
echo " map: $DIR   gebruiker: $USER_NAME"
echo "════════════════════════════════════════════════"

say "1. Dependencies"
command -v python3 >/dev/null || die "python3 ontbreekt"
command -v pip3 >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y python3-pip >/dev/null 2>&1; }
python3 -c "import psutil" 2>/dev/null || pip3 install psutil --break-system-packages -q 2>/dev/null || sudo apt-get install -y python3-psutil >/dev/null 2>&1
python3 -c "import psutil"  2>/dev/null && ok "psutil"  || warn "psutil onzeker"
python3 -c "import cairosvg" 2>/dev/null || { sudo apt-get install -y libcairo2 >/dev/null 2>&1; pip3 install cairosvg --break-system-packages -q 2>/dev/null; }
python3 -c "import cairosvg" 2>/dev/null && ok "cairosvg" || warn "cairosvg onzeker (render-kaart, alleen Advanced-modus)"
python3 -c "import playwright" 2>/dev/null || pip3 install playwright --break-system-packages -q 2>/dev/null
if python3 -c "import playwright" 2>/dev/null; then
  sudo python3 -m playwright install-deps chromium >/dev/null 2>&1
  python3 -m playwright install chromium >/dev/null 2>&1
  ok "playwright + chromium (2x-daags overzicht, alleen Advanced-modus)"
else warn "playwright onzeker (2x-daags overzicht kan mislukken, alleen Advanced-modus)"; fi
# Deps van beide modi worden nu al neergezet — zo hoeft een latere upgrade van Basis naar Advanced
# alleen nog systemd-units + sudoers te regelen, geen dependency-gedoe meer.

say "2. Orbitron-font"
FD="$HOME/.local/share/fonts"; mkdir -p "$FD"
if [ ! -f "$FD/Orbitron.ttf" ]; then
  curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf" -o "$FD/Orbitron.ttf" \
    && fc-cache -f "$FD" >/dev/null 2>&1 && ok "Orbitron geïnstalleerd" || warn "font-download mislukt (kaart valt terug op DejaVu)"
else ok "Orbitron al aanwezig"; fi

say "3. Secrets (.env)"
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  if [ "$NONINTERACTIVE" != "1" ]; then
    read -rp "  Supabase URL: " V;             sed -i "s#^SUPABASE_URL=.*#SUPABASE_URL=$V#" "$DIR/.env"
    read -rp "  Supabase SERVICE key: " V;      sed -i "s#^SUPABASE_SERVICE_KEY=.*#SUPABASE_SERVICE_KEY=$V#" "$DIR/.env"
    read -rp "  Supabase ANON key (read-only): " V; sed -i "s#^SUPABASE_ANON_KEY=.*#SUPABASE_ANON_KEY=$V#" "$DIR/.env"
    DEF=$(hostname | tr 'A-Z' 'a-z'); read -rp "  Machine-naam [$DEF]: " V; V=${V:-$DEF}
    sed -i "s#^MACHINE_NAME=.*#MACHINE_NAME=$V#" "$DIR/.env"
  fi
  ok ".env aangemaakt"
else ok ".env bestaat al (overslaan — pas handmatig aan indien nodig)"; fi
chmod 600 "$DIR/.env" && ok ".env op 600 (alleen owner leesbaar)"
set -a; . "$DIR/.env"; set +a

say "4. Installatiemodus"
EXISTING_MODE="${INSTALL_MODE:-}"
if [ -z "$MODE" ]; then
  if [ -n "$EXISTING_MODE" ] && [ "$NONINTERACTIVE" = "1" ]; then
    MODE="$EXISTING_MODE"
  elif [ "$NONINTERACTIVE" = "1" ]; then
    MODE="advanced"   # veilige default voor non-interactive zonder expliciete keuze
  else
    echo ""
    if [ -n "$EXISTING_MODE" ]; then
      echo "  Je hebt nu: $EXISTING_MODE"
      read -rp "  Basis (alleen kijken) of Advanced (kijken + sturen + meldingen)? [basis/advanced, leeg = $EXISTING_MODE] " V
      MODE="${V:-$EXISTING_MODE}"
    else
      echo "  Basis      = alleen kijken. Geen sturen, geen Discord/n8n, minste rechten."
      echo "  Advanced   = kijken + zelf herstarten/opschonen/rebooten vanaf het dashboard + Discord-meldingen."
      read -rp "  Basis of Advanced? [basis/advanced, default advanced] " V
      MODE="${V:-advanced}"
    fi
  fi
fi
case "$MODE" in
  basis|Basis|BASIS) MODE="basis" ;;
  *) MODE="advanced" ;;
esac
if [ "$MODE" = "advanced" ] && [ -z "${DISCORD_WEBHOOK:-}" ] && [ "$NONINTERACTIVE" != "1" ]; then
  read -rp "  Discord webhook URL: " V; sed -i "s#^DISCORD_WEBHOOK=.*#DISCORD_WEBHOOK=$V#" "$DIR/.env"
fi
if grep -q "^INSTALL_MODE=" "$DIR/.env" 2>/dev/null; then
  sed -i "s#^INSTALL_MODE=.*#INSTALL_MODE=$MODE#" "$DIR/.env"
else
  echo "INSTALL_MODE=$MODE" >> "$DIR/.env"
fi
ok "modus: $MODE"

say "5. Machine monitoring-klaar maken"
bash "$DIR/install/prepare-machine.sh"

say "6. Dashboard verbinden met Supabase (read-only)"
printf 'window.SYSDASH_CONFIG={url:"%s",anon:"%s"};\n' "${SUPABASE_URL:-}" "${SUPABASE_ANON_KEY:-}" > "$DIR/web/config.js"
ok "web/config.js gevuld (anon-key)"

say "7. Diensten installeren (systemd) — Basis"
inst sysdash-agent.service   "$DIR/agent/sysdash-agent.service"   "$DIR" "$USER_NAME"
inst sysdash-live.service    "$DIR/agent/sysdash-live.service"    "$DIR" "$USER_NAME"
cat <<UNIT | sudo tee /etc/systemd/system/sysdash-web.service >/dev/null
[Unit]
Description=SysDash dashboard (statische webserver)
After=network.target
[Service]
User=$USER_NAME
WorkingDirectory=$DIR/web
ExecStart=/usr/bin/python3 -m http.server 9000 --bind 0.0.0.0
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
ok "sysdash-web.service"
inst sysdash-tunnel.service "$DIR/tunnel/sysdash-tunnel.service" "$DIR" "$USER_NAME"
inst sysdash-actions-gateway.service "$DIR/actions/sysdash-actions-gateway.service" "$DIR" "$USER_NAME"
sudo systemctl daemon-reload
sudo systemctl enable --now sysdash-agent sysdash-live sysdash-web sysdash-tunnel sysdash-actions-gateway >/dev/null 2>&1 && ok "basis-diensten gestart"

if [ "$MODE" = "advanced" ]; then
  say "8. Diensten installeren (systemd) — Advanced-extra"
  inst sysdash-render.service   "$DIR/render/sysdash-render.service"   "$DIR" "$USER_NAME"
  inst sysdash-actions.service  "$DIR/actions/sysdash-actions.service" "$DIR" "$USER_NAME"
  inst sysdash-overview.service "$DIR/overview/sysdash-overview.service" "$DIR" "$USER_NAME"
  inst sysdash-overview.timer   "$DIR/overview/sysdash-overview.timer"  "$DIR" "$USER_NAME"
  inst sysdash-boot-notify.service "$DIR/boot-notify/sysdash-boot-notify.service" "$DIR" "$USER_NAME"
  inst sysdash-update.service   "$DIR/updater/sysdash-update.service" "$DIR" "$USER_NAME"
  inst sysdash-update.timer     "$DIR/updater/sysdash-update.timer"  "$DIR" "$USER_NAME"
  sudo systemctl daemon-reload
  sudo systemctl enable --now sysdash-render sysdash-actions sysdash-overview.timer sysdash-boot-notify sysdash-update.timer >/dev/null 2>&1 \
    && ok "advanced-diensten gestart (render/opschoning-zelfherstel/overzicht/boot-melding/auto-update)"
fi

say "9. Actie-laag rechten (minimale sudoers, past bij de gekozen modus)"
if [ "$MODE" = "advanced" ]; then SRC="$DIR/actions/sudoers.example"; else SRC="$DIR/actions/sudoers-basis.example"; fi
TMP=$(mktemp); sed -e "s#__USER__#$USER_NAME#g" -e "s#__DIR__#$DIR#g" "$SRC" > "$TMP"
if sudo visudo -c -f "$TMP" >/dev/null 2>&1; then
  sudo cp "$TMP" /etc/sudoers.d/sysdash && sudo chmod 440 /etc/sudoers.d/sysdash && ok "sudoers geïnstalleerd ($MODE-whitelist)"
else warn "sudoers-controle faalde — acties die sudo nodig hebben werken dan niet"; fi
rm -f "$TMP"

say "10. Verificatie"
sleep 3
systemctl is-active --quiet sysdash-agent && ok "agent draait" || warn "agent niet actief — journalctl -u sysdash-agent"
if [ "$MODE" = "advanced" ]; then
  curl -sf http://127.0.0.1:7071/health >/dev/null 2>&1 && ok "render-service leeft (/health)" || warn "render reageert nog niet — journalctl -u sysdash-render"
fi
IP=$(tailscale ip -4 2>/dev/null | head -1)

echo ""
echo "════════════════════════════════════════════════"
echo " KLAAR — modus: $MODE. De hub draait."
echo "   Dashboard:  http://${IP:-DIT-IP}:9000"
echo ""
if [ "$MODE" = "basis" ]; then
  echo " Basis-modus: alleen kijken. Wil je later ook zelf sturen en Discord-meldingen krijgen?"
  echo "   Klik 'Upgrade naar Advanced' in het dashboard (tabblad BEHEER), of draai:"
  echo "   ./install/setup.sh --mode=advanced"
else
  echo " Nog handmatig (zie docs/SETUP.md):"
  echo "   • Supabase → draai db/schema.sql en db/live.sql in de SQL Editor"
  echo "   • n8n op deze machine → importeer n8n/*.json (incl. heartbeat.json) en publiceer"
  echo "   • Dead-man's-switch (optioneel maar aanbevolen): gratis check op"
  echo "     healthchecks.io aanmaken, ping-URL in HEALTHCHECK_PING_URL (.env)"
fi
echo "════════════════════════════════════════════════"
