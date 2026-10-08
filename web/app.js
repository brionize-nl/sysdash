/* SysDash v12 · dashboard-brein
   Leest de private hubproxy (alleen lezen), rendert het ontwerp met live data.
   Interactief: machine-tabs, detail-op-tik, historie-schakelaars, auto-refresh.
   Geen data ingesteld? → DEMO-modus (nep-data), zodat je 't kunt bekijken. */
(() => {
"use strict";
const CFG = window.SYSDASH_CONFIG || {};
const DEMO = !CFG.apiBase && (!CFG.url || !CFG.anon);
const RESTARTS = [["restart-web","Dashboard"],["restart-render","Kaarten"],["restart-agent","Meting"],["restart-live","Live-modus"],["restart-tunnel","Externe link"]];
const SECTIONS = ["overzicht", "systeem", "beheer", "historie"];

// swipen tussen tabbladen (22 aug): alleen als de aanraking op de content zelf begint (niet op de
// topbar/machine-tabs/sectie-tabs — die hebben hun eigen tik-gedrag), en duidelijk horizontaal is
// (anders zou verticaal scrollen per ongeluk een tab-wissel triggeren).
let swipeStartX = null, swipeStartY = null;
document.addEventListener("touchstart", (e) => {
  const t = e.target.closest(".panel");
  if (!t) { swipeStartX = null; return; }
  swipeStartX = e.touches[0].clientX; swipeStartY = e.touches[0].clientY;
}, { passive: true });
document.addEventListener("touchend", (e) => {
  if (swipeStartX == null) return;
  const t = e.changedTouches[0];
  const dx = t.clientX - swipeStartX, dy = t.clientY - swipeStartY;
  swipeStartX = null;
  if (Math.abs(dx) < 55 || Math.abs(dx) < Math.abs(dy) * 1.5) return;   // te kort of te verticaal
  const i = SECTIONS.indexOf(STATE.section);
  const next = i + (dx < 0 ? 1 : -1);   // vinger naar links = volgende tab, naar rechts = vorige
  if (next >= 0 && next < SECTIONS.length) { STATE.section = SECTIONS[next]; render(); }
}, { passive: true });
// energieprofiel-knoppen via delegation (werkt ongeacht render-volgorde)
document.addEventListener("click", (e) => {
  const b = e.target.closest(".pbtn");
  if (b && b.dataset.mach && b.dataset.prof) { e.stopPropagation(); setProfile(b.dataset.mach, b.dataset.prof); }
  if (e.target.closest("#restartbtn")) {
    e.stopPropagation();
    const opt = RESTARTS.find(([v]) => v === STATE.restartSel) || RESTARTS[0];
    doRestart(STATE.active, opt[0], opt[1]);
  }
  // eigen dropdown i.p.v. native <select> (die kon niet gestyled worden — zag er "OS-standaard" uit).
  // Zolang 'ie open staat, de live-ververs pauzeren (zelfde reden als vroeger bij focus op de
  // native select): anders duwt een herbouw van het paneel de lijst dicht vóór je kunt klikken.
  const dropbtn = e.target.closest("#restartdropbtn");
  if (dropbtn) { e.stopPropagation(); STATE.restartDropOpen = !STATE.restartDropOpen; STATE.mgmtFocus = STATE.restartDropOpen; render(); }
  const item = e.target.closest(".mgmtdropitem");
  if (item) { e.stopPropagation(); STATE.restartSel = item.dataset.v; STATE.restartDropOpen = false; STATE.mgmtFocus = false; render(); }
  if (e.target.closest("#cleanupbtn")) { e.stopPropagation(); doCleanup(STATE.active); }
  if (e.target.closest("#rebootbtn")) { e.stopPropagation(); doReboot(STATE.active); }
  if (e.target.closest("#upgradebtn")) { e.stopPropagation(); doUpgrade(STATE.active); }
  if (e.target.closest("#downgradebtn")) { e.stopPropagation(); doDowngrade(STATE.active); }
  // ℹ-knop per tabblad: uitleg op aanvraag i.p.v. permanente tekst in de UI (generiek voor alle 4 tabs)
  const infobtn = e.target.closest(".infobtn");
  if (infobtn) {
    e.stopPropagation();
    const box = document.querySelector(`.infopop[data-infobox="${infobtn.dataset.info}"]`);
    if (box) box.classList.toggle("on");
  } else if (!e.target.closest(".mgmtdrop") && STATE.restartDropOpen) { STATE.restartDropOpen = false; STATE.mgmtFocus = false; render(); }
});
const $ = id => document.getElementById(id);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const num = v => (v == null || v === "") ? NaN : Number(v);
const asArr = v => Array.isArray(v) ? v : (typeof v === "string" ? (() => { try { return JSON.parse(v); } catch (e) { return null; } })() : null);
const hhmm = d => new Date(d || Date.now()).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });

// ── status-symbool (kleurenblind-proof: symbool + tekst) ──
const SYM = { ok: "\u2713", warn: "\u25CF", high: "\u25B2" };
const WORD = { ok: "OK", warn: "LET OP", high: "HOOG" };
const stt = (v, warn, high) => isNaN(v) ? "ok" : (v > high ? "high" : (v > warn ? "warn" : "ok"));
const sc = { ok: "ok", warn: "warn", high: "hi" };

let STATE = { machines: [], latest: {}, cfg: {}, active: null, hist: [], histMetric: "cpu", live: {}, liveStale: false, updatesOpen: false, holds: {}, statusOpen: false, profiles: {}, profileWish: {}, chipOpen: {}, perf: {}, section: "overzicht", restartDropOpen: false, mode: {}, hasWebhook: {} };

function renderSectionTabs() {
  [...document.querySelectorAll(".stab")].forEach(s => {
    s.classList.toggle("on", s.dataset.s === STATE.section);
    s.onclick = () => { STATE.section = s.dataset.s; render(); };
  });
  [...document.querySelectorAll(".panel")].forEach(p => p.classList.toggle("on", p.dataset.panel === STATE.section));
}
let LIVE_TIMER = null;

// ── Supabase REST ──
async function api(path) {
  const r = await fetch(`${CFG.apiBase || CFG.url+"/rest/v1"}/${path}`, {
    headers: CFG.apiBase ? {} : { apikey: CFG.anon, Authorization: `Bearer ${CFG.anon}` }
  });
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  return r.json();
}

// ── data laden ──
async function loadCore() {
  if (DEMO) { const d = demoData(); STATE.machines = d.machines; STATE.latest = d.latest; STATE.cfg = d.cfg; return; }
  const [machines, latest, cfg] = await Promise.all([
    api("machines?select=*&order=machine"),
    api("v_latest?select=*"),
    api("config?select=*&limit=1")
  ]);
  STATE.machines = machines;
  STATE.latest = {}; latest.forEach(r => STATE.latest[r.machine] = r);
  STATE.cfg = (cfg[0] && cfg[0].thresholds && cfg[0].thresholds.default) || {};
}

async function paged(path) {
 const result=[];let offset=0;
 for (;;) { const rows=await api(path+`&limit=500&offset=${offset}`); if (!rows.length) break;result.push(...rows);offset+=rows.length; }
 return result;
}

