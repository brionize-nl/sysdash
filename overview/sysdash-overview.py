#!/usr/bin/env python3
"""SysDash 2x-daags overzicht → Discord. Haalt v_latest op, maakt nette samenvatting."""
import os, sys, json, urllib.request, time

URL  = os.environ.get("SUPABASE_URL", "")
ANON = os.environ.get("SUPABASE_ANON_KEY", "")
HOOK = os.environ.get("DISCORD_WEBHOOK", "")

def supa(path):
    req = urllib.request.Request(URL.rstrip("/") + "/rest/v1/" + path,
        headers={"apikey": ANON, "Authorization": "Bearer " + ANON})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def human_uptime(sec):
    if not sec: return "?"
    d, rem = divmod(int(sec), 86400); h = rem // 3600
    return f"{d}d{h}u" if d else f"{h}u"

def label_of(machine, labels):
    return labels.get(machine, machine)

def status_of(r):
    """kort oordeel: alarmen / aandachtspunten."""
    alarms, notes = [], []
    disk=r.get("disk") or 0; temp=r.get("temp") or 0; mem=r.get("mem") or 0
    swap=r.get("swap") or 0; bat=r.get("battery"); health=r.get("bat_health")
    l15=r.get("load15") or 0; cores=len(r.get("cores") or [1])
    if disk>=90: alarms.append(f"schijf {round(disk)}%")
    elif disk>=75: notes.append(f"schijf {round(disk)}%")
    if temp>=90: alarms.append(f"{round(temp)}\u00b0")
    elif temp>=80: notes.append(f"{round(temp)}\u00b0")
    if mem>=95: alarms.append(f"RAM {round(mem)}%")
    elif mem>=85: notes.append(f"RAM {round(mem)}%")
    if swap>=50: alarms.append(f"swap {round(swap)}%")
    elif swap>=10: notes.append(f"swap {round(swap)}%")
    if l15>cores: notes.append(f"load {l15:.1f}")
    if r.get("net_up") is False: alarms.append("internet weg")
    if (r.get("extra") or {}).get("reboot_required"): notes.append("herstart nodig")
    if bat is not None and not r.get("bat_plugged") and bat<15: alarms.append(f"accu {round(bat)}%")
    if health is not None and 0<health<50: notes.append(f"accu-conditie {round(health)}%")
    return alarms, notes

def fmt_bytes(b):
    if b is None: return "?"
    b=float(b)
    for u in ["B","KB","MB","GB"]:
        if b<1024: return f"{b:.0f}{u}/s"
        b/=1024
    return f"{b:.0f}TB/s"

def machine_block(r, lab):
    alarms, notes = status_of(r)
    if alarms: head = f"\u25B2 {len(alarms)} alarm: " + ", ".join(alarms)
    elif notes: head = f"\u26A0 {len(notes)} aandachtspunt" + ("en" if len(notes)>1 else "") + ": " + ", ".join(notes)
    else: head = "\u2713 alles OK"
    is_laptop = r.get("battery") is not None
    L = []
    L.append(f"**{lab}**  {head}")
    # belasting
    L.append(f"Belasting: CPU {round(r.get('cpu') or 0)}% \u00b7 RAM {round(r.get('mem') or 0)}% \u00b7 Swap {round(r.get('swap') or 0)}% \u00b7 Schijf {round(r.get('disk') or 0)}%")
    l1,l5,l15 = r.get('load1'),r.get('load5'),r.get('load15')
    cores = r.get('cores') or []
    coremax = f" \u00b7 core piek {round(max(cores))}%" if cores else ""
    L.append(f"  load {l1}/{l5}/{l15}{coremax}")
    # temp + fan
    ctemps = r.get('core_temps') or []
    tpiek = f" (core piek {round(max(ctemps))}\u00b0)" if ctemps else ""
    fans = r.get('fans') or {}
    fanstr = ""
    if fans:
        fv = list(fans.values())[0]
        fanstr = f" \u00b7 fan {fv} rpm" if fv else " \u00b7 fan uit"
    L.append(f"Temp: {round(r.get('temp') or 0)}\u00b0{tpiek}{fanstr}")
    # accu (alleen laptop)
    if is_laptop:
        plug = "aan stroom" if r.get('bat_plugged') else "op accu"
        h = r.get('bat_health')
        hstr = f" \u00b7 conditie {round(h)}%" if h is not None else ""
        L.append(f"Accu: {round(r.get('battery') or 0)}% ({plug}){hstr}")
    # netwerk
    net = "online" if r.get('net_up') else "OFFLINE"
    L.append(f"Netwerk: \u2193{fmt_bytes(r.get('net_rx'))} \u2191{fmt_bytes(r.get('net_tx'))} \u00b7 {net}")
    # systeem
    ex = r.get('extra') or {}
    ul = ex.get('updates_list') or []
    nrood = sum(1 for u in ul if isinstance(u,dict) and u.get('risk')=='rood')
    updstr = f"{r.get('updates') or 0} updates" + (f" ({nrood} rood)" if nrood else "")
    reboot = "JA" if ex.get('reboot_required') else "nee"
    L.append(f"Systeem: uptime {human_uptime(r.get('uptime'))} \u00b7 {updstr} \u00b7 herstart: {reboot}")
    hw = ex.get('hardware') or {}
    if hw.get('cpu'):
        L.append(f"  {hw.get('cpu','')} \u00b7 {hw.get('ram_str','')} \u00b7 {hw.get('disk','')}")
    return "\n".join(L)

