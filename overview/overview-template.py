def sparkline(vals, labels, title, unit, warn, alarm):
    """6 balkjes in SysDash-stijl; kleur per waarde (kleurenblind: hoogte+kleur+cijfer)."""
    bars = ""
    maxv = max([v for v in vals if v is not None] + [1])
    scale = max(maxv, alarm)  # zodat alarm-niveau referentie is
    for v, lab in zip(vals, labels):
        if v is None:
            bars += f'<div class="bar"><div class="barfill empty" style="height:2px"></div><div class="barval">-</div><div class="barlab">{lab}</div></div>'
            continue
        col = "#ff5a5a" if v>=alarm else ("#f0b43c" if v>=warn else "#22e39a")
        h = max(4, round(v/scale*64))
        bars += f'<div class="bar"><div class="barfill" style="height:{h}px;background:{col};box-shadow:0 0 5px {col}"></div><div class="barval">{round(v)}</div><div class="barlab">{lab}</div></div>'
    return f'<div class="spark"><div class="sparktitle">{title} <span class="sparkunit">laatste 12u · per 2u</span></div><div class="bars">{bars}</div></div>'

"""Bouwt een SysDash-gestyled HTML-overzicht dat naar een plaatje gerenderd wordt."""

def ring_svg(val, label, sub, status, peak=None, limit=None):
    # kleurenblind-veilig: kleur + tekst. status: ok/warn/high.
    # peak: % waar de piek zat (rood streepje). limit: grens-% (amber driehoekje).
    col = {"ok":"#22e39a","warn":"#f0b43c","high":"#ff5a5a"}.get(status,"#22e39a")
    import math
    v = max(0, min(100, val or 0))
    start, sweep = 130, 280
    def pt(ang, radius=42):
        a = math.radians(ang); return 60+radius*math.cos(a), 60+radius*math.sin(a)
    x0,y0 = pt(start); x1,y1 = pt(start+sweep*v/100)
    large = 1 if sweep*v/100>180 else 0
    xt0,yt0=pt(start); xt1,yt1=pt(start+sweep)
    larget = 1 if sweep>180 else 0
    marks = ""
    # piek-streepje (rood radiaal lijntje) — voor CPU/RAM
    if peak is not None and peak > v + 3:
        pk = max(0, min(100, peak)); ang = start + sweep*pk/100
        ix,iy = pt(ang, 31); ox,oy = pt(ang, 53)
        marks += f'<line x1="{ix:.1f}" y1="{iy:.1f}" x2="{ox:.1f}" y2="{oy:.1f}" stroke="#ff3b3b" stroke-width="5.5" stroke-linecap="round" style="filter:drop-shadow(0 0 5px #ff3b3b)"/>'
    # grens-markering (amber driehoekje aan de buitenrand) — voor schijf
    if limit is not None:
        lm = max(0, min(100, limit)); ang = start + sweep*lm/100
        tx,ty = pt(ang, 52)
        a = math.radians(ang)
        # klein driehoekje wijzend naar binnen
        p1=(tx,ty); p2=(tx-4*math.cos(a-0.5),ty-4*math.sin(a-0.5)); p3=(tx-4*math.cos(a+0.5),ty-4*math.sin(a+0.5))
        marks += f'<polygon points="{p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}" fill="#f0b43c" style="filter:drop-shadow(0 0 2px #f0b43c)"/>'
    return f'''<div class="ring">
      <svg viewBox="0 0 120 120">
        <path d="M {xt0:.1f} {yt0:.1f} A 42 42 0 {larget} 1 {xt1:.1f} {yt1:.1f}" fill="none" stroke="#1a2b3d" stroke-width="9" stroke-linecap="round"/>
        <path d="M {x0:.1f} {y0:.1f} A 42 42 0 {large} 1 {x1:.1f} {y1:.1f}" fill="none" stroke="{col}" stroke-width="9" stroke-linecap="round" style="filter:drop-shadow(0 0 4px {col})"/>
        {marks}
        <text x="60" y="58" text-anchor="middle" fill="{col}" font-size="30" font-family="Arial" font-weight="bold">{round(v)}</text>
        <text x="60" y="74" text-anchor="middle" fill="#5a7a95" font-size="11">%</text>
      </svg>
      <div class="rlab">{label}</div>
      <div class="rsub">{sub.replace(chr(10),"<br>")}</div>
    </div>'''

def stt(v, warn, alarm):
    v = v or 0
    return "high" if v>=alarm else ("warn" if v>=warn else "ok")

