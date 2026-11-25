// Solar Dashboard – frontend (ingen build-trin, ren ES-modul)
import { icon } from "./icons.js";
import { carSVG } from "./car.js";
import { wxIcon, WeatherFX } from "./wx.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
if (params.has("lite")) document.body.classList.add("lite");
if (params.has("kiosk")) document.body.classList.add("kiosk");

// ---------------------------------------------------------------- formatering
const NF = {};
const nf = (d) => (NF[d] ||= new Intl.NumberFormat("da-DK", { minimumFractionDigits: d, maximumFractionDigits: d }));
const num = (v, d = 1) => (v == null || Number.isNaN(+v) ? "–" : nf(d).format(Math.abs(v) < 0.5 * 10 ** -d ? 0 : v));
const kW = (w, d) => (w == null ? "–" : num(Math.abs(w) / 1000, d ?? (Math.abs(w) >= 10000 ? 0 : 1)));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const DAYS = ["Søndag", "Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag"];
const MONTHS = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november", "december"];
const dur = (min) => {
  if (min == null) return "–";
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h ? `${h} t ${pad(m)} m` : `${m} min`;
};
const GRAD = {
  sun: "linear-gradient(135deg,#ffc14d,#ff7a2f)",
  green: "linear-gradient(135deg,#4ade80,#059669)",
  teal: "linear-gradient(135deg,#2dd4bf,#0e7490)",
  blue: "linear-gradient(135deg,#60a5fa,#1d4ed8)",
  red: "linear-gradient(135deg,#fb7185,#be123c)",
  violet: "linear-gradient(135deg,#c4b5fd,#7c3aed)",
  amber: "linear-gradient(135deg,#fcd34d,#d97706)",
  slate: "linear-gradient(135deg,#94a3b8,#475569)",
};

function setHTML(el, html) {
  if (el && el._html !== html) {
    el.innerHTML = html;
    el._html = html;
  }
}

// ---------------------------------------------------------------- tilstand
let S = null;
let serverOffset = 0;
let lastOk = 0;
let fetchError = null;

