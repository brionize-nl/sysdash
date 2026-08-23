#!/usr/bin/env python3
"""
SysDash v12 · agent
Leest systeemwaarden via psutil + /sys en PUSHT ze elke ~30s naar Supabase.
Zelf-configurerend: detecteert per machine wat er is (accu ja/nee, welke sensoren) —
niks hardcoded. Alleen stdlib + psutil (geen requests nodig).

Gebruik:
  python3 agent.py            # draait continu (voor systemd)
  python3 agent.py --once     # één meting, dan stoppen
  python3 agent.py --dry-run  # meet + print JSON, pusht NIET (voor testen)
"""
import os, sys, time, json, socket, glob, subprocess, datetime, urllib.request, urllib.error

try:
    import psutil
except ImportError:
    sys.exit("psutil ontbreekt — installeer: pip3 install psutil  (of: sudo apt install python3-psutil)")

# ─────────────────────────── config (.env) ───────────────────────────
def load_env():
    cfg = dict(os.environ)
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "..", ".env"), os.path.join(here, ".env"), os.path.expanduser("~/sysdash/.env")):
        if os.path.isfile(path):
            for ln in open(path):
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    cfg.setdefault(k.strip(), v.strip())
            break
    return cfg

CFG = load_env()
SUPABASE_URL = (CFG.get("SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY  = CFG.get("SUPABASE_SERVICE_KEY") or ""
MACHINE      = CFG.get("MACHINE_NAME") or socket.gethostname().lower()
INTERVAL     = int(CFG.get("PUSH_INTERVAL_SEC") or 30)
NCPU         = psutil.cpu_count() or 1

# ─────────────────────────── metingen ───────────────────────────
def get_temps():
    """Alle temperatuur-sensoren → (primaire temp, core-temps lijst, alle sensoren dict)."""
    temps, core_temps, primary = {}, [], None
    fn = getattr(psutil, "sensors_temperatures", None)
    if not fn:
        return None, None, None
    try:
        data = fn() or {}
    except Exception:
        return None, None, None
    pkg = None
    for chip, arr in data.items():
        for s in arr:
            label = (s.label or "").strip()
            key = f"{chip}/{label}" if label else chip
            if s.current is None:
                continue
            temps[key] = round(s.current, 1)
            if chip == "coretemp":
                if label.lower().startswith("package"):
                    pkg = s.current
                elif label.lower().startswith("core"):
                    core_temps.append(round(s.current))
    # primaire temp: coretemp-package > hoogste core-temp > hoogste sensor
    if pkg is not None:
        primary = round(pkg)
    elif core_temps:
        primary = max(core_temps)
    elif temps:
        primary = round(max(temps.values()))
    return primary, (core_temps or None), (temps or None)

def get_fans():
    fn = getattr(psutil, "sensors_fans", None)
    if not fn:
        return None
    try:
        data = fn() or {}
    except Exception:
        return None
    out = {}
    for chip, arr in data.items():
        for s in arr:
            key = f"{chip}/{s.label}" if s.label else chip
            out[key] = s.current
    return out or None

def get_battery():
    fn = getattr(psutil, "sensors_battery", None)
    b = None
    try:
        b = fn() if fn else None
    except Exception:
        b = None
    if b is None:
        return {}  # geen accu (desktop)
    out = {"battery": round(b.percent, 1), "bat_plugged": bool(b.power_plugged)}
    # conditie uit /sys
    base = (sorted(glob.glob("/sys/class/power_supply/BAT*")) or [None])[0]
    if base:
        def r(f):
            try: return int(open(os.path.join(base, f)).read().strip())
            except Exception: return None
        full = r("charge_full") or r("energy_full")
        design = r("charge_full_design") or r("energy_full_design")
        if full and design and design > 0:
            out["bat_health"] = round(full * 100 / design, 1)
        try: out["bat_status"] = open(os.path.join(base, "status")).read().strip()
        except Exception: pass
    return out

def get_disks():
    disks, root = [], None
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        disks.append({"mount": p.mountpoint, "pct": round(u.percent, 1), "gb": round(u.total / 1e9)})
        if p.mountpoint == "/":
            root = round(u.percent, 1)
    return (root, disks or None)

def internet_up():
    for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            s = socket.create_connection(host, timeout=2); s.close(); return True
        except Exception:
            continue
    return False

_updates_cache = {"ts": 0, "val": None}
def get_updates():
    if time.time() - _updates_cache["ts"] < 240 and _updates_cache["val"] is not None:
        return _updates_cache["val"]
    val = None
    try:
        env = dict(os.environ, LC_ALL="C")
        r = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=20, env=env)
        n_apt = sum(1 for ln in r.stdout.splitlines() if ln.strip() and not ln.startswith("Listing"))
        n_flat = 0
        try:
            rf = subprocess.run(["flatpak", "remote-ls", "--updates", "--columns=application"], capture_output=True, text=True, timeout=25)
            n_flat = sum(1 for ln in rf.stdout.splitlines() if ln.strip() and not ln.strip().lower().startswith("application"))
        except Exception:
            n_flat = 0
        val = n_apt + n_flat
    except Exception:
        val = None
    _updates_cache.update(ts=time.time(), val=val)
    return val

_updates_list_cache = {"ts": 0, "val": None}




_hw_cache = {"ts": 0, "val": None}
def hardware_info():
    if time.time() - _hw_cache["ts"] < 3600 and _hw_cache["val"] is not None:
        return _hw_cache["val"]
    hw = {}
    try:
        for ln in open("/proc/cpuinfo"):
            if ln.startswith("model name"):
                cpu = ln.split(":",1)[1].strip().replace("(R)","").replace("(TM)","").replace("CPU ","")
                hw["cpu"] = cpu; break
    except Exception: pass
    try:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemTotal"):
                hw["ram_gb"] = round(int(ln.split()[1])/1024/1024); break
    except Exception: pass
    try:
        out = subprocess.run(["sudo","-n","dmidecode","-t","memory"], capture_output=True, text=True, timeout=8).stdout
        import re as _re
        t = _re.search(r"\n\s*Type:\s*(DDR\d)", out); sp = _re.search(r"Speed:\s*(\d+)\s*MT/s", out)
        if t: hw["ram_type"] = t.group(1)
        if sp: hw["ram_speed"] = sp.group(1)
    except Exception: pass
    parts = []
    if hw.get("ram_gb"): parts.append("%d GB" % hw["ram_gb"])
    if hw.get("ram_type"): parts.append(hw["ram_type"])
    if hw.get("ram_speed"): parts.append(hw["ram_speed"] + " MT/s")
    if parts: hw["ram_str"] = " ".join(parts)
    try:
        import re as _re2
        out = subprocess.run(["lsblk","-ndo","NAME,SIZE,TYPE,MODEL"], capture_output=True, text=True, timeout=8).stdout
        for ln in out.splitlines():
            m = _re2.match(r"^(\S+)\s+(\S+)\s+disk\s+(.+)$", ln)
            if m:
                hw["disk"] = "%s (%s)" % (m.group(3).strip(), m.group(2)); break
    except Exception: pass
    _hw_cache.update(ts=time.time(), val=hw)
    return hw

def reboot_required():
    try:
        return os.path.exists("/var/run/reboot-required")
    except Exception:
        return False

def get_updates_list():
    if time.time() - _updates_list_cache["ts"] < 240 and _updates_list_cache["val"] is not None:
        return _updates_list_cache["val"]
    pkgs = []
    KERNEL = ("linux-image", "linux-generic", "linux-headers", "linux-modules", "linux-tools")
    try:
        env = dict(os.environ, LC_ALL="C")
        r = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=20, env=env)
        upg = []
        for ln in r.stdout.splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("Listing"): continue
            upg.append(ln.split("/")[0].strip())
        sim = subprocess.run(["apt-get", "-s", "upgrade"], capture_output=True, text=True, timeout=25, env=env)
        would_install = set()
        for ln in sim.stdout.splitlines():
            if ln.startswith("Inst "):
                parts = ln.split()
                if len(parts) >= 2: would_install.add(parts[1])
        for name in upg:
            if not name: continue
            is_kernel = any(k in name for k in KERNEL)
            is_held = name not in would_install
            risk = "rood" if (is_kernel or is_held) else "blauw"
            pkgs.append({"name": name, "risk": risk, "kind": "apt"})
    except Exception:
        pass
    try:
        rf = subprocess.run(["flatpak", "remote-ls", "--updates", "--columns=application"], capture_output=True, text=True, timeout=25)
        for ln in rf.stdout.splitlines():
            ln = ln.strip()
            if not ln or ln.lower().startswith("application"): continue
            pkgs.append({"name": ln, "risk": "blauw", "kind": "flatpak"})
    except Exception:
        pass
    _updates_list_cache.update(ts=time.time(), val=pkgs)
    return pkgs


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
    # processen primen (voor CPU%), dan het CPU-interval als meet-venster gebruiken
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
    # aparte top-5 op geheugen: een RAM-vreter met weinig CPU staat anders niet in de lijst
    # (nodig voor een betrouwbare "veroorzaker" bij een swap/RAM-alert)
    top_mem = sorted(all_procs, key=lambda x: x["mem"], reverse=True)[:5]

    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    la = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
    try: freq = round(psutil.cpu_freq().current)
    except Exception: freq = None
    primary_temp, core_temps, temps = get_temps()
    root_disk, disks = get_disks()
    rx, tx = get_net()

    row = {
        "machine": MACHINE,
        "cpu": cpu,
        "cores": [round(c, 1) for c in cores] if cores else None,
        "mem": round(vm.percent, 1),
        "swap": round(sw.percent, 1),
        "disk": root_disk, "disks": disks,
        "load1": round(la[0], 2) if la[0] is not None else None,
        "load5": round(la[1], 2) if la[1] is not None else None,
        "load15": round(la[2], 2) if la[2] is not None else None,
        "temp": primary_temp, "core_temps": core_temps, "temps": temps,
        "fans": get_fans(),
        "freq": freq,
        "net_rx": rx, "net_tx": tx, "net_up": internet_up(),
        "updates": get_updates(),
        "uptime": int(time.time() - psutil.boot_time()),
        "top_procs": top or None,
        "extra": {"updates_list": get_updates_list(), "reboot_required": reboot_required(),
                  "top_procs_mem": top_mem or None, "disk_days_left": get_disk_forecast(root_disk)},
    }
    row.update(get_battery())
    # None-velden weglaten houdt de payload schoon (kolommen blijven NULL)
    return {k: v for k, v in row.items() if v is not None}