def machine_card(r, lab):
    is_laptop = r.get("battery") is not None
    ex = r.get("extra") or {}
    hw = ex.get("hardware") or {}
    # status
    alarms, notes = [], []
    disk=r.get("disk") or 0; temp=r.get("temp") or 0; mem=r.get("mem") or 0
    if disk>=90: alarms.append(f"schijf {round(disk)}%")
    elif disk>=75: notes.append(f"schijf {round(disk)}%")
    if temp>=80: notes.append(f"{round(temp)}\u00b0")
    if mem>=85: notes.append(f"RAM {round(mem)}%")
    h=r.get("bat_health")
    if h is not None and 0<h<50: notes.append(f"accu {round(h)}%")
    if ex.get("reboot_required"): notes.append("herstart nodig")
    if alarms: badge=f'<span class="badge high">\u25B2 {", ".join(alarms)}</span>'
    elif notes: badge=f'<span class="badge warn">\u26A0 {", ".join(notes)}</span>'
    else: badge='<span class="badge ok">\u2713 alles OK</span>'
    # ringen
    blk_agg = r.get("_blocks") or {}
    ramTot = hw.get("ram_gb")
    if ramTot:
        _rv = [v for v in (blk_agg.get("mem") or []) if v is not None]
        now_gb = mem/100*ramTot
        if _rv:
            _gempct = sum(_rv)/len(_rv)
            _mx = blk_agg.get("mem_max")
            _pkpct = _mx if _mx is not None else max(_rv)
            ramSub = f"nu {now_gb:.0f} · gem {(_gempct/100*ramTot):.0f} · piek {(_pkpct/100*ramTot):.0f} GB"
        else:
            ramSub = f"{now_gb:.0f} / {ramTot} GB"
    else:
        ramSub = ""
    disks = r.get("disks") or []
    root = next((d for d in disks if d.get("mount")=="/"), disks[0] if disks else None)
    diskSub = f"{(root['pct']/100*root['gb']):.0f} / {root['gb']} GB" if root and root.get("gb") else ""
    blk_agg2 = r.get("_blocks") or {}
    def gp(key, unit):
        vals = [v for v in (blk_agg.get(key) or []) if v is not None]
        if not vals: return ""
        return f"gem {round(sum(vals)/len(vals))}{unit} · piek {round(max(vals))}{unit}"
    cpu_peak = blk_agg.get("cpu_max")
    mem_peak = blk_agg.get("mem_max")
    def gp2(key, unit, nowval):
        vals = [v for v in (blk_agg.get(key) or []) if v is not None]
        parts = [f"nu {round(nowval)}{unit}"] if nowval is not None else []
        if vals:
            gem = round(sum(vals)/len(vals))
            mx = blk_agg.get(key+"_max")
            pk = round(mx) if mx is not None else round(max(vals))
            parts += [f"gem {gem}{unit}", f"piek {pk}{unit}"]
        return " \u00b7 ".join(parts)
    cpuSub = gp2("cpu","%", r.get("cpu"))
    pk = r.get("_peak") or {}
    if pk.get("culprit"):
        extra = pk["culprit"]
        if pk.get("dur_min") is not None:
            extra += f" · {pk['dur_min']}min" if pk['dur_min']>0 else " · kort"
        cpuSub += f"\n\u2937 {extra}"
    rings = (ring_svg(r.get("cpu"),"CPU",cpuSub,stt(r.get("cpu"),75,90),peak=cpu_peak) +
             ring_svg(r.get("mem"),"RAM",ramSub,stt(mem,75,90),peak=mem_peak) +
             ring_svg(r.get("disk"),"SCHIJF",diskSub,stt(disk,75,90),limit=85))
    # extra regels
    def uphuman(s):
        if not s: return "?"
        d,rem=divmod(int(s),86400); h=rem//3600; return f"{d}d {h}u" if d else f"{h}u"
    ul = ex.get("updates_list") or []
    nrood = sum(1 for u in ul if isinstance(u,dict) and u.get("risk")=="rood")
    updstr = f"{r.get('updates') or 0}" + (f" ({nrood}\u25B2)" if nrood else "")
    accu = ""
    if is_laptop:
        plug="\u26A1" if r.get("bat_plugged") else "\U0001F50B"
        accu = f'<div class="stat"><span>ACCU</span><b>{round(r.get("battery") or 0)}% {plug} \u00b7 cond {round(h) if h else "?"}%</b></div>'
    ct = r.get("core_temps") or []
    tmax = blk_agg.get("temp_max")
    tsub = f" (piek {round(tmax)}\u00b0)" if tmax is not None else (f" (piek {round(max(ct))}\u00b0)" if ct else "")
    blk = r.get("_blocks") or {}
    labs = blk.get("labels") or ["","","","","",""]
    sparks = ""
    if blk.get("n"):
        sparks = (sparkline(blk.get("cpu") or [], labs, "CPU", "%", 75, 90) +
                  sparkline(blk.get("mem") or [], labs, "RAM", "%", 75, 90) +
                  sparkline(blk.get("temp") or [], labs, "TEMP", "\u00b0", 70, 85))
    return f'''<div class="card">
      <div class="chead"><span class="cname">{lab}</span>{badge}</div>
      <div class="rings">{rings}</div>
      {sparks}
      <div class="stats">
        <div class="stat"><span>TEMP</span><b>{gp("temp","\u00b0") or (str(round(temp))+"\u00b0")}</b></div>
        <div class="stat"><span>LOAD</span><b>{r.get("load1")} / {r.get("load5")} / {r.get("load15")}</b></div>
        {accu}
        <div class="stat"><span>UPTIME</span><b>{uphuman(r.get("uptime"))}</b></div>
        <div class="stat"><span>UPDATES</span><b>{updstr}</b></div>
        <div class="stat"><span>HERSTART</span><b>{"JA" if ex.get("reboot_required") else "nee"}</b></div>
      </div>
      <div class="hw">{hw.get("cpu","")} \u00b7 {hw.get("ram_str","")} \u00b7 {hw.get("disk","")}</div>
    </div>'''

