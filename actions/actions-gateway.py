#!/usr/bin/env python3
"""
SysDash v12 · actions-gateway
Alle schrijfacties van het dashboard richting déze machine: energieprofiel, update-holds
("overslaan"-vinkjes), en trede 2+3 (veilige opschoning + herstart vanaf het dashboard).

De ENIGE netwerk-ingang van de actie-laag richting deze machine. Bewust NIET via de publieke
Supabase anon-key: die kon voorheen door iedereen met de dashboard-link, zonder inloggen, gebruikt
worden om rechtstreeks naar machine_actions/update_holds/live_control te schrijven — drie tabellen
bleken een wagenwijd-open "ALL/true/true"-policy te hebben, ontstaan doordat ze ooit los van
schema.sql handmatig zijn aangemaakt. Gevonden en dichtgezet, zie PROGRESS.md.

Veiligheid (niet-onderhandelbaar, zelfde geest als action-runner.py):
  • Bindt UITSLUITEND op het Tailscale-IP van deze machine (auto-gedetecteerd via
    `tailscale ip -4`) — onbereikbaar vanaf het publieke internet. Het dashboard zelf staat ook
    via een trycloudflare-tunnel open, maar die tunnelt alleen poort 9000, nooit deze poort, en
    het Tailscale-IP is sowieso niet publiek routeerbaar. Wie alleen de publieke link heeft, kan
    dus WEL meekijken, NIET meer besturen.
  • WHITELIST-only — kent uitsluitend de vaste acties hieronder. Nooit vrije commando's.
  • Bevestiging zit aan de dashboard-kant (knop + confirm-dialoog); de gateway voert synchroon uit
    en meldt direct terug (ok/fout) i.p.v. te wachten op een volgende poll-ronde.
  • Audit: elke actie in actions/audit.log én in Supabase action_log (zichtbaar in het dashboard).
  • Schrijft naar Supabase met de SERVICE-key — vandaar een losse dienst, nooit in browser-JS.

Gebruik: draait continu als systemd-service (sysdash-actions-gateway).
"""
import os, re, sys, json, time, threading, subprocess, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(DIR)
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
AUDIT = os.path.join(DIR, "audit.log")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY", "")
MACHINE      = os.environ.get("MACHINE_NAME") or subprocess.run(
    ["hostname"], capture_output=True, text=True).stdout.strip().lower()
PORT         = int(os.environ.get("GATEWAY_PORT", "7072"))
# Basis (alleen kijken) vs Advanced (kijken+sturen+meldingen) — bepaalt de whitelist hieronder.
# Onbekend/ontbrekend = advanced: bestaande installaties (van vóór dit onderscheid bestond) hebben
# geen INSTALL_MODE in hun .env en moeten hun huidige rechten gewoon behouden.
INSTALL_MODE = os.environ.get("INSTALL_MODE", "advanced").strip().lower()
if INSTALL_MODE not in ("basis", "advanced"):
    INSTALL_MODE = "advanced"

# ── WHITELIST: de ENIGE toegestane acties ───────────────────────────────────
RESTART_ACTIONS = {
    "restart-render": ["sudo", "systemctl", "restart", "sysdash-render"],
    "restart-agent":  ["sudo", "systemctl", "restart", "sysdash-agent"],
    "restart-web":    ["sudo", "systemctl", "restart", "sysdash-web"],
    "restart-live":   ["sudo", "systemctl", "restart", "sysdash-live"],
    "restart-tunnel": ["sudo", "systemctl", "restart", "sysdash-tunnel"],
}
CLEANUP_STEPS = [
    ["sudo", "apt-get", "autoremove", "-y"],
    ["sudo", "apt-get", "clean"],
    ["sudo", "journalctl", "--vacuum-time=7d"],
]
REBOOT_CMD = ["sudo", "systemctl", "reboot"]
PROFILE_WHITELIST = {"power-saver", "balanced", "performance"}


