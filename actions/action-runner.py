#!/usr/bin/env python3
"""
SysDash v12 · actie-runner (trede 1: ZELF-HERSTEL)

Bewaakt de SysDash-diensten en herstart ALLEEN die als ze omvallen.
Veiligheid (niet-onderhandelbaar):
  • WHITELIST-only — kent uitsluitend de vaste acties hieronder. Nooit "voer dit commando uit".
  • Minimale rechten — restart via sudo, en de sudoers-regel staat ALLEEN deze 2 commando's toe.
  • Audit-log — elke actie wordt gelogd (wat, wanneer, waarom).
  • Geen netwerk-trigger — puur lokaal. Geen open poort, geen aanvalsvlak.

Gebruik:
  python3 action-runner.py             # draait continu (systemd)
  python3 action-runner.py --once      # één controleronde
  python3 action-runner.py --dry-run   # controleert + meldt, herstart NIET
"""
import os, sys, time, subprocess, urllib.request

# ── WHITELIST: de ENIGE toegestane acties (naam → exact commando) ──
ACTIONS = {
    "restart-render": ["sudo", "systemctl", "restart", "sysdash-render"],
    "restart-agent":  ["sudo", "systemctl", "restart", "sysdash-agent"],
    # energieprofielen (geen sudo nodig; powerprofilesctl is een user-service)
    "power-saver":       ["powerprofilesctl", "set", "power-saver"],
    "power-balanced":    ["powerprofilesctl", "set", "balanced"],
    "power-performance": ["powerprofilesctl", "set", "performance"],
}

# gewenst-profiel (uit Supabase) → whitelist-actienaam
PROFILE_ACTION = {
    "power-saver":  "power-saver",
    "balanced":     "power-balanced",
    "performance":  "power-performance",
}

# ── Wat te bewaken ──
WATCH = [
    {"unit": "sysdash-render", "health": "http://127.0.0.1:7071/health", "action": "restart-render"},
    {"unit": "sysdash-agent",  "health": None,                            "action": "restart-agent"},
]

INTERVAL   = 60          # seconden tussen controles
FAIL_LIMIT = 2           # zoveel keer achter elkaar 'down' → herstel (voorkomt flap)
AUDIT      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.log")
_fails     = {}

def audit(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, file=sys.stderr)
    try:
        with open(AUDIT, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Supabase-kanaal voor app-gestuurde acties (WHITELIST-bewaakt) ──
# Service-key (niet anon): deze daemon PATCHt applied_profile terug, en machine_actions
# is sinds de RLS-fix niet meer anon-schrijfbaar (zie db/schema.sql).
def _cfg(key):
    return os.environ.get(key, "")
SUPA_URL = _cfg("SUPABASE_URL")
SUPA_KEY = _cfg("SUPABASE_SERVICE_KEY")
MACHINE  = _cfg("MACHINE_NAME") or subprocess.run(["hostname"],capture_output=True,text=True).stdout.strip().lower()
_last_profile = {"val": None}

def _supa(path, method="GET", body=None):
    if not SUPA_URL or not SUPA_KEY: return None
    url = SUPA_URL.rstrip("/") + "/rest/v1/" + path
    data = None
    headers = {"apikey": SUPA_KEY, "Authorization": "Bearer " + SUPA_KEY, "Content-Type": "application/json"}
    if body is not None:
        import json as _j; data = _j.dumps(body).encode(); headers["Prefer"] = "return=minimal"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            import json as _j
            txt = r.read().decode()
            return _j.loads(txt) if txt.strip() else []
    except Exception as e:
        return None

def current_profile():
    try:
        return subprocess.run(["powerprofilesctl","get"], capture_output=True, text=True, timeout=6).stdout.strip()
    except Exception:
        return None

def check_app_actions(dry):
    """Leest gewenst power_profile uit Supabase; past toe via WHITELIST; meldt terug."""
    if not SUPA_URL or not SUPA_KEY: return
    rows = _supa("machine_actions?machine=eq.%s&select=power_profile,applied_profile" % MACHINE)
    if not rows: return
    want = (rows[0] or {}).get("power_profile")
    if not want: return
    if want == _last_profile["val"]: return          # al verwerkt, geen herhaling
    action = PROFILE_ACTION.get(want)
    if not action:
        audit("GEWEIGERD app-actie: onbekend profiel '%s'" % want); return
    ok = run_action(action, dry)                      # HARDE whitelist-grens
    if ok:
        _last_profile["val"] = want
        cur = current_profile()
        _supa("machine_actions?machine=eq.%s" % MACHINE, "PATCH",
              {"applied_profile": cur, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")})
        audit("app-actie toegepast: profiel -> %s (actief: %s)" % (want, cur))

def systemd_active(unit):
    # zelf-detecterend: niet elke machine heeft elke dienst (bv. render hoort alleen bij de hub,
    # niet bij een agent-only laptop) — een dienst die hier niet geïnstalleerd is, laten we met
    # rust i.p.v. 'm te blijven proberen te "herstellen".
    try:
        load = subprocess.run(["systemctl", "show", unit, "--property=LoadState", "--value"],
                               capture_output=True, text=True, timeout=8).stdout.strip()
        if load in ("not-found", ""):
            return None  # niet geïnstalleerd op deze machine → niet ons pakkie-an
        return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=8).returncode == 0
    except Exception:
        return None  # onbekend (bv. geen systemd) → niet herstellen

def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            return r.status == 200
    except Exception:
        return False

def run_action(name, dry):
    # HARDE grens: alleen namen uit de whitelist mogen draaien.
    if name not in ACTIONS:
        audit(f"GEWEIGERD: '{name}' staat niet op de whitelist — genegeerd.")
        return False
    if dry:
        audit(f"[dry-run] zou uitvoeren: {' '.join(ACTIONS[name])}")
        return True
    try:
        r = subprocess.run(ACTIONS[name], timeout=30, capture_output=True, text=True)
        if r.returncode == 0:
            audit(f"HERSTELD: actie '{name}' uitgevoerd.")
            return True
        audit(f"FOUT bij '{name}': {r.stderr.strip()[:200]}")
    except Exception as e:
        audit(f"FOUT bij '{name}': {e}")
    return False

def healthy(w):
    act = systemd_active(w["unit"])
    if act is None:
        return None                       # onbekend → laat met rust
    if not act:
        return False
    if w["health"]:
        return http_ok(w["health"])       # dienst draait, maar reageert 'ie ook?
    return True

def cycle(dry):
    check_app_actions(dry)
    for w in WATCH:
        h = healthy(w)
        if h is None:
            continue
        if h:
            _fails[w["unit"]] = 0
        else:
            _fails[w["unit"]] = _fails.get(w["unit"], 0) + 1
            audit(f"'{w['unit']}' reageert niet ({_fails[w['unit']]}/{FAIL_LIMIT}).")
            if _fails[w["unit"]] >= FAIL_LIMIT:
                run_action(w["action"], dry)
                _fails[w["unit"]] = 0

def main():
    dry = "--dry-run" in sys.argv
    once = "--once" in sys.argv or dry
    audit(f"actie-runner gestart · {'DRY-RUN' if dry else 'actief'} · bewaakt: " + ", ".join(w["unit"] for w in WATCH))
    if once:
        cycle(dry); return
    while True:
        cycle(False)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
