#!/usr/bin/env python3
# SysDash v12 - RECON PROBE. Leest ALLEEN uit, verandert NIETS.
# Draai dit op ELKE machine die je wil monitoren (delli5 EN pro) en plak de uitvoer terug.
# Het vertelt me wat de hardware/omgeving geeft, zodat ik de agent + installer foutloos bouw.
#
#   python3 probe.py
#
import os, sys, glob, socket, subprocess, shutil

def line(): print("-" * 58)
def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception:
        return ""

print("=" * 58)
print("SYSDASH v12 RECON  ·  machine:", socket.gethostname())
print("=" * 58)

# ── Systeem ──
line(); print("[SYSTEEM]")
print("hostname     :", socket.gethostname())
print("os           :", sh("(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)") or sys.platform)
print("kernel       :", sh("uname -r"))
print("python3      :", shutil.which("python3"), "|", sys.version.split()[0])
print("pip3         :", shutil.which("pip3") or "niet gevonden")

# ── psutil ──
line(); print("[PSUTIL]")
try:
    import psutil
    print("psutil       :", psutil.__version__)
    print("cpu cores    :", psutil.cpu_count(logical=False), "fysiek /", psutil.cpu_count(), "threads")
    try:
        f = psutil.cpu_freq(); print("cpu freq     :", f"{f.current:.0f} MHz" if f else "n/b")
    except Exception: print("cpu freq     : n/b")
    vm = psutil.virtual_memory(); print("ram          :", f"{vm.total/1e9:.1f} GB")
    sw = psutil.swap_memory();    print("swap         :", f"{sw.total/1e9:.1f} GB")
except ImportError:
    psutil = None
    print("psutil       : NIET geinstalleerd (installer zet 'm er straks bij)")

# ── Accu ──
line(); print("[ACCU]")
if psutil:
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    print("psutil accu  :", "geen accu (desktop?)" if b is None else f"{b.percent:.0f}% · aan stroom={b.power_plugged}")
else:
    print("psutil accu  : (psutil ontbreekt)")
bat = (sorted(glob.glob("/sys/class/power_supply/BAT*")) or [None])[0]
print("BAT-pad      :", bat or "geen /sys/.../BAT*")
if bat:
    def r(f):
        p = os.path.join(bat, f)
        try: return open(p).read().strip()
        except Exception: return None
    fv = r("charge_full") or r("energy_full"); dv = r("charge_full_design") or r("energy_full_design")
    if fv and dv and int(dv) > 0: print("accu-conditie:", f"{int(fv)*100//int(dv)}%")

# ── Temperatuur-sensoren ──
line(); print("[TEMP-SENSOREN]")
if psutil and hasattr(psutil, "sensors_temperatures"):
    t = psutil.sensors_temperatures() or {}
    if not t: print("(geen sensoren via psutil)")
    for chip, arr in t.items():
        for s in arr:
            nm = f"{chip}/{s.label}" if s.label else chip
            print(f"  {nm:28} {s.current:.0f}°C")
else:
    print("(psutil ontbreekt of geen sensor-ondersteuning)")

# ── Fans (optioneel) ──
if psutil and hasattr(psutil, "sensors_fans"):
    fans = psutil.sensors_fans() or {}
    if fans:
        line(); print("[FANS]")
        for chip, arr in fans.items():
            for s in arr: print(f"  {chip}/{s.label or 'fan'}: {s.current} rpm")

# ── Schijven / mounts ──
line(); print("[SCHIJVEN / MOUNTS]")
if psutil:
    for prt in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(prt.mountpoint)
            print(f"  {prt.mountpoint:18} {u.percent:4.0f}%  ({u.total/1e9:.0f} GB, {prt.fstype})")
        except Exception: pass
else:
    print(sh("df -h --output=target,pcent,size -x tmpfs -x devtmpfs 2>/dev/null | head -8"))

# ── GPU (optioneel) ──
line(); print("[GPU]")
print("nvidia-smi   :", "aanwezig" if shutil.which("nvidia-smi") else "niet gevonden")
print("lspci vga    :", sh("lspci 2>/dev/null | grep -iE 'vga|3d|display' | head -2") or "n/b")

# ── Netwerk / Tailscale ──
line(); print("[NETWERK / TAILSCALE]")
print("tailscale    :", "aanwezig" if shutil.which("tailscale") else "niet gevonden")
print("tailscale ip :", sh("tailscale ip -4 2>/dev/null | head -1") or "n/b")

# ── Git-identiteit (voor de repo's) ──
line(); print("[GIT]")
print("git          :", shutil.which("git") or "niet gevonden")
print("user.name    :", sh("git config --global user.name") or "(niet ingesteld)")
print("user.email   :", sh("git config --global user.email") or "(niet ingesteld)")

# ── Bestaande SysDash-sporen (om niks te overschrijven) ──
line(); print("[BESTAANDE SPOREN]")
for d in ["~/custom-monitor", "~/sysdash-render", "~/sysdash", "~/ycbm-scraper"]:
    p = os.path.expanduser(d)
    print(f"  {d:20} {'bestaat' if os.path.exists(p) else '-'}")

print("=" * 58)
print("KLAAR — plak deze hele uitvoer terug. (En draai 'm ook op je andere machine.)")
print("=" * 58)