function holdWrite(machine, pkg, hold) {
  if (DEMO) return;
  if (needsTailscaleHop(machine)) return;
  // via de Tailscale-only gateway (zie gatewayUrl/callGateway hieronder) — niet meer rechtstreeks
  // met de publiek meegestuurde anon-key naar Supabase, zelfde reden als bij setProfile().
  callGateway(machine, "/set-hold", { package: pkg, hold }, (ok) => {
    if (!ok) { alert("Kon update-voorkeur niet opslaan (sta je op het Tailscale-netwerk?)"); loadHolds().then(render); }
  });
}

// laad bestaande holds bij start/tab-wissel
async function loadHolds() {
  if (DEMO) return;
  try {
    const rows = await api("update_holds?select=machine,package");
    STATE.holds = {};
    (rows||[]).forEach(r => { (STATE.holds[r.machine] = STATE.holds[r.machine] || new Set()).add(r.package); });
  } catch(e){}
}


// ── actions-gateway (Tailscale-only, per machine) ──
// Schrijft NIET meer rechtstreeks naar Supabase met de (publiek meegestuurde) anon-key — dat kon
// voorheen door iedereen met de dashboard-link misbruikt worden. Nu via de kleine gateway die
// alleen op het Tailscale-IP van de doelmachine luistert: bereikbaar binnen het tailnet, niet
// vanaf het publieke internet. Wie alleen de publieke link heeft, kan dus meekijken, niet sturen.
function gatewayUrl(machine, path) {
  const mc = STATE.machines.find(x => x.machine === machine);
  const ip = mc && mc.tailscale_ip;
  return ip ? `http://${ip}:7072${path}` : null;
}
// Via de publieke https-tunnel-link blokkeert de browser zelf elk verzoek naar de (bewust
// plain-http/Tailscale-only) gateway — mixed content. Vóórdat een actie-knop ook maar iets
// vraagt (naam overtypen, bevestigen), meteen doorschakelen naar de stabiele Tailscale-versie
// van het dashboard, zodat je maar één keer iets hoeft in te vullen — op de plek waar het ook
// echt werkt. Geeft true (en navigeert al weg) als dit nodig was; de aanroeper stopt dan direct.
function needsTailscaleHop(machine) {
  if (location.protocol !== "https:") return false;
  const mc = STATE.machines.find(x => x.machine === machine);
  const ip = mc && mc.tailscale_ip;
  if (!ip) return false;
  if (!CFG.hub) { alert("Hubadres ontbreekt"); return true; }
  location.href = CFG.hub + location.pathname + "?machine=" + encodeURIComponent(machine);
  return true;
}
function callGateway(machine, path, body, onDone) {
  const url = gatewayUrl(machine, path);
  if (!url) { onDone(false, "geen Tailscale-IP bekend voor " + machine); return; }
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 600000);
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({...body, machine}), signal: ctl.signal })
    .then(r => r.json().then(j => ({ status: r.status, j })))
    .then(({ status, j }) => { clearTimeout(t); onDone(status === 200 && j.ok, j.detail || ""); })
    .catch(() => { clearTimeout(t); onDone(false, "niet bereikbaar — sta je op het Tailscale-netwerk?"); });
}

function setProfile(machine, profile) {
  if (DEMO) { STATE.profileWish = STATE.profileWish || {}; STATE.profileWish[machine] = profile; render(); return; }
  if (needsTailscaleHop(machine)) return;
  STATE.profileWish = STATE.profileWish || {}; STATE.profileWish[machine] = profile; render();   // optimistisch
  callGateway(machine, "/set-profile", { profile }, (ok, detail) => {
    if (!ok) alert("Profiel wijzigen mislukt: " + detail);
    loadProfiles().then(render);
  });
}

function doRestart(machine, service, label_) {
  if (needsTailscaleHop(machine)) return;
  if (!confirm(`${label(machine)} — "${label_}" herstarten?`)) return;
  callGateway(machine, "/restart", { service }, (ok, detail) => {
    alert(ok ? `Gelukt: ${label_} herstart.` : `Mislukt: ${detail}`);
    loadActionLog().then(render);
  });
}

function doCleanup(machine) {
  if (needsTailscaleHop(machine)) return;
  if (!confirm(`${label(machine)} — veilige opschoning uitvoeren?\n(apt clean + oude logs opruimen)`)) return;
  callGateway(machine, "/cleanup", {}, (ok, detail) => {
    alert(ok ? "Opschoning gelukt." : `Opschoning mislukt: ${detail}`);
    loadActionLog().then(render);
  });
}

function doReboot(machine) {
  if (needsTailscaleHop(machine)) return;
  // trede 4 — zwaarste actie: hele machine herstarten, niet alleen een dienst. Stevigere
  // bevestiging dan de andere BEHEER-knoppen: de machinenaam moet exact overgetypt worden.
  const typed = prompt(`${label(machine)} volledig HERSTARTEN (hele PC, geen dienst).\nDit kan een paar minuten duren voor alles weer online is.\n\nTyp "${machine}" om te bevestigen:`);
  if (typed === null) return;
  if (typed.trim() !== machine) { alert("Naam kwam niet overeen — geannuleerd, er is niets herstart."); return; }
  callGateway(machine, "/reboot", { confirm: machine }, (ok, detail) => {
    alert(ok ? `${label(machine)} start nu opnieuw op.` : `Mislukt: ${detail}`);
    loadActionLog().then(render);
  });
}

async function loadMode(machine) {
  if (DEMO || !machine) { STATE.mode[machine] = DEMO ? "advanced" : "basis"; STATE.hasWebhook[machine] = false; return; }
  const url = gatewayUrl(machine, "/mode");
  if (!url) { STATE.mode[machine] = DEMO ? "advanced" : "basis"; STATE.hasWebhook[machine] = false; return; }
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 4000);
    const r = await fetch(url, { signal: ctl.signal });
    clearTimeout(t);
    const j = await r.json();
    STATE.mode[machine] = (j && j.mode === "basis") ? "basis" : "advanced";
    STATE.hasWebhook[machine] = !!(j && j.has_webhook);
  } catch (e) {
    // onbereikbaar, of een oudere gateway zonder /mode-endpoint → aannemen dat het een bestaande,
    // van-vóór-dit-onderscheid volledige installatie is (zelfde default als de gateway zelf hanteert)
    STATE.mode[machine] = "unreachable";
    STATE.hasWebhook[machine] = false;
  }
}

function doUpgrade(machine) {
  if (needsTailscaleHop(machine)) return;
  let w = "";
  if (!STATE.hasWebhook[machine]) {
    // alleen vragen als er nog geen (geldige) webhook bekend is — bij een eerdere upgrade al
    // ingevuld en nog aanwezig in .env? Dan niet opnieuw lastigvallen, gewoon hergebruiken.
    const webhook = prompt(`${label(machine)} upgraden naar Advanced — kijken + zelf sturen + Discord-meldingen.\n\nVoer je Discord-webhook-URL in (Discord-kanaal → Instellingen → Integraties → Webhooks):`);
    if (webhook === null) return;
    w = webhook.trim();
    if (!/^https:\/\/discord\.com\/api\/webhooks\/\d+\/[\w-]+$/.test(w)) { alert("Dat ziet er niet uit als een geldige Discord-webhook-URL."); return; }
  }
  if (!confirm(`${label(machine)} upgraden naar Advanced?\nDit installeert de actie-laag (sturen) en meldingen-diensten. Kan een paar minuten duren.`)) return;
  callGateway(machine, "/upgrade-to-advanced", { discord_webhook: w }, (ok, detail) => {
    alert(ok ? "Upgrade gelukt! Voor Discord-meldingen moet je nog wel zelf n8n installeren en de workflows importeren — zie docs/SETUP.md." : `Upgrade mislukt: ${detail}`);
    loadMode(machine).then(() => { loadActionLog().then(render); });
  });
}