# ─────────────────────────── push naar Supabase ───────────────────────────
def _req(path, method, body=None, extra_headers=None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
               "Content-Type": "application/json"}
    if extra_headers: headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    return urllib.request.urlopen(r, timeout=10)

_DISK_FC_CACHE = {"t": 0.0, "days": None}
def get_disk_forecast(cur_disk):
    """Lineaire trend: bij dit tempo over hoeveel dagen is de schijf vol?
    Vergelijkt nu met ~7 dagen terug (eigen historie in Supabase). None bij te weinig
    geschiedenis of een schijf die niet aan het vollopen is — geen loze cijfers."""
    if cur_disk is None or not SUPABASE_URL or not SERVICE_KEY:
        return None
    now = time.time()
    if now - _DISK_FC_CACHE["t"] < 1800:      # elke 30 min is vaak genoeg voor een trend
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
        rate = (cur_disk - old_disk) / elapsed_days   # %-punten per dag
        if rate <= 0.01:
            _DISK_FC_CACHE["days"] = None; return None       # niet aan het vollopen
        _DISK_FC_CACHE["days"] = max(0, round((100 - cur_disk) / rate, 1))
    except Exception:
        _DISK_FC_CACHE["days"] = None
    return _DISK_FC_CACHE["days"]

def push(row):
    _req("metrics", "POST", row, {"Prefer": "return=minimal"})

