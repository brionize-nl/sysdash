#!/usr/bin/env bash
set -u
LOG="/var/log/sysdash-update.log"
WEBHOOK="${DISCORD_WEBHOOK:-}"
export DEBIAN_FRONTEND=noninteractive
echo "[$(date '+%F %T')] start" >>"$LOG"
apt-get update -y >>"$LOG" 2>&1
PLANNED=$(LC_ALL=C apt-get -s upgrade 2>/dev/null | grep -c '^Inst ')
apt-get upgrade -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold >>"$LOG" 2>&1
apt-get autoremove -y >>"$LOG" 2>&1
REBOOT="nee"; [ -f /var/run/reboot-required ] && REBOOT="JA"
echo "[$(date '+%F %T')] klaar bijgewerkt=$PLANNED herstart=$REBOOT" >>"$LOG"
if [ -n "$WEBHOOK" ]; then
  if [ "$PLANNED" -eq 0 ]; then MSG="✓ Auto-update ($(hostname)) — alles was up-to-date."
  else SYM="✓"; [ "$REBOOT" = "JA" ] && SYM="▲"; MSG="$SYM Auto-update ($(hostname)) — $PLANNED pakket(ten) bijgewerkt. Herstart: $REBOOT."; fi
  curl -s -H "Content-Type: application/json" -d "$(printf '%s' "$MSG" | python3 -c 'import json,sys;print(json.dumps({"username":"SysDash","content":sys.stdin.read()}))')" "$WEBHOOK" >/dev/null 2>&1
fi
