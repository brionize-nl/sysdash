#!/usr/bin/env bash
# SysDash boot/shutdown-melding naar Discord. Secrets komen via systemd's EnvironmentFile
# (.env), niet zelf ingelezen — voorkomt een hardcoded projectpad in het script.
set -u
WEBHOOK="${DISCORD_WEBHOOK:-}"
MACHINE="${MACHINE_NAME:-$(hostname|tr 'A-Z' 'a-z')}"
[ -z "$WEBHOOK" ] && exit 0
NOW=$(date '+%H:%M')
if [ "${1:-up}" = "down" ]; then MSG="⏻ $MACHINE gaat herstarten/afsluiten ($NOW)"
else MSG="✓ $MACHINE is weer online ($NOW)"; fi
curl -s -m 8 -H "Content-Type: application/json" -d "$(printf '%s' "$MSG" | python3 -c 'import json,sys;print(json.dumps({"username":"SysDash","content":sys.stdin.read()}))')" "$WEBHOOK" >/dev/null 2>&1
exit 0