def peak_detail(machine):
    """Analyseer de CPU-piek van de afgelopen 12u: veroorzaker (zwaarste proces) + hoe lang de piek aanhield."""
    import datetime
    now = datetime.datetime.utcnow()
    since = (now - datetime.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        rows = supa(f"metrics?machine=eq.{machine}&ts=gte.{since}&select=ts,cpu,top_procs&order=ts.asc")
    except Exception:
        rows = []
    if not rows:
        return {}
    # piek + index
    peak_i, peak_v = -1, -1
    for i, r in enumerate(rows):
        c = r.get("cpu")
        if c is not None and c > peak_v:
            peak_v, peak_i = c, i
    if peak_i < 0:
        return {}
    peak_row = rows[peak_i]
    # veroorzaker: zwaarste proces op het piek-moment
    culprit = ""
    procs = peak_row.get("top_procs") or []
    if procs:
        top = max(procs, key=lambda p: p.get("cpu", 0))
        culprit = top.get("name", "")
    # duur: tel opeenvolgende metingen rond de piek die boven een drempel (helft van piek, min 50%) zaten
    thr = max(50, peak_v * 0.6)
    lo = hi = peak_i
    while lo-1 >= 0 and (rows[lo-1].get("cpu") or 0) >= thr: lo -= 1
    while hi+1 < len(rows) and (rows[hi+1].get("cpu") or 0) >= thr: hi += 1
    # tijdsduur schatten uit timestamps
    def ts_of(r):
        try: return datetime.datetime.fromisoformat(r["ts"].replace("Z","").split("+")[0])
        except Exception: return None
    t_lo, t_hi = ts_of(rows[lo]), ts_of(rows[hi])
    dur_min = None
    if t_lo and t_hi:
        dur_min = round((t_hi - t_lo).total_seconds() / 60)
    return {"peak": peak_v, "culprit": culprit, "dur_min": dur_min, "thr": round(thr)}

def blocks_12h(machine):
    """Verdeel de afgelopen 12u in 6 blokken van 2u; per blok gem van cpu/mem/temp."""
    import datetime
    now = datetime.datetime.utcnow()
    since = (now - datetime.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        rows = supa(f"metrics?machine=eq.{machine}&ts=gte.{since}&select=ts,cpu,mem,temp&order=ts.asc")
    except Exception:
        rows = []
    # 6 buckets van 2u
    buckets = [[] for _ in range(6)]
    start = now - datetime.timedelta(hours=12)
    for r in rows:
        try:
            t = datetime.datetime.fromisoformat(r["ts"].replace("Z","").split("+")[0])
        except Exception:
            continue
        idx = int((t - start).total_seconds() // 7200)
        if 0 <= idx < 6: buckets[idx].append(r)
    def avg(bs, key):
        vals = [b[key] for b in bs if b.get(key) is not None]
        return (sum(vals)/len(vals)) if vals else None
    labels = []
    for i in range(6):
        h = (start + datetime.timedelta(hours=2*i)).hour
        labels.append(f"{h:02d}")
    def realmax(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return max(vals) if vals else None
    return {
        "labels": labels,
        "cpu": [avg(b,"cpu") for b in buckets],
        "mem": [avg(b,"mem") for b in buckets],
        "temp": [avg(b,"temp") for b in buckets],
        "cpu_max": realmax("cpu"),
        "mem_max": realmax("mem"),
        "temp_max": realmax("temp"),
        "n": len(rows),
    }

def main():
    rows = supa("v_latest?select=*")
    labels = {m['machine']: m.get('label') or m['machine'] for m in supa("machines?select=machine,label")}
    # verrijk elke rij met 2u-aggregaten
    for r in rows:
        r["_blocks"] = blocks_12h(r["machine"])
        r["_peak"] = peak_detail(r["machine"])
    tod = time.strftime("%H:%M")
    dagdeel = "ochtend" if int(time.strftime("%H"))<15 else "avond"
    import importlib.util, subprocess, os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("tpl", _os.path.join(here, "overview-template.py"))
    tpl = importlib.util.module_from_spec(spec); spec.loader.exec_module(tpl)
    printonly = "--print" in sys.argv or not HOOK
    for r in rows:
        lab = labels.get(r["machine"], r["machine"])
        html = tpl.build_html_single(r, lab, "%s \u00b7 %s" % (dagdeel, tod))
        html_path = "/tmp/sysdash-ov-%s.html" % r["machine"]
        png_path  = "/tmp/sysdash-ov-%s.png" % r["machine"]
        open(html_path,"w").write(html)
        render = (
            "from playwright.sync_api import sync_playwright\n"
            "with sync_playwright() as p:\n"
            "    b=p.chromium.launch(args=[\"--no-sandbox\"]); pg=b.new_page(viewport={\"width\":520,\"height\":100},device_scale_factor=2)\n"
            "    pg.goto(\"file://%s\"); pg.wait_for_timeout(700)\n"
            "    h=pg.evaluate(\"document.body.scrollHeight\"); pg.set_viewport_size({\"width\":520,\"height\":h}); pg.wait_for_timeout(200)\n"
            "    pg.screenshot(path=\"%s\", full_page=True); b.close()\n"
        ) % (html_path, png_path)
        subprocess.run([sys.executable,"-c",render], check=True, timeout=90)
        if printonly:
            print("gerenderd:", png_path); continue
        content = "\U0001F4CA %s \u00b7 %s %s" % (lab, dagdeel, tod)
        payload = json.dumps({"username":"SysDash","content":content})
        subprocess.run(["curl","-s","-o","/dev/null","-F","payload_json="+payload,
            "-F","file=@"+png_path+";type=image/png;filename=sysdash.png",HOOK], check=True, timeout=30)
        print("verstuurd: %s" % lab)

if __name__ == "__main__":
    main()
