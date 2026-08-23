#!/usr/bin/env bash
# SysDash · veilige auto-update MET hold-respect.
# Leest per machine de 'overslaan'-lijst uit Supabase, zet die op apt-mark hold,
# draait dan upgrade (holds worden overgeslagen), meldt resultaat in Discord.
set -u
LOG="/var/log/sysdash-update.log"
WEBHOOK="${DISCORD_WEBHOOK:-}"
SUPABASE_URL="${SUPABASE_URL:-}"
ANON="${SUPABASE_ANON_KEY:-}"
MACHINE="${MACHINE_NAME:-$(hostname|tr 'A-Z' 'a-z')}"
export DEBIAN_FRONTEND=noninteractive
ts(){ date '+%Y-%m-%d %H:%M:%S'; }
log(){ echo "[$(ts)] $*" >>"$LOG"; }

log "=== update-run gestart (machine=$MACHINE) ==="
apt-get update -y >>"$LOG" 2>&1

# 1) haal de hold-lijst op uit Supabase
HOLDS=""
if [ -n "$SUPABASE_URL" ] && [ -n "$ANON" ]; then
  HOLDS=$(curl -s -H "apikey: $ANON" -H "Authorization: Bearer $ANON" \
    "$SUPABASE_URL/rest/v1/update_holds?machine=eq.$MACHINE&select=package" 2>/dev/null \
    | grep -o '"package":"[^"]*"' | cut -d'"' -f4)
fi

# 2) eerst ALLE eventueel eerder gezette holds vrijgeven (schone lei), dan de actuele zetten
#    (zo werkt opnieuw-aanvinken: staat 'ie niet meer in de lijst, dan wordt 'ie niet meer geblokkeerd)
for p in $(apt-mark showhold 2>/dev/null); do apt-mark unhold "$p" >>"$LOG" 2>&1; done
HELDCOUNT=0
FLATPAK_HOLDS=""
for p in $HOLDS; do
  case "$p" in
    flatpak:*) FLATPAK_HOLDS="$FLATPAK_HOLDS ${p#flatpak:}"; HELDCOUNT=$((HELDCOUNT+1)) ;;
    *)         apt-mark hold "$p" >>"$LOG" 2>&1 && HELDCOUNT=$((HELDCOUNT+1)) ;;
  esac
done
log "holds gezet: $HELDCOUNT (apt+flatpak)"

# 3) tel wat er (na holds) bijgewerkt gaat worden
PLANNED=$(LC_ALL=C apt-get -s upgrade 2>/dev/null | grep -c '^Inst ')

# 4) upgrade (holds worden automatisch overgeslagen), veilige config-afhandeling
apt-get upgrade -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold >>"$LOG" 2>&1
RC=$?
# autoremove bewust WEG (beschermt oude kernels als vangnet)
# flatpak-updates (sandbox, veilig, geen herstart). Sla de uitgevinkte (FLATPAK_HOLDS) over.
FLATPAK_DONE=0
if command -v flatpak >/dev/null 2>&1; then
  for app in $(flatpak remote-ls --updates --columns=application 2>/dev/null | grep -v -i "^application"); do
    [ -z "$app" ] && continue
    skip=0
    for h in $FLATPAK_HOLDS; do [ "$h" = "$app" ] && skip=1; done
    if [ "$skip" -eq 0 ]; then
      flatpak update -y "$app" >>"$LOG" 2>&1 && FLATPAK_DONE=$((FLATPAK_DONE+1))
    fi
  done
fi
PLANNED=$((PLANNED + FLATPAK_DONE))
REBOOT="nee"; [ -f /var/run/reboot-required ] && REBOOT="JA"
log "klaar (rc=$RC) bijgewerkt=$PLANNED (waarvan $FLATPAK_DONE flatpak) overgeslagen=$HELDCOUNT herstart=$REBOOT"

# 5) Discord-melding
if [ -n "$WEBHOOK" ]; then
  if [ "$PLANNED" -eq 0 ] && [ "$HELDCOUNT" -eq 0 ]; then
    MSG="Auto-update ($MACHINE) - alles was up-to-date."
  else
    SYM="OK"; [ "$REBOOT" = "JA" ] && SYM="LET OP"
    EXTRA=""; [ "$HELDCOUNT" -gt 0 ] && EXTRA=" ($HELDCOUNT overgeslagen op jouw verzoek)"
    MSG="[$SYM] Auto-update ($MACHINE) - $PLANNED bijgewerkt$EXTRA. Herstart nodig: $REBOOT."
  fi
  curl -s -H "Content-Type: application/json" \
    -d "$(printf '%s' "$MSG" | python3 -c 'import json,sys;print(json.dumps({"username":"SysDash","content":sys.stdin.read()}))')" \
    "$WEBHOOK" >/dev/null 2>&1
fi
log "=== einde ==="
