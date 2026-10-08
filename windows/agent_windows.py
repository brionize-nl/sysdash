#!/usr/bin/env python3
"""
SysDash v12 · Windows-agent (LICHTE versie)
Leest kernmetingen via psutil en PUSHT ze elke ~30s naar Supabase — zelfde tabel, zelfde
dashboard als de Linux-agent. Bewust géén temperaturen/updates-telling/hardware-info: Windows
heeft daar geen ingebouwde, betrouwbare bron voor (temps zouden een extra tool als
LibreHardwareMonitor vergen, updates werken fundamenteel anders dan apt) — dat is een aparte
uitbreiding voor later, geen kwartiertje werk. Ook geen actie-laag (opschonen/herstarten/reboot
vanaf het dashboard) — deze machine is alleen-meten, geen Tailscale nodig.

Gebruik:
  python agent_windows.py            # draait continu (voor Taakplanner)
  python agent_windows.py --once     # één meting, dan stoppen
  python agent_windows.py --dry-run  # meet + print JSON, pusht NIET (voor testen)
"""
import os, sys, time, json, socket, datetime, urllib.request, urllib.error

try:
    import psutil
except ImportError:
    sys.exit("psutil ontbreekt — installeer: pip install psutil")

# ─────────────────────────── config (.env) ───────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import load_env as shared_load_env, utcnow, scoped_request

def load_env():
    return shared_load_env(os.path.join(os.path.dirname(__file__), ".env"))