def audit(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, file=sys.stderr)
    try:
        with open(AUDIT, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def detect_tailscale_ip():
    override = os.environ.get("GATEWAY_BIND_IP")
    if override:
        return override
    try:
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.strip()
        return ip or None
    except Exception:
        return None


def supa(path, method="GET", body=None):
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Content-Type": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal" if method == "POST" else "return=minimal"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt.strip() else []
    except Exception as e:
        audit(f"Supabase-fout ({method} {path}): {e}")
        return None


def log_action(action, status, detail=""):
    supa("action_log", "POST", {"machine": MACHINE, "action": action, "status": status, "detail": (detail or "")[:500]})


def run_cmd(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[:1000]
    except Exception as e:
        return False, str(e)


def do_restart(service):
    if service not in RESTART_ACTIONS:
        audit(f"GEWEIGERD: onbekende herstart-actie '{service}'")
        return False, "onbekende dienst"
    ok, out = run_cmd(RESTART_ACTIONS[service])
    audit(f"{'HERSTART' if ok else 'FOUT'}: {service} — {out or 'ok'}")
    log_action(service, "ok" if ok else "fout", out)
    return ok, out


def do_cleanup():
    all_out = []
    for cmd in CLEANUP_STEPS:
        ok, out = run_cmd(cmd, timeout=180)
        all_out.append(f"$ {' '.join(cmd)}\n{out}")
        if not ok:
            audit(f"FOUT bij opschoning ({' '.join(cmd)}): {out}")
            log_action("cleanup-safe", "fout", "\n".join(all_out))
            return False, "\n".join(all_out)
    detail = "\n".join(all_out)
    audit("OPGESCHOOND: apt autoremove + apt clean + journalctl vacuum (7d)")
    log_action("cleanup-safe", "ok", detail)
    return True, detail


def do_reboot(confirm_name):
    # trede 4: herstart de HELE machine, niet alleen een sysdash-dienst — bewust géén poweroff
    # (dat zou de machine buiten bereik zetten; een reboot komt vanzelf terug via systemd enabled-
    # services). Extra server-side check bovenop de dashboard-confirm: de aanroeper moet de
    # machinenaam exact meesturen, zodat een verkeerd-gerichte klik (verkeerde tab actief) nooit
    # per ongeluk de verkeerde machine herstart.
    if confirm_name != MACHINE:
        audit(f"GEWEIGERD: reboot-bevestiging '{confirm_name}' komt niet overeen met machine '{MACHINE}'")
        return False, "machinenaam komt niet overeen"
    ok, out = run_cmd(REBOOT_CMD)
    audit(f"{'REBOOT' if ok else 'FOUT'}: hele machine herstart aangevraagd — {out or 'ok'}")
    log_action("reboot", "ok" if ok else "fout", out)
    return ok, out


def do_set_profile(profile):
    if profile not in PROFILE_WHITELIST:
        audit(f"GEWEIGERD: onbekend energieprofiel '{profile}'")
        return False, "onbekend profiel"
    r = supa("machine_actions?on_conflict=machine", "POST",
             {"machine": MACHINE, "power_profile": profile, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    ok = r is not None
    audit(f"{'PROFIEL-WENS' if ok else 'FOUT'}: {profile} klaargezet (trede-1-daemon past 'm binnen ~60s toe)")
    return ok, ("klaargezet" if ok else "Supabase-fout")


def do_set_hold(package, hold):
    if not package or not isinstance(package, str) or len(package) > 200:
        return False, "ongeldig pakket"
    if hold:
        r = supa("update_holds", "POST", {"machine": MACHINE, "package": package})
    else:
        import urllib.parse
        r = supa(f"update_holds?machine=eq.{urllib.parse.quote(MACHINE)}&package=eq.{urllib.parse.quote(package)}", "DELETE")
    ok = r is not None
    audit(f"{'HOLD' if ok else 'FOUT'}: {package} -> {'overslaan' if hold else 'weer meenemen'}")
    return ok, ("verwerkt" if ok else "Supabase-fout")


DISCORD_WEBHOOK_RE = re.compile(r"^https://discord\.com/api/webhooks/\d+/[\w-]+$")


def set_env_var(key, value):
    """Schrijft één KEY=VALUE-regel in .env, in-place (behoudt eigenaar/rechten — belangrijk
    omdat deze gateway als de gewone gebruiker draait, nooit als root, precies om dat te garanderen)."""
    try:
        with open(ENV_PATH) as f:
            lines = f.readlines()
    except Exception as e:
        return False, str(e)
    found = False
    out = []
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}\n")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}\n")
    try:
        with open(ENV_PATH, "w") as f:
            f.writelines(out)
        return True, ""
    except Exception as e:
        return False, str(e)


def deferred_gateway_restart(delay=1.5):
    def _go():
        time.sleep(delay)
        run_cmd(["sudo", "systemctl", "restart", "sysdash-actions-gateway"])
    threading.Thread(target=_go, daemon=True).start()


def has_known_webhook():
    return bool(DISCORD_WEBHOOK_RE.match(os.environ.get("DISCORD_WEBHOOK", "")))


def do_upgrade_to_advanced(discord_webhook):
    if INSTALL_MODE != "basis":
        return False, "al in Advanced-modus"
    if discord_webhook:
        # nieuwe/andere webhook opgegeven — die gebruiken en opslaan
        if not DISCORD_WEBHOOK_RE.match(discord_webhook):
            return False, "ongeldige Discord-webhook-URL"
        ok, err = set_env_var("DISCORD_WEBHOOK", discord_webhook)
        if not ok:
            audit(f"FOUT: kon DISCORD_WEBHOOK niet naar .env schrijven: {err}")
            return False, "kon .env niet schrijven"
    elif not has_known_webhook():
        # geen nieuwe opgegeven én nog geen bestaande bekend — dan moet er echt eentje komen
        return False, "geen Discord-webhook bekend, nog niet ingevuld"
    # anders: geen nieuwe opgegeven, maar er staat al een geldige in .env — die gewoon hergebruiken
    script = os.path.join(PROJECT_DIR, "install", "upgrade-to-advanced.sh")
    ok, out = run_cmd(["sudo", "bash", script], timeout=180)
    if not ok:
        audit(f"FOUT bij upgrade naar advanced: {out}")
        log_action("upgrade-to-advanced", "fout", out)
        return False, out
    set_env_var("INSTALL_MODE", "advanced")
    audit("UPGRADE: Basis -> Advanced voltooid, gateway herstart zichzelf")
    log_action("upgrade-to-advanced", "ok", out)
    deferred_gateway_restart()
    return True, "upgrade geslaagd, gateway herstart zichzelf (~2s)"


def do_downgrade_to_basis():
    if INSTALL_MODE != "advanced":
        return False, "al in Basis-modus"
    script = os.path.join(PROJECT_DIR, "install", "downgrade-to-basis.sh")
    ok, out = run_cmd(["sudo", "bash", script], timeout=60)
    if not ok:
        audit(f"FOUT bij downgrade naar basis: {out}")
        log_action("downgrade-to-basis", "fout", out)
        return False, out
    set_env_var("INSTALL_MODE", "basis")
    audit("DOWNGRADE: Advanced -> Basis voltooid, gateway herstart zichzelf")
    log_action("downgrade-to-basis", "ok", out)
    deferred_gateway_restart()
    return True, "downgrade geslaagd, gateway herstart zichzelf (~2s)"


# ── HTTP ─────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")   # veilig: netwerk-gate (Tailscale-bind) is de echte grens
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "machine": MACHINE})
        elif self.path == "/mode":
            self._send(200, {"mode": INSTALL_MODE, "has_webhook": has_known_webhook()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, {"error": "ongeldige JSON"}); return

        # Basis-modus: alléén de upgrade-actie is ooit toegestaan — ook al zou een van de
        # onderstaande routes toevallig aangeroepen worden, hier wordt 'm hoe dan ook geweigerd
        # (defense in depth, naast dat de sudoers in Basis-modus deze commando's al niet kent).
        advanced_only = {"/restart", "/cleanup", "/reboot", "/set-profile", "/set-hold", "/downgrade-to-basis"}
        if INSTALL_MODE == "basis" and self.path in advanced_only:
            audit(f"GEWEIGERD: '{self.path}' vraagt Advanced-modus, deze machine staat op Basis")
            self._send(403, {"ok": False, "detail": "alleen beschikbaar in Advanced-modus"}); return

        if self.path == "/restart":
            ok, detail = do_restart(body.get("service", ""))
        elif self.path == "/cleanup":
            ok, detail = do_cleanup()
        elif self.path == "/reboot":
            ok, detail = do_reboot(body.get("confirm", ""))
        elif self.path == "/set-profile":
            ok, detail = do_set_profile(body.get("profile", ""))
        elif self.path == "/set-hold":
            ok, detail = do_set_hold(body.get("package", ""), bool(body.get("hold")))
        elif self.path == "/upgrade-to-advanced":
            ok, detail = do_upgrade_to_advanced(body.get("discord_webhook", ""))
        elif self.path == "/downgrade-to-basis":
            ok, detail = do_downgrade_to_basis()
        else:
            self._send(404, {"error": "not found"}); return
        self._send(200 if ok else 500, {"ok": ok, "detail": detail})

    def log_message(self, *a):  # stil (geen console-spam)
        pass


def main():
    ts_ip = detect_tailscale_ip()
    if not ts_ip:
        sys.exit("kon Tailscale-IP niet bepalen ('tailscale ip -4' faalde) — gateway start NIET "
                 "(bindt bewust nergens anders, om nooit per ongeluk publiek open te staan).")
    if not SUPABASE_URL or not SERVICE_KEY:
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_KEY ontbreken (.env).")
    audit(f"actions-gateway gestart · machine={MACHINE} · bind={ts_ip}:{PORT} (Tailscale-only)")
    ThreadingHTTPServer((ts_ip, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
