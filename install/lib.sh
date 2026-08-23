# SysDash · gedeelde installer-functies.
# Wordt gesourced door setup.sh, upgrade-to-advanced.sh en downgrade-to-basis.sh — niet zelf
# uitvoerbaar. Voorkomt dat de systemd-unit-templating-logica op drie plekken los staat.
say(){ printf '\n\033[1;36m» %s\033[0m\n' "$1"; }
ok(){ printf '  \033[1;32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[1;33m●\033[0m %s\n' "$1"; }
die(){ printf '  \033[1;31m✗ %s\033[0m\n' "$1"; exit 1; }

# inst <unit-bestandsnaam> <bronbestand> <__DIR__-waarde> <__USER__-waarde>
inst(){
  sed -e "s#__USER__#$4#g" -e "s#__DIR__#$3#g" "$2" | sudo tee "/etc/systemd/system/$1" >/dev/null && ok "$1"
}