CFG = load_env()
SUPABASE_URL = (CFG.get("SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY  = CFG.get("AGENT_TOKEN") or ""
MACHINE      = CFG.get("MACHINE_NAME") or socket.gethostname().lower()
INTERVAL     = int(CFG.get("PUSH_INTERVAL_SEC") or 30)
NCPU         = psutil.cpu_count() or 1
SYSTEM_DRIVE = (os.environ.get("SystemDrive") or "C:") + "\\"

# ─────────────────────────── metingen ───────────────────────────
def get_battery():
    fn = getattr(psutil, "sensors_battery", None)
    b = None
    try:
        b = fn() if fn else None
    except Exception:
        b = None
    if b is None:
        return {}  # geen accu (desktop)
    return {"battery": round(b.percent, 1), "bat_plugged": bool(b.power_plugged)}

def get_disks():
    disks, root = [], None
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        disks.append({"mount": p.mountpoint, "pct": round(u.percent, 1), "gb": round(u.total / 1e9)})
        if p.mountpoint.upper() == SYSTEM_DRIVE.upper():
            root = round(u.percent, 1)
    return (root, disks or None)

def internet_up():
    for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            s = socket.create_connection(host, timeout=2); s.close(); return True
        except Exception:
            continue
    return False

_net_prev = {"ts": None, "rx": 0, "tx": 0}
def get_net():
    io = psutil.net_io_counters()
    now = time.time()
    rx = tx = None
    if _net_prev["ts"] is not None:
        dt = max(0.001, now - _net_prev["ts"])
        rx = round((io.bytes_recv - _net_prev["rx"]) / dt)
        tx = round((io.bytes_sent - _net_prev["tx"]) / dt)
    _net_prev.update(ts=now, rx=io.bytes_recv, tx=io.bytes_sent)
    return rx, tx

def collect():
    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try: p.cpu_percent(None)
        except Exception: pass
    cores = psutil.cpu_percent(interval=1.0, percpu=True)          # dit is ons ~1s venster
    cpu = round(sum(cores) / len(cores), 1) if cores else None

    all_procs = []
    for p in procs:
        try:
            all_procs.append({"name": (p.info.get("name") or "?")[:24],
                        "cpu": round(p.cpu_percent(None) / NCPU, 1),
                        "mem": round(p.memory_percent(), 1)})
        except Exception:
            continue
    top = sorted(all_procs, key=lambda x: x["cpu"], reverse=True)[:5]
    top_mem = sorted(all_procs, key=lambda x: x["mem"], reverse=True)[:5]

    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    try: freq = round(psutil.cpu_freq().current)
    except Exception: freq = None
    root_disk, disks = get_disks()
    rx, tx = get_net()

    row = {
        "machine": MACHINE,
        "cpu": cpu,
        "cores": [round(c, 1) for c in cores] if cores else None,
        "mem": round(vm.percent, 1),
        "swap": round(sw.percent, 1),
        "disk": root_disk, "disks": disks,
        "freq": freq,
        "net_rx": rx, "net_tx": tx, "net_up": internet_up(),
        "uptime": int(time.time() - psutil.boot_time()),
        "top_procs": top or None,
        "extra": {"top_procs_mem": top_mem or None, "disk_days_left": get_disk_forecast(root_disk)},
    }
    row.update(get_battery())
    # None-velden weglaten houdt de payload schoon (kolommen blijven NULL) — geen temp/updates/
    # hardware in deze lichte versie, precies zoals afgesproken.
    return {k: v for k, v in row.items() if v is not None}

# ─────────────────────────── push naar Supabase ───────────────────────────
def _req(path, method, body=None, extra_headers=None):
    return scoped_request(CFG, path, method, body)

_DISK_FC_CACHE = {"t": 0.0, "days": None}
def get_disk_forecast(cur_disk):
    """Lineaire trend: bij dit tempo over hoeveel dagen is de schijf vol? Zelfde logica als de
    Linux-agent — puur Supabase-historie, geen OS-specifieke aanroepen nodig."""
    if cur_disk is None or not SUPABASE_URL or not SERVICE_KEY:
        return None
    now = time.time()
    if now - _DISK_FC_CACHE["t"] < 1800:
        return _DISK_FC_CACHE["days"]
    _DISK_FC_CACHE["t"] = now
    try:
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        since = (now_dt - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        r = _req(f"metrics?machine=eq.{MACHINE}&select=disk,ts&ts=lte.{since}&order=ts.desc&limit=1", "GET")
        rows = json.loads(r.read().decode())
        if not rows or rows[0].get("disk") is None:
            _DISK_FC_CACHE["days"] = None; return None
        old_disk = rows[0]["disk"]
        old_dt = datetime.datetime.fromisoformat(rows[0]["ts"].replace("Z", "+00:00"))
        elapsed_days = (now_dt - old_dt).total_seconds() / 86400
        if elapsed_days < 1:
            _DISK_FC_CACHE["days"] = None; return None
        rate = (cur_disk - old_disk) / elapsed_days
        if rate <= 0.01:
            _DISK_FC_CACHE["days"] = None; return None
        _DISK_FC_CACHE["days"] = max(0, round((100 - cur_disk) / rate, 1))
    except Exception:
        _DISK_FC_CACHE["days"] = None
    return _DISK_FC_CACHE["days"]

def push(row):
    _req("metrics", "POST", row, {"Prefer": "return=minimal"})

def touch_machine():
    # zelf-registrerend: upsert i.p.v. PATCH, zodat deze machine bij de eerste push zelf een
    # rij aanmaakt (met auto-gedetecteerde kind/has_battery) i.p.v. stil te falen omdat er nog
    # niemand handmatig een rij voor 'm in Supabase heeft gezet.
    try:
        fn = getattr(psutil, "sensors_battery", None)
        has_battery = bool(fn and fn())
        _req("machines?on_conflict=machine", "POST",
             {"machine": MACHINE, "last_seen": utcnow(),
              "has_battery": has_battery, "kind": "laptop" if has_battery else "desktop", "os":"windows", "role":"agent", "capabilities":{}},
             {"Prefer": "resolution=merge-duplicates,return=minimal"})
    except Exception:
        pass

# ─────────────────────────── main ───────────────────────────
def one_cycle(dry):
    row = collect()
    if dry:
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return True
    try:
        touch_machine(); push(row)
        print(f"[{time.strftime('%H:%M:%S')}] gepusht: cpu={row.get('cpu')}% mem={row.get('mem')}% machine={MACHINE}")
        return True
    except urllib.error.HTTPError as e:
        print(f"[fout] Supabase weigerde ({e.code}): {e.read().decode()[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[fout] push mislukt: {e}", file=sys.stderr)
    return False

def main():
    dry = "--dry-run" in sys.argv
    once = "--once" in sys.argv or dry
    if not dry and (not SUPABASE_URL or not SERVICE_KEY):
        sys.exit("SUPABASE_URL en AGENT_TOKEN ontbreken (.env). Gebruik --dry-run om te testen.")
    print(f"SysDash Windows-agent (licht) · machine={MACHINE} · interval={INTERVAL}s · {'DRY-RUN' if dry else 'push naar '+SUPABASE_URL}", file=sys.stderr)
    if once:
        sys.exit(0 if one_cycle(dry) else 1)
    while True:
        t0 = time.time()
        one_cycle(False)
        time.sleep(max(1, INTERVAL - (time.time() - t0)))

if __name__ == "__main__":
    main()
