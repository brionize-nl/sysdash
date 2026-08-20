#!/usr/bin/env python3
"""
SysDash v12 · render-service
HUD-kaart (SVG→PNG) voor Discord. Neemt een 'spec' en levert een PNG.
Endpoints:
  GET  /health          → {"status":"ok"}
  GET  /demo            → voorbeeldkaart (PNG)
  POST /card  (JSON spec) → PNG
Bindt op 127.0.0.1 (alleen lokaal; n8n draait op dezelfde machine).
Vereist: cairosvg  +  Orbitron-font (installer regelt beide).
"""
import sys, json, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape
try:
    import cairosvg
except ImportError:
    sys.exit("cairosvg ontbreekt — installeer: pip3 install cairosvg")

HOST, PORT = "127.0.0.1", 7071
BG = "#020810"

# ─────────────────────── HUD-kaart (getest, goedgekeurd) ───────────────────────
def build_svg(spec):
    TRACK = "#0e2a44"
    CYAN, GREEN, YELLOW, RED = "#00d4ff", "#00ff9d", "#ffc300", "#ff3d5a"
    TXT, MUTED = "#c8e0f4", "#6b8bad"
    HUD, DATA = "Orbitron, DejaVu Sans, sans-serif", "DejaVu Sans, sans-serif"
    SCOL = {"ok": GREEN, "warn": YELLOW, "high": RED}
    SWORD = {"ok": "OK", "warn": "LET OP", "high": "HOOG"}
    esc = lambda s: escape(str(s))
    def pt(cx, cy, r, d):
        a = math.radians(d); return (cx + r*math.cos(a), cy + r*math.sin(a))
    def arc(cx, cy, r, s, sw):
        x0, y0 = pt(cx, cy, r, s); x1, y1 = pt(cx, cy, r, s+sw)
        return "M %.2f %.2f A %d %d 0 %d 1 %.2f %.2f" % (x0, y0, r, r, 1 if sw > 180 else 0, x1, y1)

    title = spec.get("title", "SysDash"); subtitle = spec.get("subtitle", "")
    state = spec.get("state", "ok"); rows = spec.get("rows", []) or []; footer = spec.get("footer", "SysDash")
    tclean = title
    while tclean and not tclean[0].isalnum(): tclean = tclean[1:]
    tclean = tclean.strip()
    accent = RED if state == "alert" else CYAN

    pctrows = [r for r in rows if r.get("pct") is not None]
    if len(pctrows) >= 3:
        rings = pctrows[:3]; ringids = set(id(r) for r in rings)
        detail = [r for r in rows if id(r) not in ringids]
    else:
        rings = []; detail = rows

    W, PAD, header_h, row_h, footer_h = 680, 26, 78, 32, 44
    ring_h = 172 if rings else 0
    rows_h = (len(detail) * row_h + 20) if detail else 0
    H = header_h + ring_h + rows_h + footer_h

    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H)]
    p.append('<rect width="%d" height="%d" rx="16" fill="%s"/>' % (W, H, BG))
    p.append('<rect x="1" y="1" width="%d" height="%d" rx="15" fill="none" stroke="%s" stroke-opacity="0.18"/>' % (W-2, H-2, accent))
    p.append('<rect width="%d" height="4" rx="2" fill="%s" fill-opacity="0.9"/>' % (W, accent))
    p.append('<rect x="%d" y="26" width="27" height="27" rx="7" fill="%s" fill-opacity="0.14" stroke="%s" stroke-opacity="0.55"/>' % (PAD, CYAN, CYAN))
    p.append('<polyline points="31,39.5 35,39.5 38,31 42,48 45,39.5 49,39.5" fill="none" stroke="%s" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>' % CYAN)
    p.append('<text x="64" y="40" font-size="17" font-weight="800" fill="%s" letter-spacing="5" font-family="%s">SYSDASH</text>' % (TXT, HUD))
    p.append('<text x="64" y="57" font-size="10" fill="%s" letter-spacing="1" font-family="%s">%s</text>' % (MUTED, DATA, esc(tclean.upper())))
    if subtitle:
        p.append('<text x="%d" y="40" font-size="13" font-weight="700" fill="%s" text-anchor="end" letter-spacing="1" font-family="%s">%s</text>' % (W-PAD, accent, DATA, esc(subtitle)))
    p.append('<line x1="%d" y1="78" x2="%d" y2="78" stroke="%s" stroke-opacity="0.10"/>' % (PAD, W-PAD, CYAN))

    y0 = header_h
    if rings:
        n = len(rings)
        for i, r in enumerate(rings):
            cx = int(W * (i + 1) / (n + 1)); cy = y0 + 74
            try: val = max(0.0, min(100.0, float(r.get("pct"))))
            except Exception: val = 0.0
            col = SCOL.get(r.get("status", "ok"), GREEN); sw = max(0.5, 280*val/100.0)
            p.append('<path d="%s" fill="none" stroke="%s" stroke-width="7" stroke-linecap="round"/>' % (arc(cx, cy, 44, 130, 280), TRACK))
            p.append('<path d="%s" fill="none" stroke="%s" stroke-width="7" stroke-linecap="round"/>' % (arc(cx, cy, 44, 130, sw), col))
            p.append('<text x="%d" y="%d" font-size="27" font-weight="700" fill="%s" text-anchor="middle" font-family="%s">%d</text>' % (cx, cy+5, col, HUD, round(val)))
            p.append('<text x="%d" y="%d" font-size="9" fill="%s" text-anchor="middle" font-family="%s">%%</text>' % (cx, cy+21, MUTED, HUD))
            p.append('<text x="%d" y="%d" font-size="10" fill="%s" text-anchor="middle" letter-spacing="2" font-family="%s">%s</text>' % (cx, cy+54, MUTED, HUD, esc(r.get("label", ""))))
        p.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-opacity="0.10"/>' % (PAD, y0+ring_h-4, W-PAD, y0+ring_h-4, CYAN))

    ry = y0 + ring_h + 24; sx = W - 118
    for r in detail:
        st = r.get("status", "ok"); col = SCOL.get(st, GREEN); word = SWORD.get(st, "OK"); icy = ry - 4
        p.append('<text x="40" y="%d" font-size="11" fill="%s" letter-spacing="1.5" font-family="%s">%s</text>' % (ry, MUTED, HUD, esc(r.get("label", ""))))
        p.append('<text x="140" y="%d" font-size="13" fill="%s" font-family="%s">%s</text>' % (ry, TXT, DATA, esc(r.get("value", ""))))
        if st == "ok":
            p.append('<path d="M%d %d l3 3 l7 -9" fill="none" stroke="%s" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>' % (sx, icy, GREEN))
        elif st == "warn":
            p.append('<circle cx="%d" cy="%d" r="4.5" fill="%s"/>' % (sx+5, icy-1, YELLOW))
        else:
            p.append('<path d="M%d %d l6 10 l-12 0 z" fill="%s"/>' % (sx+5, icy-9, RED))
        p.append('<text x="%d" y="%d" font-size="11" fill="%s" letter-spacing="1" font-family="%s">%s</text>' % (sx+18, ry, col, HUD, word))
        ry += row_h

    p.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-opacity="0.10"/>' % (PAD, H-40, W-PAD, H-40, CYAN))
    p.append('<text x="40" y="%d" font-size="9" fill="%s" letter-spacing="1" font-family="%s">%s</text>' % (H-20, MUTED, DATA, esc(footer)))
    p.append('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (W-40, H-24, GREEN if state != "alert" else RED))
    p.append('</svg>')
    return "".join(p)

def render_png(spec):
    return cairosvg.svg2png(bytestring=build_svg(spec).encode(), scale=2, background_color=BG)

DEMO = {"title": "\u2713 Health report \u2014 laptop", "subtitle": "nu", "state": "ok",
        "footer": "SysDash \u00b7 demo", "rows": [
            {"label": "CPU", "value": "8%", "pct": 8, "status": "ok"},
            {"label": "RAM", "value": "45%", "pct": 45, "status": "ok"},
            {"label": "SCHIJF", "value": "76%", "pct": 76, "status": "warn"},
            {"label": "TEMP", "value": "43\u00b0C", "status": "ok"},
            {"label": "UPDATES", "value": "6 klaar", "status": "warn"}]}

# ─────────────────────── HTTP-service ───────────────────────
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code); self.send_header("Content-Type", ctype)
        if ctype == "image/png":
            self.send_header("Content-Disposition", 'inline; filename="card.png"')
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, "application/json", b'{"status":"ok"}')
        elif self.path == "/demo":
            self._send(200, "image/png", render_png(DEMO))
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path != "/card":
            self._send(404, "text/plain", b"not found"); return
        try:
            n = int(self.headers.get("Content-Length", 0))
            spec = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, "image/png", render_png(spec))
        except Exception as e:
            self._send(400, "application/json", json.dumps({"error": str(e)}).encode())

    def log_message(self, *a):  # stil (geen console-spam)
        pass

if __name__ == "__main__":
    print("SysDash render-service op http://%s:%d  (/health /demo /card)" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
