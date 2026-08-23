#!/usr/bin/env bash
# SysDash v12 · AGENT-installer (draai op een extra machine, bv. de laptop).
# Zet de agent (meet + pusht naar Supabase) + de actie-laag neer (trede 1 zelf-herstel,
# trede 2-4 opschoning/herstart/reboot vanaf het dashboard). Geen hub-onderdelen (dashboard,
# render, tunnel, auto-update, live-modus, overzicht) — die horen bij install/setup.sh.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
say(){ printf '\n\033[1;36m» %s\033[0m\n' "$1"; }
ok(){ printf '  \033[1;32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[1;33m●\033[0m %s\n' "$1"; }
die(){ printf '  \033[1;31m✗ %s\033[0m\n' "$1"; exit 1; }

echo "SysDash v12 · AGENT-installer — map: $DIR · gebruiker: $USER_NAME"

say "1. Dependencies"
command -v python3 >/dev/null || die "python3 ontbreekt"
python3 -c "import psutil" 2>/dev/null || { command -v pip3 >/dev/null || sudo apt-get install -y python3-pip >/dev/null 2>&1; pip3 install psutil --break-system-packages -q 2>/dev/null || sudo apt-get install -y python3-psutil >/dev/null 2>&1; }
python3 -c "import psutil" 2>/dev/null && ok "psutil" || die "psutil kon niet geïnstalleerd worden"

say "2. Secrets (.env)"
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  read -rp "  Supabase URL: " V;         sed -i "s#^SUPABASE_URL=.*#SUPABASE_URL=$V#" "$DIR/.env"
  read -rp "  Supabase SERVICE key: " V;  sed -i "s#^SUPABASE_SERVICE_KEY=.*#SUPABASE_SERVICE_KEY=$V#" "$DIR/.env"
  DEF=$(hostname | tr 'A-Z' 'a-z'); read -rp "  Machine-naam [$DEF]: " V; V=${V:-$DEF}
  sed -i "s#^MACHINE_NAME=.*#MACHINE_NAME=$V#" "$DIR/.env"
  ok ".env ingevuld"
else ok ".env bestaat al"; fi
chmod 600 "$DIR/.env" && ok ".env op 600 (alleen owner leesbaar)"

say "3. Machine monitoring-klaar maken"
bash "$DIR/install/prepare-machine.sh"

say "4. Agent installeren (systemd)"
inst(){ sed -e "s#__USER__#$USER_NAME#g" -e "s#__DIR__#$DIR#g" "$2" | sudo tee "/etc/systemd/system/$1" >/dev/null && ok "$1"; }
inst sysdash-agent.service "$DIR/agent/sysdash-agent.service"
sudo systemctl daemon-reload && sudo systemctl enable --now sysdash-agent >/dev/null 2>&1
sleep 2
systemctl is-active --quiet sysdash-agent && ok "agent draait" || warn "agent niet actief — journalctl -u sysdash-agent"

say "5. Actie-laag (zelf-herstel + acties vanaf het dashboard)"
inst sysdash-actions.service "$DIR/actions/sysdash-actions.service"
inst sysdash-actions-gateway.service "$DIR/actions/sysdash-actions-gateway.service"
sudo systemctl daemon-reload
sudo systemctl enable --now sysdash-actions sysdash-actions-gateway >/dev/null 2>&1 && ok "action-runner + actions-gateway gestart"

say "6. Actie-laag rechten (minimale sudoers)"
TMP=$(mktemp); sed "s#__USER__#$USER_NAME#g" "$DIR/actions/sudoers.example" > "$TMP"
if sudo visudo -c -f "$TMP" >/dev/null 2>&1; then
  sudo cp "$TMP" /etc/sudoers.d/sysdash && sudo chmod 440 /etc/sudoers.d/sysdash && ok "sudoers geïnstalleerd (whitelist: restart sysdash-diensten + veilige opschoning + herstart)"
else warn "sudoers-controle faalde — zelf-herstel kan niet herstarten (rest werkt wel)"; fi
rm -f "$TMP"

echo ""
echo "KLAAR — deze machine meet nu mee én kan vanaf het dashboard bediend worden"
echo "(profiel/opschoning/herstart/reboot). Zie 'm op het dashboard verschijnen."
