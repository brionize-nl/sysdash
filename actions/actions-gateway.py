#!/usr/bin/env python3
"""Identity-gated Tailscale action gateway; scoped machine token; fixed root-owned helper."""
import os, re, sys, json, time, threading, subprocess, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import load_env, tailscale_ip, authorized, scoped_request
CFG = load_env()
OPERATORS = CFG.get("SYSDASH_OPERATORS", "")
ORIGINS = set(CFG.get("SYSDASH_ORIGINS", "").split(","))
ACTION_LOCK = threading.Lock()

DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(DIR)
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
AUDIT = os.environ.get("AUDIT_PATH", "/var/lib/sysdash/audit.log")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY  = os.environ.get("AGENT_TOKEN", "")
MACHINE      = os.environ.get("MACHINE_NAME") or subprocess.run(
    ["hostname"], capture_output=True, text=True).stdout.strip().lower()
PORT         = int(os.environ.get("GATEWAY_PORT", "7072"))
# Basis (alleen kijken) vs Advanced (kijken+sturen+meldingen) — bepaalt de whitelist hieronder.
# Onbekende of ontbrekende modus sluit beheeracties af.
INSTALL_MODE = os.environ.get("INSTALL_MODE", "basis").strip().lower()
if INSTALL_MODE not in ("basis", "advanced"):
    INSTALL_MODE = "basis"

# ── WHITELIST: de ENIGE toegestane acties ───────────────────────────────────
RESTART_ACTIONS = {"restart-"+name:["sudo","-n","/usr/local/libexec/sysdash-action","restart-"+name] for name in ("render","agent","web","live","tunnel")}
CLEANUP_STEPS = [["sudo","-n","/usr/local/libexec/sysdash-action","cleanup-safe"]]
REBOOT_CMD = ["sudo","-n","/usr/local/libexec/sysdash-action","reboot"]
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
    try: return tailscale_ip(os.environ.get("GATEWAY_BIND_IP"))
    except Exception: return None

def supa(path, method="GET", body=None):
    try:
        with scoped_request(CFG,path,method,body) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        audit(f"Agent API-fout: {type(e).__name__}")
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
    audit("OPGESCHOOND: apt clean + journalctl vacuum (7d)")
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
    log_action("set-profile", "ok" if ok else "fout", profile)
    return ok, ("klaargezet" if ok else "Supabase-fout")


def do_set_hold(package, hold):
    if not isinstance(package,str) or not re.fullmatch(r"(?:flatpak:)?[A-Za-z0-9][A-Za-z0-9.+:_-]{0,199}",package):
        return False, "ongeldig pakket"
    if hold:
        r = supa("update_holds", "POST", {"machine": MACHINE, "package": package})
    else:
        import urllib.parse
        r = supa(f"update_holds?machine=eq.{urllib.parse.quote(MACHINE)}&package=eq.{urllib.parse.quote(package)}", "DELETE")
    ok = r is not None
    audit(f"{'HOLD' if ok else 'FOUT'}: {package} -> {'overslaan' if hold else 'weer meenemen'}")
    log_action("set-hold", "ok" if ok else "fout", package)
    return ok, ("verwerkt" if ok else "Supabase-fout")


def has_known_webhook():
    return False

# ── HTTP ─────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        origin = self.headers.get("Origin")
        if origin in ORIGINS: self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self._allowed(): self._send(403,{"ok":False,"detail":"Geen beheerrechten"}); return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _allowed(self):
        origin = self.headers.get("Origin")
        return (not origin or origin in ORIGINS) and authorized(self.client_address[0], OPERATORS)

    def do_GET(self):
        if not self._allowed(): self._send(403,{"error":"Geen toegang"}); return
        if self.path == "/health":
            self._send(200, {"status": "ok", "machine": MACHINE})
        elif self.path == "/mode":
            self._send(200, {"mode": INSTALL_MODE, "has_webhook": has_known_webhook()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed(): self._send(403,{"ok":False,"detail":"Geen beheerrechten"}); return
        if not ACTION_LOCK.acquire(blocking=False): self._send(409,{"ok":False,"detail":"Een actie loopt al"}); return
        try:
            self._post()
        finally:
            ACTION_LOCK.release()

    def _post(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n < 1 or n > 8192: raise ValueError("request size")
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(n))
            if not isinstance(body,dict): raise ValueError("expected object")
            for key in ("service","confirm","profile","package"):
                if key in body and not isinstance(body[key],str): raise ValueError("expected string")
            if "hold" in body and not isinstance(body["hold"],bool): raise ValueError("expected boolean")
        except Exception:
            self._send(400, {"error": "ongeldige JSON"}); return

        if body.get("machine") != MACHINE:
            self._send(400,{"ok":False,"detail":"Verkeerde doelmachine"}); return

        # Basis weigert alle systeemacties, ook bij een handmatig gestart proces.
        advanced_only = {"/restart", "/cleanup", "/reboot", "/set-profile", "/set-hold", "/downgrade-to-basis"}
        if INSTALL_MODE == "basis" and self.path in advanced_only:
            audit(f"GEWEIGERD: '{self.path}' vraagt Advanced-modus, deze machine staat op Basis")
            self._send(403, {"ok": False, "detail": "alleen beschikbaar in Advanced-modus"}); return

        if self.path == "/restart":
            allowed = {"restart-agent","restart-live"}
            if CFG.get("SYSDASH_ROLE")=="hub": allowed.update(RESTART_ACTIONS)
            if body.get("service") not in allowed: self._send(400,{"ok":False,"detail":"Dienst niet beschikbaar"}); return
            ok, detail = do_restart(body.get("service", ""))
        elif self.path == "/cleanup":
            ok, detail = do_cleanup()
        elif self.path == "/reboot":
            ok, detail = do_reboot(body.get("confirm", ""))
        elif self.path == "/set-profile":
            ok, detail = do_set_profile(body.get("profile", ""))
        elif self.path == "/set-hold":
            ok, detail = do_set_hold(body.get("package", ""), bool(body.get("hold")))
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
    if not SUPABASE_URL or not SERVICE_KEY or not OPERATORS:
        sys.exit("SUPABASE_URL/AGENT_TOKEN ontbreken.")
    audit(f"actions-gateway gestart · machine={MACHINE} · bind={ts_ip}:{PORT} (Tailscale-only)")
    ThreadingHTTPServer((ts_ip, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