async function poll() {
  try {
    const r = await fetch("api/state", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    S = await r.json();
    if (S.server_time) {
      const off = Date.parse(S.server_time) - Date.now();
      serverOffset = Math.abs(off) > 30000 ? off : 0; // ret kun tabletten hvis dens ur er meget forkert
    }
    lastOk = Date.now();
    fetchError = null;
    render();
  } catch (e) {
    fetchError = String(e.message || e);
    renderDock();
  } finally {
    const sec = (S && S.ui && S.ui.refresh_seconds) || 5;
    setTimeout(poll, sec * 1000);
  }
}

const now = () => new Date(Date.now() + serverOffset);

// ---------------------------------------------------------------- ur
let lastClock = "";
function tickClock() {
  const d = now();
  const t = hhmm(d);
  const date = `${DAYS[d.getDay()]} ${d.getDate()}. ${MONTHS[d.getMonth()]}`;
  if (t + date !== lastClock) {
    $("clockTime").textContent = t;
    $("clockDate").textContent = date;
    lastClock = t + date;
    const h = d.getHours();
    const nd = S?.ui?.night_dim;
    document.body.classList.toggle("night", Array.isArray(nd) && (nd[0] > nd[1] ? h >= nd[0] || h < nd[1] : h >= nd[0] && h < nd[1]));
  }
}

// ---------------------------------------------------------------- render
function render() {
  if (!S) return;
  renderWxTile();
  renderWeather();
  renderFlow();
  renderPrice();
  renderToday();
  renderCameras();
  renderCar();
  renderDevices();
  renderDock();
}

function derived() {
  const so = S.solar || {};
  const ch = S.charger || {};
  const car = S.car || {};
  let carW = 0;
  if (ch.ok && ch.power_kw != null) carW = ch.power_kw * 1000;
  else if (car.charging && car.charge_power_kw) carW = car.charge_power_kw * 1000;
  const load = so.load_w;
  // bilens effekt trækkes kun fra husets forbrug når begge tal er rigtige (eller begge er demo)
  const sameSource = !!so.demo === !!(ch.ok ? ch.demo : car.demo);
  const house = load != null ? Math.max(load - (sameSource ? carW : 0), 0) : null;
  return { so, ch, car, carW, house, charging: carW > 100 || !!car.charging || ch.state === "charging" };
}

// ---------- vejr-flise (øverst til venstre)
function renderWxTile() {
  const w = S.weather, t = $("wxTile");
  if (!w || !w.current) { setHTML(t, ""); t.hidden = true; return; }
  t.hidden = false;
  const c = w.current, d0 = (w.daily || [])[0];
  t.dataset.fx = c.effect || "none";
  t.classList.toggle("night", c.is_day === false);
  setHTML(t, `<div class="wx-scene"><i></i><i></i><i></i><i></i><i></i><i></i></div>
    <div class="wx-tile-ic">${wxIcon(c.icon, c.is_day)}</div>
    <div class="wx-tile-txt">
      <div class="wx-tile-temp">${num(c.temp, 0)}°</div>
      <div class="wx-tile-text">${esc(c.text)}</div>
      <div class="wx-tile-sub">${d0 ? `↑ ${num(d0.max, 0)}°  ↓ ${num(d0.min, 0)}° · ` : ""}vind ${num(c.wind, 0)} m/s</div>
    </div>`);
}

// ---------- energiflow
const FLOW_POS = {
  sol: { x: 0.5, y: 0.14, ic: "sun", c: "#ffb340", lbl: "Sol", side: "right" },
  net: { x: 0.1, y: 0.47, ic: "utility-pole", c: "#ff7a9a", lbl: "Net" },
  hus: { x: 0.9, y: 0.47, ic: "house", c: "#9cc4ff", lbl: "Hus" },
  bat: { x: 0.3, y: 0.85, ic: "battery-medium", c: "#34d399", lbl: "Batteri", side: "left" },
  bil: { x: 0.7, y: 0.85, ic: "car-front", c: "#5ad7ff", lbl: "Bil", side: "right" },
};
const HUB = { x: 0.5, y: 0.47 };
let flowSize = "";

function buildFlow() {
  const box = $("flow");
  const W = box.clientWidth, H = box.clientHeight;
  if (!W || !H) return;
  const nodes = Object.entries(FLOW_POS).map(([k, p]) => `
    <div class="node ${p.side ? "side-label" : ""} ${p.side === "left" ? "right" : ""}" id="n-${k}" style="left:${p.x * 100}%;top:${p.y * 100}%;--c:${p.c}">
      <div class="node-ic">${icon(p.ic)}</div>
      <div><div class="node-val" id="v-${k}">–</div><div class="node-lbl" id="l-${k}">${p.lbl}</div></div>
    </div>`).join("");
  $("flowNodes").innerHTML = nodes + `<div class="node hub" style="left:${HUB.x * 100}%;top:${HUB.y * 100}%"><div class="node-ic">${icon("zap")}</div></div>`;

  // side-labels skal ikke flytte ikonets centrum: forskyd noden så ikonet sidder på positionen
  for (const [k, p] of Object.entries(FLOW_POS)) {
    if (!p.side) continue;
    const el = $(`n-${k}`), ic = el.querySelector(".node-ic");
    const shift = el.offsetWidth / 2 - ic.offsetWidth / 2;
    el.style.transform = `translate(calc(-50% ${p.side === "right" ? "+" : "-"} ${shift}px), -50%)`;
  }
  const r = (k) => $(`n-${k}`).querySelector(".node-ic").offsetWidth / 2 + 4;
  const rh = $("flowNodes").querySelector(".hub .node-ic").offsetWidth / 2 + 4;
  const hx = HUB.x * W, hy = HUB.y * H;
  const paths = {};
  for (const [k, p] of Object.entries(FLOW_POS)) {
    const nx = p.x * W, ny = p.y * H, rn = r(k);
    let d;
    if (k === "bat" || k === "bil") {
      const sx = hx + (nx < hx ? -rh : rh);
      d = `M${sx},${hy} Q${nx},${hy} ${nx},${ny - rn}`;
    } else {
      const dx = nx - hx, dy = ny - hy, L = Math.hypot(dx, dy);
      d = `M${hx + (dx / L) * rh},${hy + (dy / L) * rh} L${nx - (dx / L) * rn},${ny - (dy / L) * rn}`;
    }
    paths[k] = d;
  }
  $("flowSvg").setAttribute("viewBox", `0 0 ${W} ${H}`);
  $("flowSvg").innerHTML = Object.entries(paths).map(([k, d]) =>
    `<path class="flow-base" d="${d}"/><path class="flow-anim" id="p-${k}" d="${d}" style="display:none"/>`).join("");
  flowSize = `${W}x${H}`;
}

function setFlow(k, watts, dir, color) {
  const p = $(`p-${k}`);
  const node = $(`n-${k}`);
  if (!p) return;
  const active = watts != null && Math.abs(watts) > 30;
  p.style.display = active ? "" : "none";
  node.classList.toggle("active", active);
  if (!active) return;
  const kw = Math.abs(watts) / 1000;
  const d = [2.2, 1.6, 1.2, 0.9, 0.7, 0.5][Math.min(5, Math.floor(Math.log2(1 + kw * 2)))];
  p.style.setProperty("--dur", `${d}s`);
  p.style.setProperty("--c", color);
  p.style.stroke = color;
  p.classList.toggle("rev", dir === "in");
}

function renderFlow() {
  const { so, car, carW, house } = derived();
  const box = $("flow");
  if (`${box.clientWidth}x${box.clientHeight}` !== flowSize) buildFlow();
  const tag = $("flowTag");
  tag.className = "tag " + (so.demo ? "demo" : so.ok === false ? "err" : "green");
  tag.innerHTML = so.demo ? "Demo" : so.ok === false ? `${icon("wifi-off")} Ingen forbindelse` : `<span class="dot pulse"></span> Live`;

  const msg = $("flowMsg");
  msg.hidden = !(so.ok === false && so.error);
  if (!msg.hidden) msg.textContent = so.error;
  const g = so.grid_w, b = so.battery_w;
  $("v-sol").textContent = `${kW(so.pv_w)} kW`;
  $("v-net").textContent = `${kW(g)} kW`;
  $("l-net").textContent = g == null ? "Net" : g < -30 ? "Salg til net" : g > 30 ? "Køb fra net" : "Net";
  $("v-hus").textContent = `${kW(house)} kW`;
  $("v-bat").textContent = so.has_battery === false ? "–" : `${num(so.battery_soc, 0)} %`;
  $("l-bat").textContent = b == null || Math.abs(b) <= 30 ? "Batteri" : `${b > 0 ? "Lader" : "Aflader"} ${kW(b)} kW`;
  $("v-bil").textContent = carW > 30 ? `${kW(carW)} kW` : car.soc != null ? `${num(car.soc, 0)} %` : "–";
  $("l-bil").textContent = carW > 30 ? `${esc(car.name || "Bil")} · ${num(car.soc, 0)} %` : esc(car.name || "Bil");

  setFlow("sol", so.pv_w, "in", "#ffb340");
  setFlow("net", g, g > 0 ? "in" : "out", g > 0 ? "#ff7a9a" : "#4ade80");
  $("n-net").style.setProperty("--c", g != null && g < -30 ? "#4ade80" : "#ff7a9a");
  setFlow("bat", b, b > 0 ? "out" : "in", "#34d399");
  setFlow("hus", house, "out", "#9cc4ff");
  setFlow("bil", carW, "out", "#5ad7ff");
}

// ---------- batteri
function arcPath(cx, cy, r, a0, a1) {
  const p = (a) => [cx + r * Math.cos((a * Math.PI) / 180), cy + r * Math.sin((a * Math.PI) / 180)];
  const [x0, y0] = p(a0), [x1, y1] = p(a1);
  return `M${x0},${y0} A${r},${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1},${y1}`;
}

function batteryStrip() {
  const so = S.solar || {};
  if (so.has_battery === false) return "";
  const soc = so.battery_soc, st = so.battery_state, b = so.battery_w;
  const stTxt = { charging: "Lader", discharging: "Aflader", idle: "Hviler", fault: "Fejl" }[st] || "–";
  const col = st === "discharging" ? ["#ffd166", "#ff8a3d"] : st === "charging" ? ["#2dd4bf", "#4ade80"] : ["#60a5fa", "#a5b4fc"];
  const pct = Math.max(0, Math.min(100, soc ?? 0));
  const R = 20, C = 2 * Math.PI * R;
  const detail = b != null && Math.abs(b) > 30 ? `${stTxt} ${kW(b)} kW` : stTxt;
  const eta = so.battery_eta_min != null ? `${st === "charging" ? "Fuld" : "Tom"} om ${dur(so.battery_eta_min)}` : (so.battery_capacity_kwh && soc != null ? `${num((soc / 100) * so.battery_capacity_kwh, 1)} kWh` : "");
  return `<div class="batt-strip">
    <svg viewBox="0 0 52 52" class="batt-ring"><defs><linearGradient id="bg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="${col[0]}"/><stop offset="1" stop-color="${col[1]}"/></linearGradient></defs>
      <circle cx="26" cy="26" r="${R}" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="6"/>
      <circle cx="26" cy="26" r="${R}" fill="none" stroke="url(#bg)" stroke-width="6" stroke-linecap="round" stroke-dasharray="${(C * pct) / 100} ${C}" transform="rotate(-90 26 26)" style="filter:drop-shadow(0 0 4px ${col[1]}99)"/></svg>
    <div class="batt-soc">${num(soc, 0)}<small>%</small></div>
    <div class="batt-txt"><b>Batteri</b><span>${detail}</span>${eta ? `<em>${eta}</em>` : ""}</div>
  </div>`;
}

// ---------- elpris
function renderPrice() {
  const pr = S.prices || {};
  $("priceArea").textContent = pr.area || "";
  const tag = $("priceTag");
  if (!pr.ok || !pr.now) {
    tag.className = "tag err";
    tag.textContent = "Ingen data";
    setHTML($("priceBody"), `<div class="empty">${esc(pr.error || "Henter elpriser …")}</div>`);
    return;
  }
  const n = pr.now;
  const lv = { low: ["green", "Billig"], mid: ["amber", "Normal"], high: ["red", "Dyr"] }[n.level] || ["", ""];
  tag.className = "tag " + (pr.demo ? "demo" : lv[0]);
  tag.textContent = pr.demo ? "Demo" : lv[1];

  const parts = [
    ["Spot", n.spot, "#60a5fa"],
    ["Nettarif", n.nettarif, "#a78bfa"],
    ["Energinet", n.energinet, "#2dd4bf"],
    ["Elafgift", n.elafgift, "#fbbf24"],
    ["Tillæg", n.supplier, "#94a3b8"],
    ["Moms", n.vat, "#f472b6"],
  ].filter(([, v]) => v);
  const sumPos = parts.reduce((a, [, v]) => a + Math.max(v, 0), 0) || 1;
  const stack = parts.map(([, v, c]) => `<i style="width:${(Math.max(v, 0) / sumPos) * 100}%;background:${c}"></i>`).join("");
  const legend = parts.filter(([l]) => l !== "Tillæg" || n.supplier).map(([l, v, c]) => `<span><i style="background:${c}"></i>${l} ${num(v, 2)}</span>`).join("");

  // de næste 24 timer
  const startIdx = Math.max(pr.hours.findIndex((h) => h.start === n.start), 0);
  const hrs = pr.hours.slice(startIdx, startIdx + 24);
  const max = Math.max(...hrs.map((h) => h.total), 0.01);
  const ch = pr.cheapest;
  const inCheap = (h) => ch && h.start >= ch.start && Date.parse(h.start) < Date.parse(ch.end);
  const bars = hrs.map((h, i) => {
    const t = new Date(h.start);
    const lbl = i % 3 === 0 ? `<em>${pad(t.getHours())}</em>` : "";
    const newday = i > 0 && t.getHours() === 0 ? "newday" : "";
    return `<div class="bar ${h.level} ${i === 0 ? "now" : ""} ${inCheap(h) ? "cheap" : ""} ${newday}"><i style="height:${Math.max((h.total / max) * 100, 3)}%"></i>${lbl}</div>`;
  }).join("");
  const missingNet = n.nettarif == null && !pr.demo;
  const note = missingNet
    ? `${icon("circle-alert")} Nettarif mangler – vælg netselskab i config.yaml`
    : `Inkl. moms, elafgift og nettarif${pr.grid_company && pr.grid_company !== "demo" ? ` (${esc(pr.grid_company)})` : ""}`;
  const foot = ch
    ? `<span>${icon("leaf")} Billigst ${ch.hours} t: <b>${hhmm(new Date(ch.start))}–${hhmm(new Date(ch.end))}</b></span><span>gns. <b>${num(ch.avg, 2)} kr</b></span>`
    : "";
  setHTML($("priceBody"), `
    <div class="price-top">
      <div>
        <div class="price-big">${num(n.total, 2)}<small>kr/kWh</small></div>
        <div class="price-note">${note}</div>
      </div>
      <div class="price-sell">Salgspris<br><b>${num(n.sell, 2)} kr</b></div>
    </div>
    <div class="stack">${stack}</div>
    <div class="legend">${legend}</div>
    <div class="bars">${bars}</div>
    <div class="price-foot">${foot}</div>`);
  $("priceBody").style.display = "flex";
  $("priceBody").style.flexDirection = "column";
  $("priceBody").style.flex = "1";
  $("priceBody").style.minHeight = "0";
}

// ---------- i dag
function renderToday() {
  const en = S.energy || {};
  const tag = $("todayTag");
  tag.className = "tag green";
  tag.innerHTML = en.self_sufficiency != null ? `${icon("leaf")} ${en.self_sufficiency} % selvforsynet` : "";
  const hist = en.history || [];
  // spark-linje: produktion (område) og forbrug (linje)
  const W = 300, H = 90;
  const xOf = (t) => { const [h, m] = t.split(":").map(Number); return ((h * 60 + m) / 1440) * W; };
  const max = Math.max(0.5, ...hist.map((p) => Math.max(p.pv, p.load)));
  const yOf = (v) => H - (v / max) * (H - 6);
  let area = "", line = "";
  if (hist.length > 1) {
    area = `M${xOf(hist[0].t)},${H} ` + hist.map((p) => `L${xOf(p.t).toFixed(1)},${yOf(p.pv).toFixed(1)}`).join(" ") + ` L${xOf(hist[hist.length - 1].t)},${H} Z`;
    line = hist.map((p, i) => `${i ? "L" : "M"}${xOf(p.t).toFixed(1)},${yOf(p.load).toFixed(1)}`).join(" ");
  }
  const nowX = ((now().getHours() * 60 + now().getMinutes()) / 1440) * W;
  const ticks = [6, 12, 18].map((h) => `<line x1="${(h / 24) * W}" x2="${(h / 24) * W}" y1="0" y2="${H}" stroke="rgba(255,255,255,.08)" stroke-dasharray="2 3"/><text class="axis" x="${(h / 24) * W}" y="${H + 11}" text-anchor="middle">${pad(h)}</text>`).join("");
  const spark = `<svg viewBox="0 0 ${W} ${H + 12}" preserveAspectRatio="none">
      <defs><linearGradient id="gPv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb340" stop-opacity=".75"/><stop offset="1" stop-color="#ff8a3d" stop-opacity=".05"/></linearGradient></defs>
      ${ticks}
      <path d="${area}" fill="url(#gPv)"/>
      <path d="${line}" fill="none" stroke="#cfe0ff" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
      <line x1="${nowX}" x2="${nowX}" y1="0" y2="${H}" stroke="rgba(255,255,255,.5)" stroke-width="1" vector-effect="non-scaling-stroke"/>
    </svg>`;
  const kr = (v) => `${num(v, 2)} kr`;
  setHTML($("todayBody"), `
    ${batteryStrip()}
    <div class="spark">${spark}</div>
    <div class="stats">
      <div class="stat"><div class="stat-l" style="color:#ffd08a">${icon("sun")} Produceret</div><div class="stat-v">${num(en.pv_kwh, 1)}<small>kWh</small></div></div>
      <div class="stat"><div class="stat-l" style="color:#cfe0ff">${icon("house")} Forbrug</div><div class="stat-v">${num(en.load_kwh, 1)}<small>kWh</small></div></div>
      <div class="stat"><div class="stat-l" style="color:#86efac">${icon("arrow-up-from-line")} Solgt</div><div class="stat-v">${num(en.export_kwh, 1)}<small>kWh</small></div><div class="stat-s">+ ${kr(en.export_dkk)}</div></div>
      <div class="stat"><div class="stat-l" style="color:#fda4af">${icon("arrow-down-to-line")} Købt</div><div class="stat-v">${num(en.import_kwh, 1)}<small>kWh</small></div><div class="stat-s">− ${kr(en.import_dkk)}</div></div>
    </div>`);
  $("todayBody").style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0";
}

// ---------- bil
const CAR_STATE = {
  charging: ["blue", "Lader"],
  ready_for_charging: ["", "Klar til opladning"],
  conservation: ["green", "Holder niveau"],
  off: ["", "Lader ikke"],
  error: ["red", "Ladefejl"],
  discharging: ["amber", "Afgiver strøm"],
};
const CHARGER_STATE = {
  charging: "Lader", idle: "Ledig", connected: "Tilsluttet", waiting: "Venter", paused: "Pause", finished: "Færdig", fault: "Fejl",
};

function renderCar() {
  const { car, ch, carW, charging } = derived();
  const pr = S.prices || {};
  const name = esc(car.name || S.ui?.car_name || "ID.3");
  const demo = car.demo || ch.demo;
  setHTML($("carTitle"), `${name}${demo ? ' <small>DEMO</small>' : ""}`);
  const tag = $("carTag");
  let [cls, txt] = CAR_STATE[car.charging_state] || ["", ""];
  if (charging) [cls, txt] = ["blue", "Lader"];
  else if (car.plug === "disconnected" || (!car.ok && ch.state === "idle")) [cls, txt] = ["", "Ikke tilsluttet"];
  else if (!txt && ch.state) txt = CHARGER_STATE[ch.state] || ch.state;
  if (car.ok === false && !ch.ok) [cls, txt] = ["err", "Ingen forbindelse"];
  tag.className = "tag " + cls;
  tag.innerHTML = charging ? `<span class="dot pulse"></span> ${txt}` : txt;

  const btn = $("chargerBtn");
  if (ch.ok && ch.switch_code) {
    btn.hidden = false;
    btn.classList.toggle("on", !!ch.on);
    setHTML(btn, icon("power"));
    btn.title = ch.on ? "Stop lader" : "Start lader";
  } else btn.hidden = true;

  const soc = car.soc;
  const target = car.target_soc;
  const eta = car.eta ? new Date(car.eta) : null;
  const heating = ["heating", "ventilation", "cooling"].includes(car.climatization);
  const climBtn = `<button class="mini mini-btn ${heating ? "on" : ""}" id="climBtn">${icon(heating ? "flame" : "thermometer-sun")}<b>${heating ? "Varmer" : "Varm op"}</b><span>${heating ? "Tryk for at stoppe" : "Kabine"}</span></button>`;
  let minis;
  if (charging) {
    minis = [
      ["zap", carW ? `${kW(carW)} kW` : "–", "Ladeeffekt"],
      ["clock", eta ? hhmm(eta) : "–", "Færdig ca."],
    ];
  } else {
    const cw = pr.cheapest;
    minis = [
      ["plug", car.plug === "connected" ? "I stik" : car.plug === "disconnected" ? "Ikke i stik" : CHARGER_STATE[ch.state] || "–", "Stik"],
      ["leaf", cw ? `${hhmm(new Date(cw.start))}–${hhmm(new Date(cw.end))}` : "–", "Billigst at lade"],
    ];
  }
  if (dragging) return;
  // VW er nede (eller demo), men der er en rigtig Tuya-lader: vis det laderen kan fortælle
  if (ch.ok && !ch.demo && (!car.ok || car.demo)) {
    const stateTxt = charging ? "Lader" : (CHARGER_STATE[ch.state] || ch.state || "–");
    const sub = charging ? `${kW(carW, 1)} kW` : ch.state === "finished" ? "Opladning færdig" : ch.state === "connected" ? "Bilen er i stik" : ch.state === "idle" ? "Ingen bil i stik" : "";
    const cw = pr.cheapest;
    const mini = [
      ["zap", carW ? `${kW(carW)} kW` : "0 kW", "Ladeeffekt"],
      ["plug-zap", ch.session_kwh != null ? `${num(ch.session_kwh, 1)} kWh` : "–", "Denne opladning"],
      ch.current_a != null ? ["activity", `${num(ch.current_a, 0)} A`, "Ladestrøm"] : ["leaf", cw ? `${hhmm(new Date(cw.start))}–${hhmm(new Date(cw.end))}` : "–", "Billigst at lade"],
    ];
    setHTML($("carBody"), `
      <div class="car-main">
        <div><div class="car-soc car-state">${stateTxt}</div><div class="car-range">${sub}</div></div>
        <div class="car-img">${carSVG(charging)}</div>
      </div>
      <div class="car-bar ${charging ? "charging" : ""}"><i style="width:${charging ? 100 : 0}%"></i></div>
      <div class="car-mini">${mini.map(([i, v, l]) => `<div class="mini">${icon(i)}<b>${v}</b><span>${l}</span></div>`).join("")}</div>
      <div class="car-note">Data fra laderen · bilens batteri er ikke tilgængeligt</div>`);
    $("carBody").style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0";
    return;
  }
  setHTML($("carBody"), `
    <div class="car-main">
      <div>
        <div class="car-soc">${num(soc, 0)}<small>%</small></div>
        <div class="car-range">${car.range_km != null ? `${num(car.range_km, 0)} km rækkevidde` : car.error ? esc(car.error).slice(0, 60) : ""}</div>
      </div>
      <div class="car-img">${carSVG(charging)}</div>
    </div>
    <div class="car-bar ${charging ? "charging" : ""}">
      <i style="width:${Math.max(0, Math.min(100, soc ?? 0))}%"></i>
      ${target ? `<div class="target" id="carTarget" style="left:${target}%"><span>Mål ${num(target, 0)} %</span></div>` : ""}
    </div>
    <div class="car-mini">${minis.map(([i, v, l]) => `<div class="mini">${icon(i)}<b>${v}</b><span>${l}</span></div>`).join("")}${car.ok !== false ? climBtn : ""}</div>`);
  $("carBody").style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0";
}

// ---------- klima-knap
$("carBody").addEventListener("click", async (e) => {
  const b = e.target.closest("#climBtn");
  if (!b || b.disabled) return;
  const turnOn = !b.classList.contains("on");
  b.disabled = true;
  b.classList.toggle("on", turnOn);
  try {
    const r = await fetch("api/car/climate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: turnOn }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
    if (S?.car) S.car.climatization = turnOn ? "heating" : "off";
    toast(turnOn ? "Opvarmning af kabinen startet" : "Opvarmning stoppet");
  } catch (err) {
    toast(`Kunne ikke styre klimaet: ${err.message}`);
  } finally {
    renderCar();
  }
});

// ---------- træk i ladegrænsen
let dragging = false;
$("carBody").addEventListener("pointerdown", (e) => {
  const t = e.target.closest("#carTarget");
  if (!t) return;
  e.preventDefault();
  dragging = true;
  const bar = t.parentElement, rect = bar.getBoundingClientRect();
  let val = parseFloat(t.style.left);
  const move = (ev) => {
    const raw = ((ev.clientX - rect.left) / rect.width) * 100;
    val = Math.max(50, Math.min(100, Math.round(raw / 10) * 10));
    t.style.left = val + "%";
    t.querySelector("span").textContent = `Mål ${val} %`;
  };
  const up = async () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
    try {
      const r = await fetch("api/car/target", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ level: val }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
      if (S?.car) S.car.target_soc = val;
      toast(`Bilen lader nu til ${val} %`);
    } catch (err) {
      toast(`Kunne ikke ændre ladegrænsen: ${err.message}`);
    } finally {
      dragging = false;
      renderCar();
    }
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
});

// ---------- kameraer
let camKey = "";
const camSrc = (id, w, fps) => `api/camera/${encodeURIComponent(id)}/stream?w=${w}&fps=${fps}&t=${Date.now()}`;
function camStart(img) {
  img.dataset.live = "1";
  img.classList.remove("err");
  img.src = camSrc(img.dataset.id, 480, 4);
}
function camStop(img) { img.dataset.live = ""; img.removeAttribute("src"); }

function renderCameras() {
  const cam = S.cameras || {};
  const items = cam.items || [];
  const tag = $("camTag");
  tag.className = "tag " + (cam.demo ? "demo" : items.length ? "green" : "");
  tag.innerHTML = cam.demo ? "Demo" : items.length ? `<span class="dot pulse"></span> Live` : "";
  const grid = $("camGrid");
  const key = items.map((c) => c.id + c.name).join("|").slice(0, 400);
  if (key === camKey) return;  // billederne må ikke genstartes ved hver opdatering
  camKey = key;
  if (!items.length) {
    grid.className = "cam-grid";
    grid.innerHTML = `<div class="empty">Ingen kameraer fundet i Tuya.<br>Tilføj dem i Smart Life-appen.</div>`;
    return;
  }
  const shown = items.slice(0, 4);
  grid.className = "cam-grid n" + shown.length;
  grid.innerHTML = shown.map((c) => `<button class="cam" data-id="${esc(c.id)}" aria-label="${esc(c.name)}">
      <img data-id="${esc(c.id)}" alt="" draggable="false"><div class="cam-off">${icon("cctv")}<span>Henter …</span></div>
      <div class="cam-name">${esc(c.name)}</div></button>`).join("");
  grid.querySelectorAll("img").forEach((img) => {
    img.addEventListener("load", () => img.parentElement.classList.add("ok"));
    img.addEventListener("error", async () => {
      if (!img.dataset.live) return;
      const box = img.parentElement;
      box.classList.remove("ok");
      let msg = "Ingen forbindelse";
      try {  // find ud af hvorfor: serveren svarer med årsagen
        const ctl = new AbortController();
        const r = await fetch(camSrc(img.dataset.id, 160, 1), { signal: ctl.signal });
        if (!r.ok) msg = (await r.json().catch(() => ({}))).detail || `Fejl ${r.status}`;
        ctl.abort();
      } catch { /* ignorer */ }
      box.querySelector(".cam-off span").textContent = msg.length > 120 ? msg.slice(0, 117) + "…" : msg;
      setTimeout(() => img.dataset.live && !document.hidden && camStart(img), 30000);
    });
    camStart(img);
  });
}
$("camGrid").addEventListener("click", (e) => {
  const b = e.target.closest(".cam");
  if (!b) return;
  const big = $("camBig");
  $("camBigName").textContent = b.querySelector(".cam-name").textContent;
  big.src = camSrc(b.dataset.id, 960, 8);
  $("camModal").hidden = false;
});
const camClose = () => { $("camBig").removeAttribute("src"); $("camModal").hidden = true; };
$("camClose").addEventListener("click", camClose);
$("camModal").addEventListener("click", (e) => { if (e.target === $("camModal")) camClose(); });
// spar båndbredde og CPU når siden ikke vises
document.addEventListener("visibilitychange", () => {
  document.querySelectorAll("#camGrid img").forEach((img) => (document.hidden ? camStop(img) : camStart(img)));
  if (document.hidden) camClose();
});

// ---------- enheder
const DEV_COLOR = { lightbulb: "#f59e0b", "lamp-ceiling": "#f59e0b", "lamp-floor": "#f59e0b", lamp: "#f59e0b", sun: "#f59e0b",
  plug: "#2563eb", "toggle-right": "#2563eb", zap: "#2563eb", tv: "#7c3aed", coffee: "#b45309", "washing-machine": "#0891b2",
  heater: "#ea580c", flame: "#ea580c", fan: "#0891b2", snowflake: "#0284c7", wind: "#0891b2", blinds: "#475569", "ev-charger": "#16a34a" };

function devSub(d) {
  if (d.online === false) return "Offline";
  const bits = [];
  if (d.on != null) bits.push(d.on ? "Tændt" : "Slukket");
  if (d.on && d.brightness != null) bits.push(`${d.brightness} %`);
  if (d.on && d.power_w != null && d.power_w > 0.5) bits.push(d.power_w >= 1000 ? `${num(d.power_w / 1000, 2)} kW` : `${num(d.power_w, 0)} W`);
  if (d.temp != null) bits.push(`${num(d.temp, 1)}°`);
  if (d.humidity != null) bits.push(`${num(d.humidity, 0)} %`);
  if (d.open != null) bits.push(d.open ? "Åben" : "Lukket");
  return bits.join(" · ") || (d.product ? esc(d.product) : "");
}

function renderDevices() {
  const dv = S.devices || {};
  const items = dv.items || [];
  const onCount = items.filter((d) => d.on).length;
  const tag = $("devTag");
  tag.className = "tag " + (dv.demo ? "demo" : dv.error ? "err" : "");
  tag.textContent = dv.demo ? "Demo" : dv.error && !items.length ? "Fejl" : `${onCount} tændt`;
  const html = items.length
    ? items.map((d) => {
        const sensor = d.on == null;
        const cls = sensor ? "sensor" : d.on ? "on" : "off";
        return `<button class="dev ${cls} ${d.online === false ? "offline" : ""}" data-id="${esc(d.id)}" style="--dc:${DEV_COLOR[d.icon] || "#2563eb"}" ${sensor ? "disabled" : ""}>
          <div class="dev-ic">${icon(d.icon)}</div>
          <div><div class="dev-name">${esc(d.name)}</div><div class="dev-sub">${devSub(d)}</div></div>
        </button>`;
      }).join("")
    : `<div class="empty">${dv.error ? esc(dv.error) : "Ingen enheder endnu – tilføj dem i Smart Life/Tuya-appen"}</div>`;
  const grid = $("devGrid");
  setHTML(grid, html);
  grid.classList.toggle("fits", grid.scrollHeight <= grid.clientHeight + 2);
}

$("devGrid").addEventListener("click", async (e) => {
  const b = e.target.closest(".dev");
  if (!b || b.classList.contains("sensor") || b.classList.contains("busy")) return;
  const id = b.dataset.id;
  const wasOn = b.classList.contains("on");
  b.classList.add("busy");
  b.classList.toggle("on", !wasOn);
  b.classList.toggle("off", wasOn);
  try {
    const r = await fetch(`api/devices/${encodeURIComponent(id)}/toggle`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: !wasOn }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
    const it = (S.devices?.items || []).find((d) => d.id === id);
    if (it) it.on = !wasOn;
    $("devGrid")._html = null;
  } catch (err) {
    b.classList.toggle("on", wasOn);
    b.classList.toggle("off", !wasOn);
    toast(`Kunne ikke skifte: ${err.message}`);
  } finally {
    b.classList.remove("busy");
    renderDevices();
  }
});

$("chargerBtn").addEventListener("click", async () => {
  const ch = S?.charger || {};
  const turnOn = !ch.on;
  const go = async () => {
    try {
      const r = await fetch("api/charger/toggle", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: turnOn }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
      ch.on = turnOn;
      toast(turnOn ? "Laderen er tændt" : "Laderen er slukket");
      setTimeout(() => fetch("api/state").then((r) => r.json()).then((d) => { S = d; render(); }), 1500);
    } catch (err) {
      toast(`Laderen svarede ikke: ${err.message}`);
    }
  };
  if (ch.confirm === false) return go();
  confirmModal(turnOn ? "Start opladning?" : "Stop opladning?",
    turnOn ? `Tænder for ${esc(ch.name || "laderen")}.` : `Slukker for ${esc(ch.name || "laderen")}. Bilen stopper med at lade.`,
    turnOn ? "Start" : "Stop", go, turnOn ? "plug-zap" : "power");
});

// ---------- dock
let tickerKey = "";
function renderDock() {
  if (!S) return;
  const demoParts = S.ui?.demo_parts || [];
  const age = (Date.now() - lastOk) / 1000;
  const bad = fetchError || age > 60;
  const demo = demoParts.length || S.prices?.demo;
  const items = S.news?.items || [];
  const key = items.map((n) => n.url).join("|").slice(0, 600) + (S.news?.demo ? "d" : "");
  if (key !== tickerKey || !$("tickerTrack")) {
    tickerKey = key;
    const one = items.length
      ? items.map((n) => `<a class="news-item" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer"><b class="src ${n.src === "DR" ? "dr" : "nj"}">${esc(n.src)}</b>${esc(n.title)}</a><span class="news-sep">◆</span>`).join("")
      : `<span class="news-empty">${S.news?.error ? "Nyheder kunne ikke hentes lige nu" : "Henter nyheder …"}</span>`;
    $("dock").innerHTML = `<div class="ticker"><div class="ticker-track" id="tickerTrack"><div class="tk">${one}</div><div class="tk" aria-hidden="true">${one}</div></div></div>
      <button class="status-dot" id="statusPill" aria-label="Status"></button>`;
    const track = $("tickerTrack");
    requestAnimationFrame(() => {
      const w = track.scrollWidth / 2;
      track.style.animationDuration = Math.max(25, w / 60) + "s";  // ca. 60 px i sekundet
    });
  }
  const dot = $("statusPill");
  dot.className = "status-dot " + (bad ? "bad" : demo ? "demo" : "live");
  dot.title = bad ? "Ingen forbindelse" : demo ? "Demo-data" : "Live";
}

let tkTimer;
$("dock").addEventListener("pointerdown", (e) => {
  if (!e.target.closest(".ticker")) return;
  $("dock").classList.add("paused");
  clearTimeout(tkTimer);
});
const tkResume = () => { clearTimeout(tkTimer); tkTimer = setTimeout(() => $("dock").classList.remove("paused"), 4000); };
$("dock").addEventListener("pointerup", tkResume);
$("dock").addEventListener("pointercancel", tkResume);

$("dock").addEventListener("click", (e) => {
  if (!e.target.closest("#statusPill")) return;
  const names = { solar: "solceller/batteri", car: "bil", devices: "Tuya-enheder", charger: "lader", weather: "vejr" };
  const demo = (S?.ui?.demo_parts || []).map((p) => names[p] || p);
  if (S?.prices?.demo) demo.push("elpriser");
  toast(fetchError ? `Fejl: ${fetchError}` : demo.length ? `Demo-data for: ${demo.join(", ")}` : "Alle data er live");
});

// ---------- vejr
const fx = new WeatherFX($("wxBack"), $("wxFront"));
const WEEKDAY = ["Søn", "Man", "Tir", "Ons", "Tor", "Fre", "Lør"];

function renderWeather() {
  const w = S.weather;
  const forced = params.get("weather");
  const c = w?.current || {};
  const effect = forced || c.effect || "none";
  const rad = ((c.wind_dir ?? 270) * Math.PI) / 180;
  const windX = -Math.sin(rad) * (c.wind ?? 2);
  const intensity = /heavy|thunder/.test(effect) ? 1 : forced ? 0.65 : Math.max(0.3, Math.min((c.precip || 0.6) / 2.5, 1));
  let mode = S.ui?.weather_effects || "full";
  if (document.body.classList.contains("lite") && mode === "full") mode = "light";
  if (params.get("fx")) mode = params.get("fx");
  fx.set({ effect, intensity, wind: windX, isDay: params.has("night") ? false : c.is_day !== false, accum: Number(params.get("fxspeed")) || 1 }, mode);
  if (!$("wxModal").hidden) renderWeatherModal();
}

function renderWeatherModal() {
  const w = S.weather;
  if (!w || !w.current) return;
  const c = w.current;
  const hrs = (w.hourly || []).slice(0, 24);
  const COL = 54;                       // bredde pr. time
  const Wd = hrs.length * COL, H = 96;
  const temps = hrs.map((h) => h.temp);
  const tmin = Math.min(...temps), tmax = Math.max(...temps), span = Math.max(tmax - tmin, 3);
  const yT = (t) => 14 + (1 - (t - tmin) / span) * (H - 34);
  const pts = hrs.map((h, i) => [i * COL + COL / 2, yT(h.temp)]);
  let line = "";
  pts.forEach((p, i) => {
    if (!i) line = `M${p[0]},${p[1]}`;
    else { const q = pts[i - 1], mx = (q[0] + p[0]) / 2; line += ` C${mx},${q[1]} ${mx},${p[1]} ${p[0]},${p[1]}`; }
  });
  const area = line + ` L${pts[pts.length - 1][0]},${H} L${pts[0][0]},${H} Z`;
  const curve = `<svg class="yr-curve" width="${Wd}" height="${H}" viewBox="0 0 ${Wd} ${H}">
      <defs><linearGradient id="yrA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8FB8AE" stop-opacity=".4"/><stop offset="1" stop-color="#8FB8AE" stop-opacity="0"/></linearGradient></defs>
      <path d="${area}" fill="url(#yrA)"/><path d="${line}" fill="none" stroke="#DCEBE6" stroke-width="2.5" stroke-linecap="round"/>
      ${pts.map((p, i) => `<text x="${p[0]}" y="${p[1] - 7}" text-anchor="middle" class="yr-t">${num(hrs[i].temp, 0)}°</text>`).join("")}</svg>`;
  const pmax = Math.max(1, ...hrs.map((h) => h.precip || 0));
  const col = (h, i) => `<div class="yr-c" style="width:${COL}px">${i === 0 || new Date(h.time).getHours() === 0 ? `<em>${WEEKDAY[new Date(h.time).getDay()]}</em>` : "<em></em>"}<b>${pad(new Date(h.time).getHours())}</b>${wxIcon(h.icon, h.is_day)}</div>`;
  const rain = hrs.map((h) => `<div class="yr-r" style="width:${COL}px"><i style="height:${Math.max(0, Math.min(100, ((h.precip || 0) / pmax) * 100))}%"></i><span>${h.precip ? num(h.precip, 1) : ""}</span></div>`).join("");
  const wind = hrs.map((h) => `<div class="yr-w" style="width:${COL}px"><svg viewBox="0 0 24 24" style="transform:rotate(${(h.wind_dir ?? 0) + 180}deg)"><path d="M12 3 L18 19 L12 15 L6 19 Z" fill="#DCEBE6"/></svg><span>${num(h.wind, 0)}</span></div>`).join("");
  const days = w.daily || [];
  const rows = days.map((d, i) => {
    const dt = new Date(d.date + "T12:00");
    return `<div class="yr-d"><div class="yr-dn"><b>${i === 0 ? "I dag" : i === 1 ? "I morgen" : DAYS[dt.getDay()]}</b><span>${dt.getDate()}. ${MONTHS[dt.getMonth()].slice(0, 3)}</span></div>
      ${wxIcon(d.icon, true)}<div class="yr-dt"><b>${num(d.max, 0)}°</b><span>${num(d.min, 0)}°</span></div>
      <div class="yr-dp">${d.precip ? icon("droplets") + " " + num(d.precip, 1) + " mm" : ""}</div>
      <div class="yr-dw">${d.wind != null ? icon("wind") + " " + num(d.wind, 0) + " m/s" : ""}</div></div>`;
  }).join("");
  setHTML($("wxCard"), `
    <div class="yr-head">
      <div><div class="yr-place">${esc(w.place || "Vejret")}${w.demo ? " · demo" : ""}</div>
        <div class="yr-big">${num(c.temp, 0)}°</div>
        <div class="yr-text">${esc(c.text)} · føles som ${num(c.feels_like, 0)}°</div></div>
      <div class="yr-ic">${wxIcon(c.icon, c.is_day)}</div>
      <div class="yr-facts"><span>${icon("wind")} ${num(c.wind, 0)} m/s${c.gusts ? ` <small>(stød ${num(c.gusts, 0)})</small>` : ""}</span><span>${icon("droplets")} ${num(c.humidity, 0)} %</span><span>${icon("sun")} ${days[0]?.sunrise ? days[0].sunrise.slice(11, 16) : "–"} · ${days[0]?.sunset ? days[0].sunset.slice(11, 16) : "–"}</span></div>
      <button class="round-btn yr-x" id="wxClose" aria-label="Luk">✕</button>
    </div>
    <div class="yr-sec"><div class="yr-lbl">De næste 24 timer</div>
      <div class="yr-scroll"><div style="width:${Wd}px">
        <div class="yr-row">${hrs.map(col).join("")}</div>${curve}
        <div class="yr-sub">Nedbør (mm)</div><div class="yr-row yr-rain">${rain}</div>
        <div class="yr-sub">Vind (m/s)</div><div class="yr-row">${wind}</div></div></div></div>
    <div class="yr-sec"><div class="yr-lbl">Næste dage</div>${rows}</div>`);
}

document.addEventListener("click", (e) => {
  if (e.target.closest("#wxTile")) { $("wxModal").hidden = false; $("wxCard")._html = null; renderWeatherModal(); }
  else if (e.target.closest("#wxClose") || e.target === $("wxModal")) $("wxModal").hidden = true;
});

// ---------------------------------------------------------------- modal / toast
let toastT;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (t.hidden = true), 3500);
}