function doDowngrade(machine) {
  if (needsTailscaleHop(machine)) return;
  if (!confirm(`${label(machine)} terugzetten naar Basis (alleen kijken)?\nSturen vanaf het dashboard en Discord-meldingen stoppen dan — je blijft wel gewoon meekijken.`)) return;
  callGateway(machine, "/downgrade-to-basis", {}, (ok, detail) => {
    alert(ok ? "Terug naar Basis-modus." : `Mislukt: ${detail}`);
    loadMode(machine).then(() => { loadActionLog().then(render); });
  });
}

async function loadActionLog() {
  if (DEMO) { STATE.actionLog = []; return; }
  try {
    STATE.actionLog = await api(`action_log?machine=eq.${encodeURIComponent(STATE.active)}&select=action,status,detail,ts&order=ts.desc&limit=5`);
  } catch (e) { STATE.actionLog = []; }
}
async function loadProfiles() {
  if (DEMO) return;
  try {
    const rows = await api("machine_actions?select=machine,power_profile,applied_profile");
    STATE.profiles = {};
    (rows||[]).forEach(r => STATE.profiles[r.machine] = { wish: r.power_profile, applied: r.applied_profile });
  } catch(e){}
}

async function loadHist() {
  const m = STATE.active; if (!m) return;
  if (DEMO) { STATE.hist = demoHist(); return; }
  const rows = await api(`metrics?machine=eq.${encodeURIComponent(m)}&select=ts,cpu,temp,battery,net_rx&order=ts.desc&limit=120`);
  STATE.hist = rows.reverse();
}

// ── PRESTATIE: laatste zware gebruikssessie + throttling-indicator ──
// Puur client-side uit de bestaande metrics-historie (geen agent-wijziging nodig). Herkent een
// sustained periode van hoge CPU-load (>=5 min aaneengesloten) en vergelijkt de klokfrequentie
// tijdens die sessie met de hoogste frequentie die ooit gemeten is TIJDENS vergelijkbaar zware
// belasting (niet de absolute piek — die haalt de CPU juist bij weinig actieve kernen, single-core
// turbo ligt altijd hoger dan all-core turbo, dat zou anders ten onrechte als throttling tellen).
// Zakt de sessie duidelijk onder die belaste-referentie, dan is alleen een frequentiedaling aangetoond; de oorzaak is onbekend.
// Bewust géén hardcoded turbo-clock per CPU-model: past zich vanzelf aan elke machine aan.
const PERF_BUSY_CPU = 65, PERF_MIN_SAMPLES = 10; // 10 x 30s = 5 min aaneengesloten
function findSession(rows) {
  const sessions = []; let cur = null;
  for (const r of rows) {
    const cpu = num(r.cpu);
    if (cur && Date.parse(r.ts)-Date.parse(cur[cur.length-1].ts)>90000) { sessions.push(cur);cur=null; }
    if (!isNaN(cpu) && cpu >= PERF_BUSY_CPU) { if (!cur) cur = []; cur.push(r); }
    else { if (cur) sessions.push(cur); cur = null; }
  }
  if (cur) sessions.push(cur);
  const real = sessions.filter(s => s.length >= PERF_MIN_SAMPLES && Date.parse(s[s.length-1].ts)-Date.parse(s[0].ts)>=270000);
  return real.length ? real[real.length - 1] : null;
}
async function loadPerf() {
  const m = STATE.active; if (!m) return;
  STATE.perf = STATE.perf || {};
  if (DEMO) { STATE.perf[m] = null; return; }
  try {
    const [rows, maxRows] = await Promise.all([
      paged(`metrics?machine=eq.${encodeURIComponent(m)}&select=ts,cpu,freq,temp&ts=gte.${encodeURIComponent(new Date(Date.now()-48*3600000).toISOString())}&order=ts.desc`),   // ~48u op 30s
      // referentie voor throttling: hoogste freq ooit gemeten TIJDENS vergelijkbaar zware belasting
      // (cpu>=busy-drempel) — niet de absolute piek, want die haalt de CPU juist bij weinig actieve
      // kernen (single-core turbo ligt altijd hoger dan all-core turbo onder volle belasting).
      api(`metrics?machine=eq.${encodeURIComponent(m)}&select=freq&cpu=gte.${PERF_BUSY_CPU}&freq=not.is.null&order=freq.desc&limit=1`),
    ]);
    const sess = findSession(rows.reverse());
    if (!sess) { STATE.perf[m] = { none: true }; return; }
    const maxFreq = (maxRows[0] && num(maxRows[0].freq)) || null;
    const peakCpuRow = sess.reduce((a, b) => (num(b.cpu) > num(a.cpu) ? b : a));
    const peakTempRow = sess.reduce((a, b) => (num(b.temp) > num(a.temp) ? b : a));
    const freqs = sess.map(r => num(r.freq)).filter(v => !isNaN(v));
    const avgFreq = freqs.length ? freqs.reduce((a, b) => a + b, 0) / freqs.length : null;
    const throttled = (maxFreq && avgFreq) ? (avgFreq < maxFreq * 0.9) : null;
    let culprit = null;
    try {
      const cr = await api(`metrics?machine=eq.${encodeURIComponent(m)}&ts=eq.${encodeURIComponent(peakCpuRow.ts)}&select=top_procs&limit=1`);
      const tp = (cr[0] && asArr(cr[0].top_procs)) || [];
      culprit = tp.length ? tp[0].name : null;
    } catch (e) {}
    STATE.perf[m] = {
      start: sess[0].ts, end: sess[sess.length - 1].ts,
      durationMin: Math.max(1, Math.round((Date.parse(sess[sess.length - 1].ts) - Date.parse(sess[0].ts)) / 60000)),
      peakCpu: num(peakCpuRow.cpu), peakTemp: num(peakTempRow.temp),
      avgFreq, maxFreq, throttled, culprit,
    };
  } catch (e) { STATE.perf[STATE.active] = null; }
}

// ── helpers ──
const TH = () => ({...STATE.cfg,...((STATE.machines.find(x=>x.machine===STATE.active)||{}).thresholds||{})});
const capability = key => !!((STATE.machines.find(x=>x.machine===STATE.active)||{}).capabilities||{})[key];
function online(r) { const t = r && Date.parse(r.ts); return t && (Date.now() - t) / 60000 <= (TH().offline_min ?? 10); }
function label(m) { const x = STATE.machines.find(x => x.machine === m); return x ? (x.label || m) : m; }

