#!/usr/bin/env bash
# SysDash · maakt een machine "monitoring-klaar" (idempotent, veilig).
# - wifi-powersave uit (voorkomt wegvallende verbinding — de fix die we vonden)
# - sensoren beschikbaar maken (lm-sensors)
# - auto-suspend op netstroom uit (scherm mag uit, machine blijft aan)
# Draai:  bash prepare-machine.sh
set -u
say(){ printf '\n\033[1;36m» %s\033[0m\n' "$1"; }
ok(){ printf '  \033[1;32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[1;33m●\033[0m %s\n' "$1"; }

say "1. Wifi-powersave uitzetten (stabiele verbinding)"
IFACE=$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')
if [ -n "${IFACE:-}" ]; then
  sudo iw dev "$IFACE" set power_save off 2>/dev/null && ok "nu uit op $IFACE" || warn "kon niet direct zetten"
  printf '[connection]\nwifi.powersave = 2\n' | sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf >/dev/null \
    && sudo systemctl restart NetworkManager 2>/dev/null && ok "blijvend uit (na herstart ook)"
else
  warn "geen wifi-interface gevonden (bekabeld? dan niet nodig)"
fi

say "2. Sensoren beschikbaar maken (lm-sensors)"
if ! command -v sensors >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y lm-sensors >/dev/null 2>&1 && ok "lm-sensors geinstalleerd" || warn "installatie mislukt"
else
  ok "lm-sensors is al aanwezig"
fi
command -v sensors-detect >/dev/null 2>&1 && { sudo sensors-detect --auto >/dev/null 2>&1 && ok "sensors-detect gedraaid"; }

say "3. Auto-suspend op netstroom uit (scherm mag wel uit)"
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null \
    && ok "slaapt niet meer op netstroom" || warn "kon gsettings niet zetten (geen GNOME?)"
else
  warn "gsettings niet gevonden — sla suspend-instelling over"
fi

say "Klaar — machine is monitoring-klaar."
