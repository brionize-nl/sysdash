#!/usr/bin/env bash
# SysDash v12 · HUB-installer (draai op de Asus).
# Zet neer: agent + render-service + actie-laag + dashboard-webserver.
# Idempotent en defensief. Vraagt sudo waar nodig.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
say(){ printf '\n\033[1;36m» %s\033[0m\n' "$1"; }
ok(){ printf '  \033[1;32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[1;33m●\033[0m %s\n' "$1"; }
die(){ printf '  \033[1;31m✗ %s\033[0m\n' "$1"; exit 1; }

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
python3 -c "import cairosvg" 2>/dev/null && ok "cairosvg" || warn "cairosvg onzeker (render-kaart)"

say "2. Orbitron-font"
FD="$HOME/.local/share/fonts"; mkdir -p "$FD"
if [ ! -f "$FD/Orbitron.ttf" ]; then
  curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf" -o "$FD/Orbitron.ttf" \
    && fc-cache -f "$FD" >/dev/null 2>&1 && ok "Orbitron geïnstalleerd" || warn "font-download mislukt (kaart valt terug op DejaVu)"
else ok "Orbitron al aanwezig"; fi

say "3. Secrets (.env)"
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  read -rp "  Supabase URL: " V;             sed -i "s#^SUPABASE_URL=.*#SUPABASE_URL=$V#" "$DIR/.env"
  read -rp "  Supabase SERVICE key: " V;      sed -i "s#^SUPABASE_SERVICE_KEY=.*#SUPABASE_SERVICE_KEY=$V#" "$DIR/.env"
  read -rp "  Supabase ANON key (read-only): " V; sed -i "s#^SUPABASE_ANON_KEY=.*#SUPABASE_ANON_KEY=$V#" "$DIR/.env"
  read -rp "  Discord webhook URL: " V;        sed -i "s#^DISCORD_WEBHOOK=.*#DISCORD_WEBHOOK=$V#" "$DIR/.env"
  DEF=$(hostname | tr 'A-Z' 'a-z'); read -rp "  Machine-naam [$DEF]: " V; V=${V:-$DEF}
  sed -i "s#^MACHINE_NAME=.*#MACHINE_NAME=$V#" "$DIR/.env"
  ok ".env ingevuld"
else ok ".env bestaat al (overslaan — pas handmatig aan indien nodig)"; fi
set -a; . "$DIR/.env"; set +a

say "4. Machine monitoring-klaar maken"
bash "$DIR/install/prepare-machine.sh"

say "5. Dashboard verbinden met Supabase (read-only)"
printf 'window.SYSDASH_CONFIG={url:"%s",anon:"%s"};\n' "${SUPABASE_URL:-}" "${SUPABASE_ANON_KEY:-}" > "$DIR/web/config.js"
ok "web/config.js gevuld (anon-key)"

say "6. Diensten installeren (systemd)"
inst(){ sed -e "s#__USER__#$USER_NAME#g" -e "s#__DIR__#$DIR#g" "$2" | sudo tee "/etc/systemd/system/$1" >/dev/null && ok "$1"; }
inst sysdash-agent.service   "$DIR/agent/sysdash-agent.service"
inst sysdash-render.service  "$DIR/render/sysdash-render.service"
inst sysdash-actions.service "$DIR/actions/sysdash-actions.service"
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
sudo systemctl daemon-reload
sudo systemctl enable --now sysdash-agent sysdash-render sysdash-actions sysdash-web >/dev/null 2>&1 && ok "diensten gestart"

say "7. Actie-laag rechten (minimale sudoers)"
TMP=$(mktemp); sed "s#__USER__#$USER_NAME#g" "$DIR/actions/sudoers.example" > "$TMP"
if sudo visudo -c -f "$TMP" >/dev/null 2>&1; then
  sudo cp "$TMP" /etc/sudoers.d/sysdash && sudo chmod 440 /etc/sudoers.d/sysdash && ok "sudoers geïnstalleerd (alleen restart van sysdash-diensten)"
else warn "sudoers-controle faalde — zelf-herstel kan niet herstarten (rest werkt wel)"; fi
rm -f "$TMP"

say "8. Verificatie"
sleep 3
curl -sf http://127.0.0.1:7071/health >/dev/null 2>&1 && ok "render-service leeft (/health)" || warn "render reageert nog niet — journalctl -u sysdash-render"
systemctl is-active --quiet sysdash-agent && ok "agent draait" || warn "agent niet actief — journalctl -u sysdash-agent"
IP=$(tailscale ip -4 2>/dev/null | head -1)

echo ""
echo "════════════════════════════════════════════════"
echo " KLAAR — de hub draait."
echo "   Dashboard:  http://${IP:-DIT-IP}:9000"
echo ""
echo " Nog handmatig (zie docs/SETUP.md):"
echo "   • Supabase → draai db/schema.sql in de SQL Editor"
echo "   • n8n op deze machine → Supabase-credential + Variable"
echo "     DISCORD_WEBHOOK + importeer n8n/*.json"
echo "════════════════════════════════════════════════"
