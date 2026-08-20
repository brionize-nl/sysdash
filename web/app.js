/* SysDash v12 · dashboard-brein
   Leest Supabase (READ-ONLY anon-key), rendert het ontwerp met live data.
   Interactief: machine-tabs, detail-op-tik, historie-schakelaars, auto-refresh.
   Geen data ingesteld? → DEMO-modus (nep-data), zodat je 't kunt bekijken. */
(() => {
"use strict";
const CFG = window.SYSDASH_CONFIG || {};
const DEMO = !CFG.url || !CFG.anon;
// energieprofiel-knoppen via delegation (werkt ongeacht render-volgorde)
document.addEventListener("click", (e) => {
  const b = e.target.closest(".pbtn");
  if (b && b.dataset.mach && b.dataset.prof) { e.stopPropagation(); setProfile(b.dataset.mach, b.dataset.prof); }
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

let STATE = { machines: [], latest: {}, cfg: {}, active: null, hist: [], histMetric: "cpu", live: {}, liveStale: false, updatesOpen: false, holds: {}, statusOpen: false, profiles: {}, profileWish: {} };
let LIVE_TIMER = null;

// ── Supabase REST ──
async function api(path) {
  const r = await fetch(`${CFG.url}/rest/v1/${path}`, {
    headers: { apikey: CFG.anon, Authorization: `Bearer ${CFG.anon}` }
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

function holdWrite(machine, pkg, hold) {
  if (DEMO) return;
  if (hold) {
    fetch(CFG.url + "/rest/v1/update_holds", {
      method: "POST",
      headers: { apikey: CFG.anon, Authorization: "Bearer " + CFG.anon, "Content-Type": "application/json", Prefer: "resolution=merge-duplicates,return=minimal" },
      body: JSON.stringify({ machine, package: pkg })
    }).catch(()=>{});
  } else {
    fetch(CFG.url + "/rest/v1/update_holds?machine=eq." + encodeURIComponent(machine) + "&package=eq." + encodeURIComponent(pkg), {
      method: "DELETE",
      headers: { apikey: CFG.anon, Authorization: "Bearer " + CFG.anon }
    }).catch(()=>{});
  }
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


function setProfile(machine, profile) {
  if (DEMO) { STATE.profileWish = STATE.profileWish || {}; STATE.profileWish[machine] = profile; render(); return; }
  fetch(CFG.url + "/rest/v1/machine_actions?on_conflict=machine", {
    method: "POST",
    headers: { apikey: CFG.anon, Authorization: "Bearer " + CFG.anon, "Content-Type": "application/json", Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({ machine, power_profile: profile, updated_at: new Date().toISOString() })
  }).then(()=>{ STATE.profileWish = STATE.profileWish || {}; STATE.profileWish[machine] = profile; render(); }).catch(()=>{});
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
  const rows = await api(`metrics?machine=eq.${m}&select=ts,cpu,temp,battery,net_rx&order=ts.desc&limit=120`);
  STATE.hist = rows.reverse();
}

// ── helpers ──
const TH = () => STATE.cfg || {};
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
    const liveFields = {};
    ["cpu","mem","temp","freq","cores","core_temps","top_procs"].forEach(k => { if (r[k] !== undefined && r[k] !== null) liveFields[k] = r[k]; });
    STATE.latest[r.machine] = { ...base, ...liveFields };
  });
}
function setLive(){}

// ── render ──
function render() {
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
    <div class="topright"><div class="clock">${hhmm()}<small>${nOn}/${machs.length} online</small></div></div>`;

  // tabs
  $("tabs").innerHTML = "";
  STATE.machines.forEach(x => {
    const t = el("div", "tab" + (x.machine === STATE.active ? " on" : ""), esc((x.label || x.machine).toUpperCase()));
    if (!online(STATE.latest[x.machine])) t.innerHTML += ' <span class="hi">\u25B2</span>';
    t.onclick = () => { STATE.active = x.machine; loadHist().then(render); };
    $("tabs").appendChild(t);
  });
const sp = document.getElementById("statuspill"); if (sp) sp.onclick = (e) => { e.stopPropagation(); STATE.statusOpen = !STATE.statusOpen; sp.classList.toggle("open", STATE.statusOpen); };

  const off = !online(d);
  // netwerk
  const rx = num(d.net_rx), tx = num(d.net_tx);
  const spd = b => isNaN(b) ? "\u2014" : (b > 1e6 ? (b / 1e6).toFixed(1) + " <span class='u'>MB/s</span>" : Math.round(b / 1e3) + " <span class='u'>kB/s</span>");
  const netUp = d.net_up !== false && !off;
  const procs = asArr(d.top_procs) || [];
  $("net").innerHTML = `
    <div class="netgrid">
      <div class="nstat"><div class="nl">INTERNET</div><div class="nv"><span class="${netUp ? "ok" : "hi"}">${netUp ? "\u2713" : "\u25B2"}</span> ${netUp ? "Online" : "Weg"}</div></div>
      <div class="nstat"><div class="nl">STATUS</div><div class="nv"><span class="${off ? "hi" : "ok"}">${off ? "\u25B2" : "\u2713"}</span> ${off ? "offline" : "actief"}</div></div>
      <div class="nstat"><div class="nl">DOWNLOAD</div><div class="nv">\u2193 ${spd(rx)}</div></div>
      <div class="nstat"><div class="nl">UPLOAD</div><div class="nv">\u2191 ${spd(tx)}</div></div>
    </div>
    <div class="procs"><div class="pt">TOP PROCESSEN NU</div>${procs.length ? procs.map(p => {
      const c = Math.max(0, Math.min(100, num(p.cpu) || 0));
      return `<div class="prow"><span class="pn">${esc(p.name)}</span><span class="pb"><span class="pf" style="width:${c}%"></span></span><span class="pp">${isNaN(num(p.cpu)) ? "" : Math.round(p.cpu) + "%"}</span></div>`;
    }).join("") : '<div class="prow"><span class="pn" style="color:var(--muted)">geen data</span></div>'}</div>`;

  // ringen
  const cpu = num(d.cpu), mem = num(d.mem), disk = num(d.disk);
  // CPU-frequentie als subtekst (freq komt binnen in MHz)
  const freqVal = num(d.freq);
  const cpuSub = isNaN(freqVal) ? "" : (freqVal/1000).toFixed(2) + " GHz";
  // RAM in GB: mem% van totaal (uit hardware.ram_gb)
  let ramSub = "";
  const ramTot = d.extra && d.extra.hardware && d.extra.hardware.ram_gb;
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
    ${(d.extra && d.extra.hardware) ? `<div class="cpanel"><div class="ph">HARDWARE <span class="ok">\u2713</span></div><div class="misc">
      ${d.extra.hardware.cpu ? `<div class="m hw"><span class="n">CPU</span><span class="v">${esc(d.extra.hardware.cpu)}</span></div>` : ""}
      ${d.extra.hardware.ram_str ? `<div class="m hw"><span class="n">RAM</span><span class="v">${esc(d.extra.hardware.ram_str)}</span></div>` : ""}
      ${d.extra.hardware.disk ? `<div class="m hw"><span class="n">Schijf</span><span class="v">${esc(d.extra.hardware.disk)}</span></div>` : ""}
    </div></div>` : ""}
    ${(() => {
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
    })()}`;

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
    ? `<div class="updhint">Uitvinken = deze update overslaan om 19:00. (Lijst staat stil zolang open.)</div>` +
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
          return `<label class="updrow ${risk}"><input type="checkbox" data-pkg="${esc(key)}" ${heldSet.has(key) ? "" : "checked"}><span class="usym">${sym}</span><span class="uname">${esc(shown)}${isFlat ? ` <em class="flatpill">flatpak</em>` : ""}</span></label>`;
        })()
      ).join("") + `</div>`
    : (isNaN(upd) ? "geen data" : "alles up-to-date");
  chips.push({ id: "updates", label: "UPDATES", sym: isNaN(upd) ? "ok" : (upd > (TH().updates_many ?? 20) ? "high" : (upd > 0 ? "warn" : "ok")), val: isNaN(upd) ? "\u2014" : (upd <= 0 ? "0" : upd), tap: isNaN(upd) ? "" : (upd <= 0 ? "up-to-date" : upd + " klaar"), detail: updDetail });
  const needsReboot = d.extra && d.extra.reboot_required;
  chips.push({ label: "UPTIME", sym: needsReboot ? "high" : "ok", val: upStr, tap: needsReboot ? "\u25B2 herstart nodig" : "sinds herstart", detail: needsReboot ? `<b class="rbwarn">\u25B2 HERSTART NODIG</b><br>Een update wacht op een herstart. Doe dit op een rustig moment (kernel/systeem).<br><br>Laatste meting: ${d.ts ? hhmm(d.ts) : "?"}` : `Laatste meting: ${d.ts ? hhmm(d.ts) : "?"}` });
  chips.push({ label: "LOAD", sym: "ok", val: isNaN(num(d.load1)) ? "\u2014" : num(d.load1).toFixed(2), tap: "1-min gemiddelde", detail: `1m ${d.load1 ?? "?"} · 5m ${d.load5 ?? "?"} · 15m ${d.load15 ?? "?"}` });
  $("chips").innerHTML = chips.map(c => `
    <div class="chip glass ${c.id === "updates" && STATE.updatesOpen ? "open" : ""}" ${c.id ? `data-chip="${c.id}"` : ""}><div class="cl">${esc(c.label)} <span class="${sc[c.sym]}">${SYM[c.sym]}</span></div>
      <div class="cv">${esc(c.val)}</div><div class="tapd">${esc(c.tap || "tik voor detail")}</div>
      <div class="detail" ${c.id === "updates" ? 'data-updates="1"' : ""}>${c.detail || ""}</div></div>`).join("");
  [...document.querySelectorAll(".chip")].forEach(ch => {
    ch.onclick = (e) => {
      // klik op een checkbox/label binnen updates → niet de chip togglen
      if (e.target.closest("[data-updates]") && ch.dataset.chip === "updates") return;
      if (ch.dataset.chip === "updates") { STATE.updatesOpen = !STATE.updatesOpen; ch.classList.toggle("open"); }
      else ch.classList.toggle("open");
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
  try { await loadCore(); if (!STATE.active) { STATE.active = STATE.machines.find(m=>m.machine==='pro') ? 'pro' : (STATE.machines[0]||{}).machine; await loadHist(); } render(); }
  catch (e) { document.querySelector(".app").insertBefore(el("div", "err", "Kan Supabase niet lezen: " + esc(e.message) + "<br>Controleer <code>config.js</code> (URL + anon-key)."), $("topbar")); }
}
loadCore().then(async () => { STATE.active = STATE.machines.find(m=>m.machine==='pro') ? 'pro' : (STATE.machines[0]||{}).machine; await loadHist(); await loadHolds(); await loadProfiles(); render(); setInterval(tick, 30000); const lbeat=()=>{ if (STATE.updatesOpen) return; return loadLive().then(render).catch(()=>{}); }; lbeat(); setInterval(lbeat, 2000); const pbeat=()=>{ if (STATE.updatesOpen) return; return loadProfiles().then(render).catch(()=>{}); }; setInterval(pbeat, 6000); })
  .catch(e => { document.querySelector(".app").insertBefore(el("div", "err", "Startfout: " + esc(e.message)), $("topbar")); });
// (LIVE-modus vervangt de 30s-tick zolang 'ie aan staat)

// ── DEMO-data (als config.js leeg is) ──
function demoData() {
  const now = new Date().toISOString();
  return {
    cfg: { disk_warn: 80, disk_alarm: 90, temp_alarm: 90, bat_min: 15, updates_many: 20, offline_min: 10 },
    machines: [{ machine: "delli5", label: "Laptop", kind: "laptop" }, { machine: "pro", label: "Asus", kind: "desktop" }],
    latest: {
      delli5: { machine: "delli5", ts: now, cpu: 8, mem: 45, disk: 76, swap: 0, temp: 43, freq: 1660, load1: 1.29, load5: 1.1, load15: 0.9,
        net_rx: 8500000, net_tx: 1200000, net_up: true, updates: 6, uptime: 100800, extra: { updates_list: [{name:"linux-image-6.8",risk:"rood",kind:"apt"},{name:"firefox",risk:"blauw",kind:"apt"},{name:"curl",risk:"blauw",kind:"apt"}] }, battery: 77, bat_plugged: false, bat_health: 34, bat_status: "Discharging",
        cores: [19, 23, 5, 2, 5, 3, 3, 2], core_temps: [43, 42, 40, 40], temps: { pch_skylake: 56, iwlwifi: 30, acpitz: 25 },
        top_procs: [{ name: "firefox", cpu: 14, mem: 6 }, { name: "claude", cpu: 6, mem: 4 }, { name: "n8n", cpu: 3, mem: 2 }, { name: "kworker", cpu: 2, mem: 0 }] },
      pro: { machine: "pro", ts: now, cpu: 12, mem: 30, disk: 22, swap: 0, temp: 44, freq: 4286, load1: 0.4, load5: 0.5, load15: 0.6,
        net_rx: 2000000, net_tx: 400000, net_up: true, updates: 0, uptime: 320400, cores: [12, 9, 8, 7, 3, 2, 2, 1], core_temps: [44, 42, 41, 42], temps: { nvme: 39, acpitz: 28 },
        top_procs: [{ name: "chrome", cpu: 9, mem: 5 }, { name: "n8n", cpu: 4, mem: 3 }] }
    }
  };
}
function demoHist() { const out = []; for (let i = 0; i < 48; i++) out.push({ ts: new Date(Date.now() - (48 - i) * 18e5).toISOString(), cpu: 40 + 20 * Math.sin(i / 4) + (i % 5) * 3, temp: 42 + 6 * Math.sin(i / 6), battery: 60 + i % 30, net_rx: 2e6 + 1e6 * Math.random() }); return out; }
})();

// PWA: service worker registreren (stil falen als niet ondersteund)
if ("serviceWorker" in navigator) { window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(()=>{})); }