// ── ring-gauge ──
function pt(cx, cy, r, d) { const a = d * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
function arcPath(cx, cy, r, s, sw) { const [x0, y0] = pt(cx, cy, r, s), [x1, y1] = pt(cx, cy, r, s + sw); return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${sw > 180 ? 1 : 0} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; }
const RCOL = { ok: "var(--green)", warn: "var(--amber)", high: "var(--red)" };
function ringHTML(val, status, lab, sub) {
  const v = isNaN(val) ? 0 : Math.max(0, Math.min(100, val)), c = RCOL[status] || RCOL.ok, cx = 75, cy = 72, r = 54;
  return `<svg class="ringsvg" viewBox="0 0 150 150">
    <path class="rtrack" d="${arcPath(cx, cy, r, 130, 280)}"/>
    <path class="rfill" d="${arcPath(cx, cy, r, 130, Math.max(1, 280 * v / 100))}" stroke="${c}" style="filter:drop-shadow(0 0 5px ${c})"/>
    <text class="rval" x="${cx}" y="${cy + 8}" fill="${c}">${isNaN(val) ? "\u2014" : Math.round(v)}</text>
    <text class="rpct" x="${cx}" y="${cy + 26}">%</text></svg><div class="rlabel">${esc(lab)}</div>${sub ? `<div class="rsub">${esc(sub)}</div>` : ""}`;
}


async function loadLive() {
  if (DEMO) {
    for (const mc of STATE.machines) {
      const b = STATE.latest[mc.machine] || {}; const j=(x,d)=>Math.max(0,Math.min(100,(Number(x)||d)+(Math.random()*10-5)));
      STATE.latest[mc.machine] = {...b, cpu:j(b.cpu,30), mem:j(b.mem,40),
        cores:(b.cores||[20,15,10,8,6,5,4,3]).map(c=>Math.round(j(c,10)))};
    }
    return;
  }
  const rows = await api("live?select=*");
  (rows||[]).forEach(r => {
    const base = STATE.latest[r.machine] || {};
    // alleen de live-velden overschrijven; de rest (updates, accu, disk, net, load, uptime...) blijft van de 30s-meting
    if (!r.ts || Date.now()-Date.parse(r.ts)>10000 || Date.parse(r.ts)>Date.now()+5000) return;
    const liveFields = {};
    ["cpu","mem","temp","freq","cores","core_temps","top_procs"].forEach(k => { if (r[k] !== undefined && r[k] !== null) liveFields[k] = r[k]; });
    STATE.latest[r.machine] = { ...base, ...liveFields };
  });
}
function setLive(){}
// niveaumeter: balklengte = gewoon het percentage zelf, direct en simpel — geen herschaling,
// geen trucjes. Zolang dezelfde rij hergebruikt wordt (i.p.v. gesloopt+herbouwd) beweegt de balk
// gewoon mee zodra het percentage verandert, precies zoals het percentage-label ernaast dat al deed.
function updateProcRows(procs) {
  const list = $("prowlist"); if (!list) return;
  // Matchen op NAAM ongeacht positie — niet alleen "zelfde naam op zelfde plek". Op een drukke
  // machine wisselt de volgorde van de top-5 voortdurend (cpu% schommelt), ook al blijven het vaak
  // dezelfde processen. Positioneel matchen zag dat als "steeds een ander proces" en verving de
  // rij dus telkens vers. Nu: bestaande rij (ongeacht huidige plek) hergebruiken + verplaatsen naar
  // de nieuwe plek, zodat dezelfde DOM-node blijft bestaan en de breedte-transitie (style.css) écht
  // kan lopen. (Geen pid beschikbaar vanuit de agent — bij twee processen met dezelfde naam kan de
  // match dus wisselen; voor een levendige activiteitsmeter is dat een aanvaardbare benadering.)
  const byName = new Map();
  [...list.children].forEach(r => {
    const k = r.dataset.name;
    if (!byName.has(k)) byName.set(k, []);
    byName.get(k).push(r);
  });
  const used = new Set();
  procs.forEach((p, i) => {
    const c = Math.max(0, Math.min(100, num(p.cpu) || 0));
    const pctTxt = isNaN(num(p.cpu)) ? "" : Math.round(p.cpu) + "%";
    const bucket = byName.get(p.name);
    let node = null;
    while (bucket && bucket.length && !node) { const cand = bucket.shift(); if (!used.has(cand)) node = cand; }
    const ref = list.children[i] || null;
    if (node) {
      used.add(node);
      node.querySelector(".pf").style.width = c + "%";
      node.querySelector(".pp").textContent = pctTxt;
      if (ref !== node) list.insertBefore(node, ref);
    } else {
      const fresh = el("div", "prow", `<span class="pn">${esc(p.name)}</span><span class="pb"><span class="pf" style="width:${c}%"></span></span><span class="pp">${pctTxt}</span>`);
      fresh.dataset.name = p.name;
      list.insertBefore(fresh, ref);
    }
  });
  while (list.children.length > procs.length) list.removeChild(list.lastChild);
}
// TOP PROCESSEN krijgt zijn eigen, onafhankelijke 2s-lus — los van de grote render()-cyclus
// (die ook rings/chips/cockpit/etc. herbouwt). Leest rechtstreeks uit STATE.latest, dat de
// live-heartbeat (lbeat) toch al vers houdt; hoeft dus niet te wachten tot render() zelf aan de
// beurt komt. Eigen idee na een lang debug-traject over de balkjes.
function procTick() {
  if (STATE.updatesOpen || STATE.mgmtFocus) return;
  if (!$("prowlist")) return;
  const d = STATE.latest[STATE.active] || {};
  const procs = asArr(d.top_procs) || [];
  if (procs.length) updateProcRows(procs);
  else $("prowlist").innerHTML = '<div class="prow"><span class="pn" style="color:var(--muted)">geen data</span></div>';
}

// ── render ──
function refreshStatus() {
  const node=$("refresh-status");
  if(node){node.hidden=!(STATE.updatesOpen||STATE.mgmtFocus);node.textContent="Weergave tijdelijk gepauzeerd tijdens bediening. Sluit het menu om de nieuwste metingen te zien.";}
}
function render() {
  refreshStatus();
  const machs = STATE.machines.map(x => x.machine);
  if (!STATE.active || !machs.includes(STATE.active)) STATE.active = (machs.includes('pro') ? 'pro' : machs[0]);
  const d = STATE.latest[STATE.active] || {};
  // status: verzamel ALARMEN (LET OP) en AANDACHTSPUNTEN (bewust van zijn) over alle machines
  const T = TH();
  const alarms = [], notes = [];
  [STATE.active].forEach(m => {
    const r = STATE.latest[m]; const lab = label(m);
    if (!r || !online(r)) { alarms.push(`${lab}: offline`); return; }
    const disk=num(r.disk), temp=num(r.temp), mem=num(r.mem), swap=num(r.swap), bat=num(r.battery),
          health=num(r.bat_health), l15=num(r.load15), cores=(r.cores||[]).length||1,
          reboot=(r.extra&&r.extra.reboot_required);
    // ── ALARMEN ──
    if (disk >= (T.disk_alarm ?? 90)) alarms.push(`${lab}: schijf ${Math.round(disk)}%`);
    for(const mount of (r.disks||[])){if(mount.mount!=="/" && num(mount.pct)>=(T.disk_alarm??90))alarms.push(`${lab}: ${mount.mount} ${Math.round(mount.pct)}%`);}
    if (temp >= (T.temp_alarm ?? 90)) alarms.push(`${lab}: ${Math.round(temp)}\u00b0`);
    if (r.net_up === false) alarms.push(`${lab}: internet weg`);
    if (r.bat_plugged === false && bat < (T.bat_min ?? 15)) alarms.push(`${lab}: accu ${Math.round(bat)}%`);
    if (mem >= 95) alarms.push(`${lab}: RAM ${Math.round(mem)}%`);
    if (swap >= 50) alarms.push(`${lab}: swap ${Math.round(swap)}%`);
    // ── AANDACHTSPUNTEN (alleen als geen alarm voor dat item) ──
    if (disk >= (T.disk_warn ?? 75) && disk < (T.disk_alarm ?? 90)) notes.push(`${lab}: schijf ${Math.round(disk)}%`);
    if (temp >= (T.temp_warn ?? 80) && temp < (T.temp_alarm ?? 90)) notes.push(`${lab}: ${Math.round(temp)}\u00b0`);
    if (mem >= 85 && mem < 95) notes.push(`${lab}: RAM ${Math.round(mem)}%`);
    if (swap >= 10 && swap < 50) notes.push(`${lab}: swap ${Math.round(swap)}%`);
    if (l15 > cores) notes.push(`${lab}: load ${l15.toFixed(1)} (15m)`);
    if (reboot) notes.push(`${lab}: herstart nodig`);
    if (!isNaN(health) && health > 0 && health < 50) notes.push(`${lab}: accu-conditie ${Math.round(health)}%`);
  });
  const anyAlert = alarms.length > 0;
  const anyNote = notes.length > 0;
  const statusSym = anyAlert ? "\u25B2" : (anyNote ? "\u26A0" : "\u2713");
  const statusTxt = anyAlert ? "LET OP" : (anyNote ? `${notes.length} AANDACHTSPUNT${notes.length>1?"EN":""}` : "ALLES OK");
  const statusCls = anyAlert ? "alert" : (anyNote ? "warn" : "ok");
  const statusList = (anyAlert ? alarms : notes);
  const nOn = machs.filter(m => online(STATE.latest[m])).length;

  // topbar
  $("topbar").innerHTML = `
    <div class="mark"><svg viewBox="0 0 24 24" fill="none" stroke="#00d4ff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2-7 4 14 2-7h6"/></svg></div>
    <div class="brand">SYSDASH<small>mission control${DEMO ? " · DEMO" : ""}</small></div>
    <div class="pill ${statusCls}${STATE.statusOpen ? " open" : ""}" id="statuspill"><span class="dot"></span>${statusSym} ${statusTxt}${statusList.length ? `<div class="statusdetail">${statusList.map(x=>esc(x)).join("<br>")}</div>` : ""}</div>
    <div class="topright">
      ${capability("gateway") && STATE.mode[STATE.active]==="advanced" ? `<button class="topreboot" id="rebootbtn" title="${esc(label(STATE.active))} — hele PC herstarten">⚠</button>` : ""}
      <div class="clock">${hhmm()}<small>${nOn}/${machs.length} online</small></div>
    </div>`;

  // tabs
  $("tabs").innerHTML = "";
  STATE.machines.forEach(x => {
    const t = el("div", "tab" + (x.machine === STATE.active ? " on" : ""), esc((x.label || x.machine).toUpperCase()));
    if (!online(STATE.latest[x.machine])) t.innerHTML += ' <span class="hi">\u25B2</span>';
    t.onclick = () => { STATE.active = x.machine; Promise.all([loadHist(), loadActionLog(), loadPerf(), loadMode(x.machine)]).then(render); };
    $("tabs").appendChild(t);
  });
const sp = document.getElementById("statuspill"); if (sp) sp.onclick = (e) => { e.stopPropagation(); STATE.statusOpen = !STATE.statusOpen; sp.classList.toggle("open", STATE.statusOpen); };
  renderSectionTabs();

  const off = !online(d);
  // netwerk
  const rx = num(d.net_rx), tx = num(d.net_tx);
  const spd = b => isNaN(b) ? "\u2014" : (b > 1e6 ? (b / 1e6).toFixed(1) + " <span class='u'>MB/s</span>" : Math.round(b / 1e3) + " <span class='u'>kB/s</span>");
  const netUp = d.net_up !== false && !off;
  // #prowlist zit als STATISCHE markup in index.html, nooit via innerHTML vervangen \u2014 alleen
  // #netgrid (simpele cijfers) wordt elke cyclus herbouwd. TOP PROCESSEN zelf loopt via de eigen
  // procTick()-lus hieronder, niet hier (zie procTick voor de reden).
  $("netgrid").innerHTML = `
      <div class="nstat"><div class="nl">INTERNET</div><div class="nv"><span class="${netUp ? "ok" : "hi"}">${netUp ? "\u2713" : "\u25B2"}</span> ${netUp ? "Online" : "Weg"}</div></div>
      <div class="nstat"><div class="nl">STATUS</div><div class="nv"><span class="${off ? "hi" : "ok"}">${off ? "\u25B2" : "\u2713"}</span> ${off ? "offline" : "actief"}</div></div>
      <div class="nstat"><div class="nl">DOWNLOAD</div><div class="nv">\u2193 ${spd(rx)}</div></div>
      <div class="nstat"><div class="nl">UPLOAD</div><div class="nv">\u2191 ${spd(tx)}</div></div>`;
  procTick();   // meteen bijwerken bij bv. een machine-wissel, niet wachten op de eigen 2s-lus

  // ringen
  const cpu = num(d.cpu), mem = num(d.mem), disk = num(d.disk);
  // CPU-frequentie als subtekst (freq komt binnen in MHz)
  const freqVal = num(d.freq);
  const cpuSub = isNaN(freqVal) ? "" : (freqVal/1000).toFixed(2) + " GHz";
  // hardware-info komt van de machines-rij (1x per machine, verandert nooit tussen reboots) —
  // niet uit de metrics-tijdreeks, om dat niet elke 30s te dupliceren.
  const hw = (STATE.machines.find(x => x.machine === STATE.active) || {}).hardware;
  // RAM in GB: mem% van totaal (uit hardware.ram_gb)
  let ramSub = "";
  const ramTot = hw && hw.ram_gb;
  if (ramTot && !isNaN(mem)) { const used = mem/100*ramTot; ramSub = `${used.toFixed(1)} / ${ramTot} GB`; }
  // Schijf in GB: uit de root-partitie in d.disks
  let diskSub = "";
  if (Array.isArray(d.disks)) {
    const root = d.disks.find(x => x.mount === "/") || d.disks[0];
    if (root && root.gb) { const usedG = (root.pct||0)/100*root.gb; diskSub = `${usedG.toFixed(0)} / ${root.gb} GB`; }
  }
  $("rings").innerHTML =
    `<div class="ring">${ringHTML(cpu, stt(cpu, 75, 90), "CPU", cpuSub)}</div>` +
    `<div class="ring">${ringHTML(mem, stt(mem, 75, 90), "RAM", ramSub)}</div>` +
    `<div class="ring">${ringHTML(disk, stt(disk, TH().disk_warn ?? 80, TH().disk_alarm ?? 90), "SCHIJF", diskSub)}</div>`;

  // cockpit
  const cores = asArr(d.cores) || [], ct = asArr(d.core_temps) || [], temps = (typeof d.temps === "object" && d.temps) || asArr(d.temps) || {};
  const coreBars = cores.length ? cores.map((v, i) => `<div class="cbar"><i style="height:${Math.max(3, Math.min(100, num(v) || 0))}%"></i><b>c${i}</b></div>`).join("") : '<span style="color:var(--muted);font-size:11px">geen data</span>';
  const ctRows = ct.length ? ct.map((v, i) => `<div class="ctemp"><span class="n">Core ${i}</span><span class="v">${Math.round(v)}\u00b0</span></div>`).join("") + (isNaN(num(d.temp)) ? "" : `<div class="ctemp"><span class="n">Package</span><span class="v">${Math.round(d.temp)}\u00b0</span></div>`) : '<span style="color:var(--muted);font-size:11px">geen data</span>';
  // systeem: overige sensoren (niet core), + swap + freq
  const sysT = Object.entries(temps).filter(([k]) => !/core|package/i.test(k)).slice(0, 3)
    .map(([k, v]) => `<div class="m"><span class="n">${esc(k.split("/").pop())}</span><span class="v">${Math.round(v)}\u00b0</span></div>`).join("");
  const swap = num(d.swap), freq = num(d.freq);
  $("cockpit").innerHTML = `
    <div class="cpanel"><div class="ph">CORE LOAD <span class="ok">\u2713</span></div><div class="cores">${coreBars}</div></div>
    <div class="cpanel"><div class="ph">CORE TEMP <span class="${stt(Math.max(...(ct.length ? ct.map(Number) : [0])), (TH().temp_alarm ?? 90) - 10, TH().temp_alarm ?? 90) === "ok" ? "ok" : "warn"}">\u2713</span></div><div class="ctemps">${ctRows}</div></div>
    <div class="cpanel"><div class="ph">SYSTEEM <span class="ok">\u2713</span></div><div class="misc">${sysT}
      <div class="m"><span class="n">Swap</span><span class="v">${isNaN(swap) ? "\u2014" : Math.round(swap) + "%" + (swap>=10 ? " \u26A0" : "")}</span></div>
      <div class="m"><span class="n">Freq</span><span class="v">${isNaN(freq) ? "\u2014" : (freq / 1000).toFixed(2) + " GHz"}</span></div></div></div>
    ${(Array.isArray(d.disks) && d.disks.length) ? `<div class="cpanel"><div class="ph">SCHIJVEN <span class="ok">\u2713</span></div><div class="misc">${d.disks.map(dk=>`<div class="m"><span class="n">${esc(dk.mount||"?")}</span><span class="v">${Math.round(dk.pct||0)}% ${dk.gb?`\u00b7 ${dk.gb} GB`:""}</span></div>`).join("")}</div></div>` : ""}
    ${hw ? `<div class="cpanel"><div class="ph">HARDWARE <span class="ok">\u2713</span></div><div class="misc">
      ${hw.cpu ? `<div class="m hw"><span class="n">CPU</span><span class="v">${esc(hw.cpu)}</span></div>` : ""}
      ${hw.ram_str ? `<div class="m hw"><span class="n">RAM</span><span class="v">${esc(hw.ram_str)}</span></div>` : ""}
      ${hw.disk ? `<div class="m hw"><span class="n">Schijf</span><span class="v">${esc(hw.disk)}</span></div>` : ""}
    </div></div>` : ""}
    ${(() => {
      const p = (STATE.perf || {})[STATE.active];
      if (!p) return "";
      if (p.none) return `<div class="cpanel"><div class="ph">PRESTATIE <span class="ok">✓</span></div><div class="misc"><div class="m"><span class="n" style="color:var(--muted)">nog geen zware sessie herkend (laatste 48u)</span></div></div></div>`;
      const relTime = ts => { const min = Math.round((Date.now() - Date.parse(ts)) / 60000);
        if (min < 60) return `${min} min geleden`; const uur = Math.round(min/60);
        return uur < 24 ? `${uur}u geleden` : `${Math.round(uur/24)}d geleden`; };
      const pct = (p.maxFreq && p.avgFreq) ? Math.round(p.avgFreq / p.maxFreq * 100) : null;
      const throttleSym = p.throttled === null ? "—" : (p.throttled ? "▲" : "✓");
      const throttleCls = p.throttled === null ? "" : (p.throttled ? "hi" : "ok");
      const throttleTxt = p.throttled === null ? "onbekend (te weinig freq-data)" :
        (p.throttled ? `zakte weg${pct!=null?` (${pct}% van piek)`:""} — oorzaak niet vastgesteld` : `hield stand${pct!=null?` (${pct}% van piek)`:""}`);
      return `<div class="cpanel"><div class="ph">PRESTATIE <span class="ok">✓</span></div><div class="misc">
        <div class="m"><span class="n">Laatste zware sessie</span><span class="v">${relTime(p.start)} · ${p.durationMin} min</span></div>
        <div class="m"><span class="n">Piek CPU</span><span class="v">${isNaN(p.peakCpu)?"—":Math.round(p.peakCpu)+"%"}</span></div>
        <div class="m"><span class="n">Piek temp</span><span class="v">${isNaN(p.peakTemp)?"—":Math.round(p.peakTemp)+"°C"}</span></div>
        <div class="m"><span class="n">Frequentie</span><span class="v ${throttleCls}">${throttleSym} ${throttleTxt}</span></div>
        ${p.culprit ? `<div class="m"><span class="n">Veroorzaker</span><span class="v">${esc(p.culprit)}</span></div>` : ""}
      </div></div>`;
    })()}`;

  // BEHEER-tab: energie + beheer, apart van de telemetrie hierboven (§ sparren 22 aug —
  // acties horen niet tussen de meetwaarden te staan, dat is te makkelijk per ongeluk te raken)
  // Basis-modus (alleen kijken, geen actie-laag): alleen een upgrade-kaart, geen energie/herstart/
  // opschonen — die bestaan simpelweg niet op een Basis-installatie (zie install/setup.sh).
  const mode = STATE.mode[STATE.active] || "basis";
  if (!capability("gateway") || mode !== "advanced") {
    $("beheerpanel").innerHTML = `<div class="cpanel"><div class="ph">ALLEEN KIJKEN</div><p>Beheer is op deze machine niet beschikbaar. Wijzig de installatiemodus lokaal met de installer.</p></div>`;
  } else {
  $("beheerpanel").innerHTML = `
    ${(() => {
      if (!capability("profiles")) return "";
      const pr = (STATE.profiles[STATE.active] || {});
      const active = pr.applied || pr.wish || "balanced";
      const btn = (prof, sym, lab) => `<button class="pbtn ${active===prof?"on":""}" data-prof="${prof}" data-mach="${esc(STATE.active)}">${sym} ${lab}</button>`;
      return `<div class="cpanel"><div class="ph">ENERGIE <span class="ok">\u2713</span></div>
        <div class="pbtns">
          ${btn("power-saver","\u{1F50B}","Spaar")}
          ${btn("balanced","\u2696","Balans")}
          ${btn("performance","\u26A1","Prestatie")}
        </div>
        <div class="pnow">Nu actief: ${esc(active)}</div></div>`;
    })()}
    ${(() => {
      if (!STATE.restartSel) STATE.restartSel = RESTARTS[0][0];   // onthouden, anders reset de live-ververs 'm elke 2s
      const restarts = (STATE.machines.find(x=>x.machine===STATE.active)||{}).role === "hub" ? RESTARTS : RESTARTS.filter(([name])=>["restart-agent","restart-live"].includes(name));
      if (!restarts.some(([name])=>name===STATE.restartSel)) STATE.restartSel="restart-agent";
      const curLabel = (restarts.find(([v]) => v === STATE.restartSel) || RESTARTS[0])[1];
      const log = (STATE.actionLog || []).map(l => `<div class="alrow ${l.status}"><span>${l.status === "ok" ? "✓" : "▲"} ${esc(l.action)}</span><span class="alt">${hhmm(l.ts)}</span></div>`).join("") || `<div class="alrow"><span>nog geen acties</span></div>`;
      return `<div class="cpanel"><div class="ph">BEHEER <span class="ok">✓</span></div>
        <div class="mgmtrow">
          <div class="mgmtdrop${STATE.restartDropOpen ? " open" : ""}">
            <button class="mgmtdropbtn" id="restartdropbtn" type="button">${esc(curLabel)} <span class="car">▾</span></button>
            <div class="mgmtdroplist">${restarts.map(([v,l])=>`<div class="mgmtdropitem${v===STATE.restartSel?" on":""}" data-v="${v}">${esc(l)}</div>`).join("")}</div>
          </div>
          <button class="mgmtbtn" id="restartbtn">↻ Herstart</button>
        </div>
        <div class="mgmtrow"><button class="mgmtbtn wide" id="cleanupbtn">\u{1F9F9} Veilig opschonen</button></div>
        <div class="ph small">LAATSTE ACTIES</div>
        <div class="actionlog">${log}</div>
        <div class="pnow">Installatiemodus wijzigen: gebruik de installer op de machine.</div>
      </div>`;
    })()}`;
  }

  // status-chips (tik voor detail)
  const bat = num(d.battery), plug = d.bat_plugged, health = num(d.bat_health);
  const upd = num(d.updates), up = num(d.uptime);
  const upStr = isNaN(up) ? "\u2014" : (up >= 86400 ? Math.floor(up / 86400) + "d " + Math.floor((up % 86400) / 3600) + "u" : Math.floor(up / 3600) + "u " + Math.floor((up % 3600) / 60) + "m");
  const hasBat = !isNaN(bat);
  const chips = [];
  if (hasBat) {
    let bs = "ok"; if (plug === false && bat < (TH().bat_min ?? 15)) bs = "high"; else if (plug === false && bat < 40) bs = "warn";
    chips.push({ label: "ACCU", sym: bs, val: Math.round(bat) + "%", tap: (plug ? "aan stroom" : "op accu") + (isNaN(health) ? "" : " · conditie " + Math.round(health) + "%"), detail: `Status: ${esc(d.bat_status || "?")}<br>Conditie: ${isNaN(health) ? "?" : Math.round(health) + "% van origineel"}` });
  }
  const ulist = (d.extra && d.extra.updates_list) || [];
  const heldSet = STATE.holds[STATE.active] || new Set();
  const updDetail = ulist.length
    ? `<div class="updhint">Uitvinken = deze update overslaan bij de volgende ingeschakelde update-run (18:50). (Lijst staat stil zolang open.)</div>` +
      `<div class="updlegend"><span class="ulg rood">\u25B2 rood = beter uitvinken (kernel/uitgesteld)</span> <span class="ulg blauw">\u2713 blauw = veilig</span></div>` +
      `<div class="updlist">` + ulist.map(pkg =>
        (() => {
          // backwards-compat: pkg kan string (oud) of object {name,risk,kind} (nieuw) zijn
          const isObj = pkg && typeof pkg === "object";
          const raw = isObj ? pkg.name : pkg;
          const isFlat = isObj ? (pkg.kind === "flatpak") : raw.startsWith("flatpak:");
          const key = isObj ? (pkg.kind === "flatpak" ? "flatpak:" + raw : raw) : raw;
          const shown = (!isObj && raw.startsWith("flatpak:")) ? raw.slice(8) : raw;
          const risk = isObj ? pkg.risk : "blauw";
          const sym = risk === "rood" ? "\u25B2" : "\u2713";
          return `<label class="updrow ${risk}"><input type="checkbox" data-pkg="${esc(key)}" ${!capability("updates") || !capability("gateway") ? "disabled" : ""} ${heldSet.has(key) ? "" : "checked"}><span class="usym">${sym}</span><span class="uname">${esc(shown)}${isFlat ? ` <em class="flatpill">flatpak</em>` : ""}</span></label>`;
        })()
      ).join("") + `</div>`
    : (isNaN(upd) ? "geen data" : "alles up-to-date");
  chips.push({ id: "updates", label: "UPDATES", sym: isNaN(upd) ? "ok" : (upd > (TH().updates_many ?? 20) ? "high" : (upd > 0 ? "warn" : "ok")), val: isNaN(upd) ? "\u2014" : (upd <= 0 ? "0" : upd), tap: isNaN(upd) ? "" : (upd <= 0 ? "up-to-date" : upd + " klaar"), detail: updDetail });
  const needsReboot = d.extra && d.extra.reboot_required;
  chips.push({ label: "UPTIME", sym: needsReboot ? "high" : "ok", val: upStr, tap: needsReboot ? "\u25B2 herstart nodig" : "sinds herstart", detail: needsReboot ? `<b class="rbwarn">\u25B2 HERSTART NODIG</b><br>Een update wacht op een herstart. Doe dit op een rustig moment (kernel/systeem).<br><br>Laatste meting: ${d.ts ? hhmm(d.ts) : "?"}` : `Laatste meting: ${d.ts ? hhmm(d.ts) : "?"}` });
  chips.push({ label: "LOAD", sym: "ok", val: isNaN(num(d.load1)) ? "\u2014" : num(d.load1).toFixed(2), tap: "1-min gemiddelde", detail: `1m ${d.load1 ?? "?"} · 5m ${d.load5 ?? "?"} · 15m ${d.load15 ?? "?"}` });
  // elke tegel krijgt een stabiele id (updates had die al) zodat de open/dicht-status
  // ook de volgende live-ververs-cyclus (elke 2s) overleeft — anders klapt 'ie vanzelf weer dicht.
  $("chips").innerHTML = chips.map(c => { const cid = c.id || c.label.toLowerCase(); const isOpen = cid === "updates" ? STATE.updatesOpen : !!STATE.chipOpen[cid]; return `
    <div class="chip glass ${isOpen ? "open" : ""}" data-chip="${esc(cid)}"><div class="cl">${esc(c.label)} <span class="${sc[c.sym]}">${SYM[c.sym]}</span></div>
      <div class="cv">${esc(c.val)}</div><div class="tapd">${esc(c.tap || "tik voor detail")}</div>
      <div class="detail" ${cid === "updates" ? 'data-updates="1"' : ""}>${c.detail || ""}</div></div>`; }).join("");
  [...document.querySelectorAll(".chip")].forEach(ch => {
    ch.onclick = (e) => {
      const cid = ch.dataset.chip;
      // klik op een checkbox/label binnen updates → niet de chip togglen
      if (e.target.closest("[data-updates]") && cid === "updates") return;
      if (cid === "updates") STATE.updatesOpen = !STATE.updatesOpen;
      else STATE.chipOpen[cid] = !STATE.chipOpen[cid];
      ch.classList.toggle("open");
    };
  });
  // checkbox-handlers: elk vinkje meteen opslaan naar update_holds
  [...document.querySelectorAll('[data-updates] input[type=checkbox]')].forEach(cb => {
    cb.onclick = (e) => e.stopPropagation();
    cb.onchange = () => {
      const pkg = cb.dataset.pkg, who = STATE.active;
      if (!STATE.holds[who]) STATE.holds[who] = new Set();
      if (cb.checked) { STATE.holds[who].delete(pkg); holdWrite(who, pkg, false); }
      else { STATE.holds[who].add(pkg); holdWrite(who, pkg, true); }
    };
  });

  // historie
  renderHist();
  $("foot").innerHTML = `<span>SYSDASH \u00b7 ${esc(label(STATE.active))} \u00b7 ${off ? "offline" : "healthy"}</span><span>\u25CF ${DEMO ? "demo" : "live"}</span>`;
}

function renderHist() {
  const metrics = [["cpu", "CPU"], ["temp", "TEMP"], ["battery", "ACCU"], ["net_rx", "NET"]];
  const has = m => STATE.hist.some(r => r[m] != null);
  const avail = metrics.filter(([m]) => m === "cpu" || m === "temp" || has(m));
  if (!avail.some(([m]) => m === STATE.histMetric)) STATE.histMetric = "cpu";
  const seg = avail.map(([m, l]) => `<span class="${m === STATE.histMetric ? "on" : ""}" data-m="${m}">${l}</span>`).join("");
  const pts = STATE.hist.map(r => num(r[STATE.histMetric])).filter(v => !isNaN(v));
  $("hist").innerHTML = `<div class="hh"><div class="ht">HISTORIE \u2014 ${STATE.hist.length ? STATE.hist.length + " metingen" : "geen data"}</div><div class="seg">${seg}</div></div>${sparkSVG(pts)}`;
  [...document.querySelectorAll(".seg span")].forEach(s => s.onclick = () => { STATE.histMetric = s.dataset.m; renderHist(); });
}
function sparkSVG(pts) {
  const W = 600, H = 96;
  if (pts.length < 2) return `<svg class="spark" viewBox="0 0 ${W} ${H}"><text x="20" y="50" fill="#6b8bad" font-size="12" font-family="monospace">nog te weinig data</text></svg>`;
  const mn = Math.min(...pts), mx = Math.max(...pts), rng = (mx - mn) || 1, n = pts.length;
  const xs = i => i * (W / (n - 1)), ys = v => H - 8 - ((v - mn) / rng) * (H - 20);
  let d = `M ${xs(0)} ${ys(pts[0]).toFixed(1)}`;
  for (let i = 1; i < n; i++) { const x = xs(i), px = xs(i - 1); d += ` C ${((px + x) / 2).toFixed(1)} ${ys(pts[i - 1]).toFixed(1)}, ${((px + x) / 2).toFixed(1)} ${ys(pts[i]).toFixed(1)}, ${x.toFixed(1)} ${ys(pts[i]).toFixed(1)}`; }
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#00d4ff" stop-opacity=".38"/><stop offset="1" stop-color="#00d4ff" stop-opacity="0"/></linearGradient></defs><path d="${d} L ${W} ${H} L 0 ${H} Z" fill="url(#sg)"/><path d="${d}" fill="none" stroke="#00d4ff" stroke-width="2.2" style="filter:drop-shadow(0 0 4px #00d4ff)"/></svg>`;
}

// ── start + auto-refresh ──
async function tick() {
  refreshStatus();
  try { await loadCore(); if (!STATE.active) { STATE.active = STATE.machines.some(m=>m.machine===new URLSearchParams(location.search).get('machine')) ? new URLSearchParams(location.search).get('machine') : (STATE.machines[0]||{}).machine; await loadHist(); } await loadHist(); if(!STATE.updatesOpen&&!STATE.mgmtFocus) render(); }
  catch (e) { document.querySelector(".app").insertBefore(el("div", "err", "Kan Supabase niet lezen: " + esc(e.message) + "<br>Controleer de hubdienst en de Supabase-verbinding."), $("topbar")); }
}
loadCore().then(async () => { STATE.active = STATE.machines.some(m=>m.machine===new URLSearchParams(location.search).get('machine')) ? new URLSearchParams(location.search).get('machine') : (STATE.machines[0]||{}).machine; await loadHist(); await loadHolds(); await loadProfiles(); await loadActionLog(); await loadPerf(); await loadMode(STATE.active); render(); setInterval(tick, 30000); const lbeat=()=>{ return loadLive().then(()=>{refreshStatus();if(!STATE.updatesOpen&&!STATE.mgmtFocus)render();}).catch(()=>{}); }; lbeat(); setInterval(lbeat, 2000); const pbeat=()=>{ return loadProfiles().then(()=>{if(!STATE.updatesOpen&&!STATE.mgmtFocus)render();}).catch(()=>{}); }; setInterval(pbeat, 6000); setInterval(()=>loadPerf().then(()=>{if(!STATE.updatesOpen&&!STATE.mgmtFocus)render();}).catch(()=>{}), 300000); procTick(); setInterval(procTick, 2000); })
  .catch(e => { document.querySelector(".app").insertBefore(el("div", "err", "Startfout: " + esc(e.message)), $("topbar")); });
// (LIVE-modus vervangt de 30s-tick zolang 'ie aan staat)

// ── DEMO-data (als config.js leeg is) ──
function demoData() {
  const now = new Date().toISOString();
  return {
    cfg: { disk_warn: 80, disk_alarm: 90, temp_alarm: 90, bat_min: 15, updates_many: 20, offline_min: 10 },
    machines: [{ machine: "laptop", label: "Laptop", kind: "laptop" }, { machine: "desktop", label: "Desktop", kind: "desktop" }],
    latest: {
      laptop: { machine: "laptop", ts: now, cpu: 8, mem: 45, disk: 76, swap: 0, temp: 43, freq: 1660, load1: 1.29, load5: 1.1, load15: 0.9,
        net_rx: 8500000, net_tx: 1200000, net_up: true, updates: 6, uptime: 100800, extra: { updates_list: [{name:"linux-image-6.8",risk:"rood",kind:"apt"},{name:"firefox",risk:"blauw",kind:"apt"},{name:"curl",risk:"blauw",kind:"apt"}] }, battery: 77, bat_plugged: false, bat_health: 34, bat_status: "Discharging",
        cores: [19, 23, 5, 2, 5, 3, 3, 2], core_temps: [43, 42, 40, 40], temps: { pch_skylake: 56, iwlwifi: 30, acpitz: 25 },
        top_procs: [{ name: "firefox", cpu: 14, mem: 6 }, { name: "claude", cpu: 6, mem: 4 }, { name: "n8n", cpu: 3, mem: 2 }, { name: "kworker", cpu: 2, mem: 0 }] },
      desktop: { machine: "desktop", ts: now, cpu: 12, mem: 30, disk: 22, swap: 0, temp: 44, freq: 4286, load1: 0.4, load5: 0.5, load15: 0.6,
        net_rx: 2000000, net_tx: 400000, net_up: true, updates: 0, uptime: 320400, cores: [12, 9, 8, 7, 3, 2, 2, 1], core_temps: [44, 42, 41, 42], temps: { nvme: 39, acpitz: 28 },
        top_procs: [{ name: "chrome", cpu: 9, mem: 5 }, { name: "n8n", cpu: 4, mem: 3 }] }
    }
  };
}
function demoHist() { const out = []; for (let i = 0; i < 48; i++) out.push({ ts: new Date(Date.now() - (48 - i) * 18e5).toISOString(), cpu: 40 + 20 * Math.sin(i / 4) + (i % 5) * 3, temp: 42 + 6 * Math.sin(i / 6), battery: 60 + i % 30, net_rx: 2e6 + 1e6 * Math.random() }); return out; }
})();

// PWA: service worker registreren (stil falen als niet ondersteund)
if ("serviceWorker" in navigator) { window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(()=>{})); }