def build_html(rows, labels, when):
    cards = "".join(machine_card(r, labels.get(r["machine"], r["machine"])) for r in rows)
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box;font-family:Arial,sans-serif}}
    body{{background:#070f18;color:#cfe3f5;padding:28px;width:900px}}
    .top{{display:flex;align-items:center;gap:10px;margin-bottom:18px}}
    .logo{{width:26px;height:26px}}
    .title{{font-size:26px;font-weight:bold;letter-spacing:4px;color:#dff}}
    .sub{{font-size:11px;color:#5a7a95;letter-spacing:2px}}
    .when{{margin-left:auto;font-size:13px;color:#00d4ff;font-family:monospace}}
    .card{{background:linear-gradient(160deg,rgba(16,30,46,.6),rgba(10,18,28,.4));border:1px solid rgba(90,140,190,.18);border-radius:16px;padding:20px 22px;margin-bottom:18px}}
    .chead{{display:flex;align-items:center;gap:12px;margin-bottom:12px}}
    .cname{{font-size:20px;font-weight:bold;letter-spacing:2px;color:#dff}}
    .badge{{font-size:13px;padding:4px 11px;border-radius:7px;font-family:monospace}}
    .badge.ok{{color:#22e39a;border:1px solid rgba(34,227,154,.4);background:rgba(34,227,154,.08)}}
    .badge.warn{{color:#f0b43c;border:1px solid rgba(240,180,60,.4);background:rgba(240,180,60,.08)}}
    .badge.high{{color:#ff5a5a;border:1px solid rgba(255,90,90,.4);background:rgba(255,90,90,.08)}}
    .rings{{display:flex;gap:6px;justify-content:space-between;margin-bottom:16px}}
    .ring{{text-align:center;flex:1}}
    .ring svg{{width:140px;height:140px}}
    .rlab{{font-size:14px;letter-spacing:2px;color:#8fb0cc;margin-top:0}}
    .rsub{{font-size:12px;color:#7a9ab5;font-family:monospace;margin-top:3px}}
    .stats{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px 22px;margin-bottom:14px}}
    .stat{{display:flex;justify-content:space-between;gap:8px;font-size:16px;border-bottom:1px solid rgba(90,140,190,.12);padding:8px 0}}
    .stat span{{color:#7a9ab5;letter-spacing:1px}}
    .stat b{{color:#eaf4ff;font-family:monospace;font-weight:normal}}
    .spark{{margin:6px 0 10px}}
    .sparktitle{{font-size:14px;letter-spacing:1px;color:#a5c2dc;margin-bottom:7px}}
    .sparkunit{{color:#5a7a95;font-size:11px;letter-spacing:0}}
    .bars{{display:flex;gap:10px;align-items:flex-end;height:84px}}
    .bar{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end}}
    .barfill{{width:100%;border-radius:3px 3px 0 0;min-height:2px}}
    .barfill.empty{{background:#1a2b3d}}
    .barval{{font-size:13px;color:#b5d0e8;font-family:monospace;margin-top:4px}}
    .barlab{{font-size:11px;color:#5a7a95;font-family:monospace;margin-top:2px}}
    .hw{{font-size:12px;color:#7a9ab5;font-family:monospace;border-top:1px solid rgba(90,140,190,.14);padding-top:10px}}
    </style></head><body>
    <div class="top">
      <svg class="logo" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2-7 4 14 2-7h6"/></svg>
      <div><div class="title">SYSDASH</div><div class="sub">MISSION CONTROL</div></div>
      <div class="when">{when}</div>
    </div>
    {cards}
    </body></html>'''

def build_html_single(r, lab, when):
    """Eén machine, smal canvas (520px) met GROTE tekst voor telefoon-leesbaarheid."""
    card = machine_card(r, lab)
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box;font-family:Arial,sans-serif}}
    body{{background:#070f18;color:#cfe3f5;padding:22px;width:520px}}
    .top{{display:flex;align-items:center;gap:10px;margin-bottom:16px}}
    .logo{{width:30px;height:30px}}
    .title{{font-size:26px;font-weight:bold;letter-spacing:3px;color:#dff}}
    .sub{{font-size:13px;color:#5a7a95;letter-spacing:2px}}
    .when{{margin-left:auto;font-size:16px;color:#00d4ff;font-family:monospace}}
    .card{{background:linear-gradient(160deg,rgba(16,30,46,.6),rgba(10,18,28,.4));border:1px solid rgba(90,140,190,.18);border-radius:16px;padding:22px 24px}}
    .chead{{display:flex;align-items:center;gap:12px;margin-bottom:16px}}
    .cname{{font-size:26px;font-weight:bold;letter-spacing:2px;color:#dff}}
    .badge{{font-size:16px;padding:5px 13px;border-radius:8px;font-family:monospace}}
    .badge.ok{{color:#22e39a;border:1px solid rgba(34,227,154,.4);background:rgba(34,227,154,.08)}}
    .badge.warn{{color:#f0b43c;border:1px solid rgba(240,180,60,.4);background:rgba(240,180,60,.08)}}
    .badge.high{{color:#ff5a5a;border:1px solid rgba(255,90,90,.4);background:rgba(255,90,90,.08)}}
    .rings{{display:flex;gap:6px;justify-content:space-between;margin-bottom:18px}}
    .ring{{text-align:center;flex:1}}
    .ring svg{{width:150px;height:150px}}
    .rlab{{font-size:17px;letter-spacing:2px;color:#9fbdd8;margin-top:2px}}
    .rsub{{font-size:15px;color:#7a9ab5;font-family:monospace;margin-top:4px}}
    .spark{{margin:10px 0 14px}}
    .sparktitle{{font-size:18px;letter-spacing:1px;color:#a5c2dc;margin-bottom:9px}}
    .sparkunit{{color:#5a7a95;font-size:14px}}
    .bars{{display:flex;gap:10px;align-items:flex-end;height:96px}}
    .bar{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end}}
    .barfill{{width:100%;border-radius:4px 4px 0 0;min-height:3px}}
    .barfill.empty{{background:#1a2b3d}}
    .barval{{font-size:17px;color:#c5daf0;font-family:monospace;margin-top:5px;font-weight:bold}}
    .barlab{{font-size:14px;color:#6a8aa0;font-family:monospace;margin-top:2px}}
    .stats{{display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-bottom:16px}}
    .stat{{display:flex;justify-content:space-between;gap:10px;font-size:19px;border-bottom:1px solid rgba(90,140,190,.14);padding:10px 0}}
    .stat span{{color:#7a9ab5;letter-spacing:1px}}
    .stat b{{color:#eaf4ff;font-family:monospace;font-weight:normal}}
    .hw{{font-size:14px;color:#7a9ab5;font-family:monospace;border-top:1px solid rgba(90,140,190,.14);padding-top:12px;line-height:1.5}}
    </style></head><body>
    <div class="top">
      <svg class="logo" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2-7 4 14 2-7h6"/></svg>
      <div><div class="title">SYSDASH</div><div class="sub">MISSION CONTROL</div></div>
      <div class="when">{when}</div>
    </div>
    {card}
    </body></html>'''
