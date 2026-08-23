#!/usr/bin/env bash
# SysDash · voegt de Advanced-laag toe aan een bestaande Basis-installatie.
# Draait ALTIJD via 'sudo bash upgrade-to-advanced.sh' — root nodig voor systemd-units + sudoers.
# Doet BEWUST niets met .env (root mag dat bestand niet aanraken — zou de eigenaar/rechten van een
# asus-owned 600-bestand kunnen omzetten naar root en het daarmee onleesbaar maken voor de eigen
# diensten). Wie deze aanroept (de actions-gateway, als de gewone gebruiker) schrijft zelf naar
# .env, vóór en los van deze sudo-aanroep. Dependencies (cairosvg/playwright/font) staan al klaar
# sinds de eerste installatie (setup.sh zet die altijd neer, ongeacht modus) — hier dus alleen
# systemd-units + sudoers, niets anders.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-$(whoami)}"
. "$DIR/install/lib.sh"

[ "$(id -u)" = "0" ] || die "moet als root draaien (sudo bash $0)"

say "Advanced-laag installeren — map: $DIR  gebruiker: $USER_NAME"

inst sysdash-render.service   "$DIR/render/sysdash-render.service"   "$DIR" "$USER_NAME"
inst sysdash-actions.service  "$DIR/actions/sysdash-actions.service" "$DIR" "$USER_NAME"
inst sysdash-overview.service "$DIR/overview/sysdash-overview.service" "$DIR" "$USER_NAME"
inst sysdash-overview.timer   "$DIR/overview/sysdash-overview.timer"  "$DIR" "$USER_NAME"
inst sysdash-boot-notify.service "$DIR/boot-notify/sysdash-boot-notify.service" "$DIR" "$USER_NAME"
inst sysdash-update.service   "$DIR/updater/sysdash-update.service" "$DIR" "$USER_NAME"
inst sysdash-update.timer     "$DIR/updater/sysdash-update.timer"  "$DIR" "$USER_NAME"
systemctl daemon-reload
systemctl enable --now sysdash-render sysdash-actions sysdash-overview.timer sysdash-boot-notify sysdash-update.timer >/dev/null 2>&1 \
  && ok "advanced-diensten gestart"

TMP=$(mktemp)
sed -e "s#__USER__#$USER_NAME#g" -e "s#__DIR__#$DIR#g" "$DIR/actions/sudoers.example" > "$TMP"
if visudo -c -f "$TMP" >/dev/null 2>&1; then
  cp "$TMP" /etc/sudoers.d/sysdash && chmod 440 /etc/sudoers.d/sysdash && ok "volledige sudoers geïnstalleerd"
else
  rm -f "$TMP"; die "sudoers-controle faalde — niets gewijzigd aan rechten, veiligheidshalve gestopt"
fi
rm -f "$TMP"

ok "Advanced-laag klaar. De aanroeper (gateway) herstart zichzelf om de nieuwe modus/rechten te gebruiken."