function confirmModal(title, text, okLabel, onOk, ic = "power") {
  $("modalTitle").textContent = title;
  $("modalText").innerHTML = text;
  $("modalOk").textContent = okLabel;
  $("modalIcon").innerHTML = icon(ic);
  $("modal").hidden = false;
  const close = () => ($("modal").hidden = true);
  $("modalCancel").onclick = close;
  $("modal").onclick = (e) => { if (e.target === $("modal")) close(); };
  $("modalOk").onclick = () => { close(); onOk(); };
}

// ---------------------------------------------------------------- små ting
// Undgå indbrænding på skærme der altid er tændt: flyt layoutet et par pixels hvert 5. minut
setInterval(() => {
  const x = Math.round(Math.random() * 4 - 2), y = Math.round(Math.random() * 4 - 2);
  $("app").style.transform = `translate(${x}px, ${y}px)`;
}, 5 * 60 * 1000);

// Hold skærmen tændt hvor browseren tillader det (kræver https eller localhost)
async function wakeLock() {
  try { if ("wakeLock" in navigator) await navigator.wakeLock.request("screen"); } catch { /* ignorer */ }
}
document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && wakeLock());
wakeLock();

window.addEventListener("resize", () => { flowSize = ""; $("devGrid")._html = null; render(); });

tickClock();
setInterval(tickClock, 1000);
poll();