_hw_last_pushed_ts = 0
def push_hardware_if_changed():
    # hardware verandert nooit tussen twee reboots — apart bijgewerkt op machines (1 rij),
    # niet elke 30s dubbel meegestuurd in de groeiende metrics-tijdreeks. Alleen een write als
    # hardware_info()'s eigen cache (1u) net vers is berekend, niet elke cyclus.
    global _hw_last_pushed_ts
    hw = hardware_info()
    if hw and _hw_cache["ts"] != _hw_last_pushed_ts:
        try:
            _req(f"machines?machine=eq.{MACHINE}", "PATCH", {"hardware": hw}, {"Prefer": "return=minimal"})
            _hw_last_pushed_ts = _hw_cache["ts"]
        except Exception:
            pass

def touch_machine():
    # zelf-registrerend: upsert i.p.v. PATCH, zodat een nog nooit geziene machine gewoon een
    # rij aanmaakt (met auto-gedetecteerde kind/has_battery) i.p.v. dat de PATCH stil faalt
    # omdat de rij nog niet bestaat (was het geval bij elke nieuwe derde+ machine).
    try:
        fn = getattr(psutil, "sensors_battery", None)
        has_battery = bool(fn and fn())
        _req("machines?on_conflict=machine", "POST",
             {"machine": MACHINE, "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "has_battery": has_battery, "kind": "laptop" if has_battery else "desktop"},
             {"Prefer": "resolution=merge-duplicates,return=minimal"})
    except Exception:
        pass

# ─────────────────────────── main ───────────────────────────

def collect_live():
    # processen primen (voor CPU%), zelfde patroon als collect() — daarna het bestaande
    # 0.4s-interval van de live-lus als meet-venster hergebruiken (geen extra latency).
    # Was eerder op geheugen gesorteerd zónder cpu-veld: het net-paneel toont %CPU-balkjes,
    # dus die klapten elke 2s leeg tot de volgende 30s-meting ze weer herstelde.
    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try: p.cpu_percent(None)
        except Exception: pass
    cores = psutil.cpu_percent(interval=0.4, percpu=True)
    cpu = round(sum(cores)/len(cores),1) if cores else None
    vm = psutil.virtual_memory()
    primary_temp, core_temps, _ = get_temps()
    row = {"machine": MACHINE, "cpu": cpu, "mem": round(vm.percent,1),
           "temp": primary_temp, "core_temps": core_temps,
           "cores": [round(c,1) for c in cores] if cores else None}
    top_procs = []
    for p in procs:
        try:
            top_procs.append({"name": (p.info.get("name") or "?")[:24],
                               "cpu": round(p.cpu_percent(None) / NCPU, 1),
                               "mem": round(p.memory_percent(), 1)})
        except Exception:
            continue
    row["top_procs"] = sorted(top_procs, key=lambda x: x["cpu"], reverse=True)[:5]
    try:
        f=psutil.cpu_freq(); row["freq"]=round(f.current) if f else None
    except Exception: pass
    return {k:v for k,v in row.items() if v is not None}

def push_live(row):
    _req("live?on_conflict=machine", "POST", row,
         {"Prefer": "resolution=merge-duplicates,return=minimal"})

def live_loop():
    interval = float(CFG.get("LIVE_INTERVAL_SEC") or 2)
    print(f"SysDash LIVE %s elke %ss" % (MACHINE, interval), file=sys.stderr)
    while True:
        t0=time.time()
        try: push_live(collect_live())
        except Exception as e: print("[live-fout] %s" % e, file=sys.stderr)
        time.sleep(max(0.2, interval-(time.time()-t0)))

def one_cycle(dry):
    row = collect()
    if dry:
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return True
    try:
        touch_machine(); push_hardware_if_changed(); push(row)
        print(f"[{time.strftime('%H:%M:%S')}] gepusht: cpu={row.get('cpu')}% mem={row.get('mem')}% temp={row.get('temp')} machine={MACHINE}")
        return True
    except urllib.error.HTTPError as e:
        print(f"[fout] Supabase weigerde ({e.code}): {e.read().decode()[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[fout] push mislukt: {e}", file=sys.stderr)
    return False

def main():
    if "--live" in sys.argv:
        live_loop(); return
    dry = "--dry-run" in sys.argv
    once = "--once" in sys.argv or dry
    if not dry and (not SUPABASE_URL or not SERVICE_KEY):
        sys.exit("SUPABASE_URL en SUPABASE_SERVICE_KEY ontbreken (.env). Gebruik --dry-run om te testen.")
    print(f"SysDash agent · machine={MACHINE} · interval={INTERVAL}s · {'DRY-RUN' if dry else 'push naar '+SUPABASE_URL}", file=sys.stderr)
    if once:
        one_cycle(dry); return
    while True:
        t0 = time.time()
        one_cycle(False)
        time.sleep(max(1, INTERVAL - (time.time() - t0)))

if __name__ == "__main__":
    main()
