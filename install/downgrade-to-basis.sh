#!/usr/bin/env bash
# SysDash · haalt de Advanced-laag weer weg, terug naar Basis (alleen kijken).
# Draait ALTIJD via 'sudo bash downgrade-to-basis.sh' — root nodig voor systemd-units + sudoers.
# Raakt BEWUST .env niet aan (zie upgrade-to-advanced.sh voor de reden — ownership/rechten).
# Stopt/schakelt uit i.p.v. te verwijderen — de unit-bestanden blijven staan (onschadelijk, inactief)
# zodat een latere upgrade ze zo weer kan aanzetten zonder opnieuw te hoeven schrijven.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-$(whoami)}"
. "$DIR/install/lib.sh"

[ "$(id -u)" = "0" ] || die "moet als root draaien (sudo bash $0)"

say "Advanced-laag uitzetten — terug naar Basis"

systemctl disable --now sysdash-render sysdash-actions sysdash-overview.timer sysdash-boot-notify sysdash-update.timer >/dev/null 2>&1
ok "advanced-diensten gestopt en uitgeschakeld (blijven onschadelijk op schijf staan)"

TMP=$(mktemp)
sed -e "s#__USER__#$USER_NAME#g" -e "s#__DIR__#$DIR#g" "$DIR/actions/sudoers-basis.example" > "$TMP"
if visudo -c -f "$TMP" >/dev/null 2>&1; then
  cp "$TMP" /etc/sudoers.d/sysdash && chmod 440 /etc/sudoers.d/sysdash && ok "sudoers versmald naar Basis-whitelist"
else
  rm -f "$TMP"; die "sudoers-controle faalde — niets gewijzigd aan rechten, veiligheidshalve gestopt"
fi
rm -f "$TMP"

ok "Basis-modus actief. De aanroeper (gateway) herstart zichzelf om de nieuwe modus/rechten te gebruiken."
