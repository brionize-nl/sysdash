#!/usr/bin/env bash
# SysDash v12 · AGENT-installer (draai op een extra machine, bv. de laptop).
# Zet alleen de agent neer (meet + pusht naar Supabase). Geen hub-onderdelen.
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

say "3. Machine monitoring-klaar maken"
bash "$DIR/install/prepare-machine.sh"

say "4. Agent installeren (systemd)"
sed -e "s#__USER__#$USER_NAME#g" -e "s#__DIR__#$DIR#g" "$DIR/agent/sysdash-agent.service" | sudo tee /etc/systemd/system/sysdash-agent.service >/dev/null
sudo systemctl daemon-reload && sudo systemctl enable --now sysdash-agent >/dev/null 2>&1
sleep 2
systemctl is-active --quiet sysdash-agent && ok "agent draait" || warn "agent niet actief — journalctl -u sysdash-agent"
echo ""
echo "KLAAR — deze machine meet nu mee. Zie 'm op het dashboard verschijnen."
