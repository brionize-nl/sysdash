#!/usr/bin/env bash
set -u
WEBHOOK="${DISCORD_WEBHOOK:-}"
LOG="/tmp/sysdash-tunnel.log"
: > "$LOG"
cloudflared tunnel --url http://localhost:9000 >>"$LOG" 2>&1 &
CFPID=$!
URL=""
for i in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && break
  sleep 1
done
if [ -n "$URL" ]; then
  echo "$URL" > /tmp/sysdash-tunnel-url.txt
  if [ -n "$WEBHOOK" ]; then
    MSG="SysDash is nu bereikbaar op: $URL"
    curl -s -H "Content-Type: application/json" -d "$(printf '%s' "$MSG" | python3 -c 'import json,sys;print(json.dumps({"username":"SysDash","content":sys.stdin.read()}))')" "$WEBHOOK" >/dev/null 2>&1
  fi
fi
wait $CFPID
