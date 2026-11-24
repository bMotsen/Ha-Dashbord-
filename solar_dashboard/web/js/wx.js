// Vejr: animerede ikoner + vejr-effekter (regndråber på glasset, sne der lægger sig, skyer, sol, stjerner, lyn)

// ------------------------------------------------------------------ ikoner
const CLOUD = "M17 47 H47 A10 10 0 0 0 48 27.1 A13.5 13.5 0 0 0 22.6 24.4 A11.3 11.3 0 0 0 17 47 Z";
const defs = (id) => `
  <defs>
    <linearGradient id="${id}s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffe066"/><stop offset="1" stop-color="#ff9a1f"/></linearGradient>
    <linearGradient id="${id}c" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d4dde8"/></linearGradient>
    <linearGradient id="${id}d" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9c4d2"/><stop offset="1" stop-color="#7d8a9c"/></linearGradient>
    <linearGradient id="${id}m" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fdfcf3"/><stop offset="1" stop-color="#c9d3e6"/></linearGradient>
  </defs>`;

function sun(id, cx = 32, cy = 32, r = 11, sc = 1) {
  const rays = Array.from({ length: 8 }, (_, i) => {
    const a = (i * Math.PI) / 4;
    const x1 = cx + Math.cos(a) * (r + 5) * sc, y1 = cy + Math.sin(a) * (r + 5) * sc;
    const x2 = cx + Math.cos(a) * (r + 10) * sc, y2 = cy + Math.sin(a) * (r + 10) * sc;
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
  }).join("");
  return `<g class="wx-rays" style="transform-origin:${cx}px ${cy}px" stroke="url(#${id}s)" stroke-width="${3.2 * sc}" stroke-linecap="round">${rays}</g>
    <circle cx="${cx}" cy="${cy}" r="${r * sc}" fill="url(#${id}s)" style="filter:drop-shadow(0 0 4px rgba(255,190,60,.7))"/>`;
}
function moon(id, cx = 32, cy = 30, sc = 1) {
  return `<path transform="translate(${cx - 32 * sc} ${cy - 30 * sc}) scale(${sc})" d="M38 12 A18 18 0 1 0 50 40 A14 14 0 1 1 38 12 Z" fill="url(#${id}m)" style="filter:drop-shadow(0 0 5px rgba(220,230,255,.55))"/>
    <circle class="wx-twinkle" cx="${cx + 14 * sc}" cy="${cy - 14 * sc}" r="${1.4 * sc}" fill="#fff"/>
    <circle class="wx-twinkle d2" cx="${cx + 20 * sc}" cy="${cy - 4 * sc}" r="${1 * sc}" fill="#fff"/>`;
}
function cloud(id, dark = false, dx = 0, dy = 0, s = 1, cls = "wx-cloud") {
  return `<g class="${cls}"><path d="${CLOUD}" transform="translate(${dx} ${dy}) scale(${s})" fill="url(#${id}${dark ? "d" : "c"})" style="filter:drop-shadow(0 3px 4px rgba(0,0,0,.25))"/></g>`;
}
const drops = (n, color = "#7cc7ff") => Array.from({ length: n }, (_, i) => {
  const x = 22 + i * (20 / Math.max(n - 1, 1));
  return `<line class="wx-drop" style="animation-delay:${(i * 0.27).toFixed(2)}s" x1="${x}" y1="50" x2="${x - 2}" y2="56" stroke="${color}" stroke-width="2.6" stroke-linecap="round"/>`;
}).join("");
const flakes = (n) => Array.from({ length: n }, (_, i) => {
  const x = 22 + i * (20 / Math.max(n - 1, 1));
  return `<g class="wx-flake" style="animation-delay:${(i * 0.6).toFixed(2)}s"><g transform="translate(${x} 53)">
    <path d="M0 -3.6V3.6M-3.1 -1.8L3.1 1.8M-3.1 1.8L3.1 -1.8" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></g></g>`;
}).join("");

export function wxIcon(icon, isDay = true) {
  const id = `wx${icon}${isDay ? "d" : "n"}_`;
  let body;
  switch (icon) {
    case "clear": body = isDay ? sun(id) : moon(id); break;
    case "partly": body = (isDay ? sun(id, 23, 23, 9, 0.85) : moon(id, 24, 22, 0.7)) + cloud(id, false, 4, 4, 0.9); break;
    case "cloudy": body = cloud(id, true, -6, -6, 0.85, "wx-cloud slow") + cloud(id, false, 2, 2, 0.95); break;
    case "fog": body = cloud(id, true, 0, -6, 0.95) +
      `<g stroke="#cfd8e3" stroke-width="3" stroke-linecap="round"><line class="wx-fogl" x1="14" y1="50" x2="44" y2="50"/><line class="wx-fogl d2" x1="20" y1="56" x2="52" y2="56"/></g>`; break;
    case "drizzle": body = cloud(id, false, 0, -6) + drops(3, "#9fd4ff"); break;
    case "rain": case "showers":
      body = (icon === "showers" && isDay ? sun(id, 22, 18, 8, 0.75) : "") + cloud(id, true, 0, -6) + drops(4); break;
    case "sleet": body = cloud(id, true, 0, -6) + drops(2) + flakes(2); break;
    case "snow": body = cloud(id, false, 0, -7) + flakes(3); break;
    case "thunder": body = cloud(id, true, 0, -8) + drops(2) +
      `<path class="wx-bolt" d="M33 38 L26 50 H32 L28 60 L40 46 H34 L38 38 Z" fill="#ffd43b" style="filter:drop-shadow(0 0 4px #ffd43b)"/>`; break;
    default: body = cloud(id, false, 0, 0);
  }
  return `<svg class="wx-ic" viewBox="0 0 64 64" aria-hidden="true">${defs(id)}${body}</svg>`;
}

// ------------------------------------------------------------------ effekter
const rnd = (a, b) => a + Math.random() * (b - a);

function sprite(size, draw) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  draw(c.getContext("2d"), size);
  return c;
}

const DROP = sprite(64, (g, s) => {
  const r = s / 2;
  let grd = g.createRadialGradient(r, r * 1.08, r * 0.1, r, r, r);
  grd.addColorStop(0, "rgba(255,255,255,0.16)");
  grd.addColorStop(0.62, "rgba(220,240,255,0.14)");
  grd.addColorStop(0.86, "rgba(0,20,15,0.42)");
  grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd;
  g.beginPath(); g.arc(r, r, r, 0, Math.PI * 2); g.fill();
  // lys brydning nederst i dråben
  grd = g.createRadialGradient(r, r * 1.45, 1, r, r * 1.45, r * 0.55);
  grd.addColorStop(0, "rgba(255,255,255,0.38)");
  grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd;
  g.beginPath(); g.arc(r, r * 1.45, r * 0.55, 0, Math.PI * 2); g.fill();
  // højlys øverst til venstre
  g.fillStyle = "rgba(255,255,255,0.85)";
  g.beginPath(); g.ellipse(r * 0.68, r * 0.62, r * 0.16, r * 0.11, -0.6, 0, Math.PI * 2); g.fill();
});

const FLAKE = sprite(32, (g, s) => {
  const r = s / 2;
  const grd = g.createRadialGradient(r, r, 0, r, r, r);
  grd.addColorStop(0, "rgba(255,255,255,1)");
  grd.addColorStop(0.45, "rgba(255,255,255,0.85)");
  grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd;
  g.beginPath(); g.arc(r, r, r, 0, Math.PI * 2); g.fill();
});

export class WeatherFX {
  constructor(back, front) {
    this.back = back; this.front = front;
    this.bg = back.getContext("2d"); this.fg = front.getContext("2d");
    this.mode = "full";
    this.state = { effect: "none", intensity: 0.5, wind: 0, isDay: true };
    this.drops = []; this.streaks = []; this.flakes = []; this.clouds = []; this.stars = [];
    this.surfaces = []; this.flash = 0; this.nextFlash = 0; this.bolt = null;
    this.t = 0; this.lastFront = 0; this.lastBack = 0; this.lastSurf = 0;
    this.running = false;
    this.resize();
    window.addEventListener("resize", () => this.resize());
    document.addEventListener("visibilitychange", () => { if (!document.hidden) this.kick(); });
  }

  resize() {
    this.dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    this.W = window.innerWidth; this.H = window.innerHeight;
    for (const c of [this.back, this.front]) {
      c.width = Math.round(this.W * this.dpr); c.height = Math.round(this.H * this.dpr);
      c.style.width = this.W + "px"; c.style.height = this.H + "px";
    }
    this.bg.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.fg.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.surfaces = [];
    this.stars = Array.from({ length: 140 }, () => ({ x: rnd(0, this.W), y: rnd(0, this.H * 0.7), r: rnd(0.4, 1.4), p: rnd(0, 6.3), s: rnd(0.5, 2) }));
    this.lastBack = 0;
    this.kick();
  }

  set(state, mode = "full") {
    this.mode = mode;
    const prev = this.state.effect;
    this.state = { ...this.state, ...state };
    if (prev !== this.state.effect) {
      this.flakes = []; this.streaks = [];
      if (!/rain|drizzle|thunder|sleet/.test(this.state.effect)) this.drops = this.drops.filter((d) => !d.big);
      this.clouds = [];
    }
    this.lastBack = 0;
    this.kick();
  }

  kick() {
    if (this.running || this.mode === "off") return;
    this.running = true;
    requestAnimationFrame((t) => this.loop(t));
  }

  // fliser og dock som sneen kan lægge sig på
  updateSurfaces() {
    const els = [...document.querySelectorAll(".tile, .dock")];
    const old = new Map(this.surfaces.map((s) => [s.key, s]));
    const out = [];
    for (const el of els) {
      const r = el.getBoundingClientRect();
      const key = `${el.id || el.className}`;
      const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 20;
      const prev = old.get(key);
      const cols = Math.max(4, Math.ceil(r.width / 4));
      const h = prev && prev.h.length === cols && Math.abs(prev.top - r.top) < 2 ? prev.h : new Float32Array(cols);
      out.push({ key, left: r.left, top: r.top, w: r.width, radius, h, max: el.classList.contains("dock") ? 7 : 11, p: 0.22 });
    }
    const bkey = "bottom";
    const bprev = old.get(bkey);
    const bcols = Math.ceil(this.W / 4);
    out.push({ key: bkey, left: 0, top: this.H, w: this.W, radius: 0, h: bprev && bprev.h.length === bcols ? bprev.h : new Float32Array(bcols), max: 30, p: 1 });
    this.surfaces = out;
  }

  loop(t) {
    const { effect } = this.state;
    if (document.hidden || this.mode === "off") { this.running = false; this.fg.clearRect(0, 0, this.W, this.H); this.bg.clearRect(0, 0, this.W, this.H); return; }
    const dt = Math.min((t - (this.t || t)) / 1000, 0.1);
    this.t = t;
    if (this.mode === "full" && t - this.lastBack > 83) { this.drawBack(t, (t - (this.lastBack || t)) / 1000); this.lastBack = t; }
    if (t - this.lastFront > 30) { this.drawFront(t, dt); this.lastFront = t; }
    const busy = effect !== "none" || this.surfaces.some((s) => s.h.some((v) => v > 0.05)) || this.drops.length;
    if (busy) requestAnimationFrame((tt) => this.loop(tt));
    else { this.running = false; this.fg.clearRect(0, 0, this.W, this.H); }
  }

  // ---------------- baggrund (bag fliserne, ~12 fps for at spare grafikkortet)
  drawBack(t, dt) {
    const g = this.bg, W = this.W, H = this.H;
    const { effect, isDay } = this.state;
    g.clearRect(0, 0, W, H);
    const sec = t / 1000;
    if (effect === "none") return;
    if (effect === "clear") {
      if (isDay) {
        const cx = W * 0.82, cy = -H * 0.06, R = Math.max(W, H) * 0.55;
        const grd = g.createRadialGradient(cx, cy, 10, cx, cy, R);
        grd.addColorStop(0, "rgba(255,226,140,0.30)"); grd.addColorStop(0.35, "rgba(255,200,90,0.10)"); grd.addColorStop(1, "rgba(255,200,90,0)");
        g.fillStyle = grd; g.fillRect(0, 0, W, H);
        g.save(); g.translate(cx, cy); g.rotate(sec * 0.02);
        for (let i = 0; i < 14; i++) {
          g.rotate((Math.PI * 2) / 14);
          const a = 0.035 + 0.02 * Math.sin(sec * 0.4 + i);
          g.fillStyle = `rgba(255,236,170,${a})`;
          g.beginPath(); g.moveTo(0, 0); g.lineTo(R * 1.2, -R * 0.06); g.lineTo(R * 1.2, R * 0.06); g.closePath(); g.fill();
        }
        g.restore();
      } else {
        for (const s of this.stars) {
          const a = 0.35 + 0.45 * Math.sin(sec * s.s + s.p);
          g.fillStyle = `rgba(255,255,255,${Math.max(a, 0.05)})`;
          g.beginPath(); g.arc(s.x, s.y, s.r, 0, Math.PI * 2); g.fill();
        }
      }
      return;
    }
    // skyer
    const want = { cloudy: 8, fog: 10, drizzle: 9, rain: 10, "heavy-rain": 12, thunder: 12, snow: 9, "heavy-snow": 11, sleet: 10 }[effect] || 0;
    while (this.clouds.length < want) this.clouds.push(this.newCloud(true));
    if (this.clouds.length > want) this.clouds.length = want;
    const dark = /rain|thunder|sleet/.test(effect);
    for (const c of this.clouds) {
      c.x += (c.v + this.state.wind * 1.5) * Math.max(dt, 0.083);
      if (c.x - c.w > W) Object.assign(c, this.newCloud(false));
      for (const p of c.puffs) {
        const x = c.x + p.dx, y = c.y + p.dy;
        const grd = g.createRadialGradient(x, y, 0, x, y, p.r);
        const col = dark ? "150,170,170" : "225,240,235";
        grd.addColorStop(0, `rgba(${col},${c.a})`); grd.addColorStop(1, `rgba(${col},0)`);
        g.fillStyle = grd; g.beginPath(); g.arc(x, y, p.r, 0, Math.PI * 2); g.fill();
      }
    }
    if (this.bolt && this.flash > 0.05) {
      g.strokeStyle = `rgba(235,245,255,${this.flash})`; g.lineWidth = 2.2; g.shadowColor = "#cfe6ff"; g.shadowBlur = 16;
      g.beginPath(); this.bolt.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
      g.shadowBlur = 0;
    }
  }

  newCloud(initial) {
    const w = rnd(260, 520);
    const puffs = Array.from({ length: 6 }, (_, i) => ({ dx: (i / 5) * w - w / 2 + rnd(-30, 30), dy: rnd(-40, 40), r: rnd(90, 170) }));
    return { x: initial ? rnd(-w, this.W) : -w - rnd(0, 300), y: rnd(-60, this.H * 0.55), w, v: rnd(6, 14), a: rnd(0.05, 0.11), puffs };
  }

  // ---------------- forgrund (oven på fliserne)
  drawFront(t, dt) {
    const g = this.fg, W = this.W, H = this.H;
    const { effect, intensity, wind } = this.state;
    g.clearRect(0, 0, W, H);
    const rainy = /rain|drizzle|thunder|sleet/.test(effect);
    const snowy = /snow|sleet/.test(effect);
    const k = Math.max(0.15, Math.min(intensity, 1));

    if (t - this.lastSurf > 1500) { this.updateSurfaces(); this.lastSurf = t; }

    // tåge
    if (effect === "fog") {
      for (let i = 0; i < 3; i++) {
        const y = H * (0.25 + i * 0.28), x = ((t / 1000) * (8 + i * 4)) % (W * 2) - W;
        const grd = g.createLinearGradient(0, y - 120, 0, y + 120);
        grd.addColorStop(0, "rgba(220,235,230,0)"); grd.addColorStop(0.5, "rgba(220,235,230,0.07)"); grd.addColorStop(1, "rgba(220,235,230,0)");
        g.fillStyle = grd; g.fillRect(x, y - 120, W * 2, 240);
      }
    }

    // regnstriber i luften
    if (rainy && this.mode === "full") {
      const target = Math.round((effect === "drizzle" ? 45 : 110) * k * (effect === "heavy-rain" || effect === "thunder" ? 1.8 : 1));
      while (this.streaks.length < target) this.streaks.push({ x: rnd(-50, W + 50), y: rnd(-H, H), l: rnd(12, 30), v: rnd(700, 1100), a: rnd(0.1, 0.3) });
      g.lineCap = "round"; g.lineWidth = 1.1;
      const slant = wind * 18;
      for (const s of this.streaks) {
        s.y += s.v * dt; s.x += slant * dt;
        if (s.y > H) { s.y = rnd(-80, -10); s.x = rnd(-50, W + 50); }
        g.strokeStyle = `rgba(200,230,240,${s.a})`;
        g.beginPath(); g.moveTo(s.x, s.y); g.lineTo(s.x - slant * 0.02 * s.l / 10, s.y - s.l); g.stroke();
      }
    }

    // dråber på glasset
    if (rainy || this.drops.length) this.drawDrops(g, dt, rainy, k, effect);

    // sne
    if (snowy || this.flakes.length) this.drawSnow(g, dt, snowy, k, effect, wind);
    this.drawSnowCover(g, dt, snowy);

    // lyn
    if (effect === "thunder") {
      if (t > this.nextFlash) {
        this.flash = 0.55; this.nextFlash = t + rnd(5000, 16000);
        const x0 = rnd(W * 0.15, W * 0.85); let x = x0, y = -10; this.bolt = [[x, y]];
        while (y < H * rnd(0.35, 0.6)) { x += rnd(-40, 40); y += rnd(20, 55); this.bolt.push([x, y]); }
        setTimeout(() => (this.flash = 0.4), 180);
      }
      if (this.flash > 0.01) {
        g.fillStyle = `rgba(230,240,255,${this.flash * 0.35})`; g.fillRect(0, 0, W, H);
        this.flash *= Math.pow(0.02, dt);
      }
    }
  }

  drawDrops(g, dt, rainy, k, effect) {
    const W = this.W, H = this.H;
    if (rainy) {
      const rate = (effect === "drizzle" ? 16 : 38) * k * (effect === "heavy-rain" || effect === "thunder" ? 1.6 : 1);
      for (let n = rate * dt + (Math.random() < (rate * dt) % 1 ? 1 : 0); n >= 1; n--) {
        if (this.drops.length > 520) break;
        const big = Math.random() < (effect === "drizzle" ? 0.04 : 0.14);
        this.drops.push({ x: rnd(0, W), y: rnd(0, H), r: big ? rnd(5, 9) : rnd(1.3, 3.8), big, life: rnd(8, 26), age: 0, v: 0, slide: false, wob: rnd(0, 6) });
      }
    }
    const fade = rainy ? 1 : 3;
    const keep = [];
    for (const d of this.drops) {
      d.age += dt * fade;
      if (d.big && !d.slide && d.r > 5.2 && Math.random() < 0.004) d.slide = true;
      if (d.slide) {
        d.v = Math.min(d.v + 260 * dt, 70 + d.r * 18);
        d.y += d.v * dt; d.x += Math.sin(d.y * 0.05 + d.wob) * 0.3;
        if (Math.random() < 0.18) keep.push({ x: d.x + rnd(-1, 1), y: d.y - d.r, r: rnd(0.8, 1.8), big: false, life: rnd(4, 9), age: 0, v: 0, slide: false, wob: 0 });
        d.r = Math.max(d.r - dt * 0.25, 3);
      }
      if (d.y - d.r > H || d.age > d.life) continue;
      const a = Math.min(1, (d.life - d.age) / 2, d.age * 3);
      g.globalAlpha = Math.max(a, 0);
      const s = d.r * 2;
      g.drawImage(DROP, d.x - d.r, d.y - d.r * (d.slide ? 1.25 : 1), s, s * (d.slide ? 1.25 : 1.05));
      keep.push(d);
    }
    g.globalAlpha = 1;
    // store glidende dråber opsluger små dråber på vejen
    const sliders = keep.filter((d) => d.slide);
    if (sliders.length) {
      this.drops = keep.filter((d) => {
        if (d.big) return true;
        for (const s of sliders) if (Math.abs(d.x - s.x) < s.r && Math.abs(d.y - s.y) < s.r * 1.2) { s.r = Math.min(s.r + d.r * 0.08, 9); return false; }
        return true;
      });
    } else this.drops = keep;
  }

  drawSnow(g, dt, snowy, k, effect, wind) {
    const W = this.W, H = this.H;
    const target = snowy ? Math.round((effect === "heavy-snow" ? 300 : 190) * k + 50) : 0;
    const seed = !this.flakes.length;  // første gang: fyld hele skærmen med det samme
    while (this.flakes.length < target) this.flakes.push(this.newFlake(seed));
    const f60 = dt * 60;
    const keep = [];
    for (const f of this.flakes) {
      const py = f.y;
      f.p += 0.02 * f60;
      f.y += f.vy * f60;
      f.x += (Math.sin(f.p) * 0.45 + wind * 0.12 * f.z) * f60;
      if (f.x < -10) f.x = W + 10; if (f.x > W + 10) f.x = -10;
      let landed = false;
      for (const s of this.surfaces) {
        const xi = f.x - s.left;
        if (xi < s.radius * 0.6 || xi > s.w - s.radius * 0.6) continue;
        const col = Math.floor(xi / 4);
        const top = s.top - s.h[col];
        if (py < top && f.y >= top && (s.p >= 1 || (f.z > 0.75 && Math.random() < s.p))) {
          this.addSnow(s, col, f.r);
          landed = true; break;
        }
      }
      if (landed || f.y > H + 10) {
        if (!snowy) continue;
        Object.assign(f, this.newFlake(false));
      }
      g.globalAlpha = f.a;
      const s = f.r * 2.4;
      g.drawImage(FLAKE, f.x - s / 2, f.y - s / 2, s, s);
      keep.push(f);
    }
    g.globalAlpha = 1;
    this.flakes = snowy ? keep.slice(0, target) : keep;
  }

  newFlake(seed) {
    const z = Math.random();
    return { x: rnd(0, this.W), y: seed ? rnd(-this.H, this.H) : rnd(-60, -5), z, r: 0.8 + z * z * 3.4, vy: 0.3 + z * 0.95, p: rnd(0, 6.3), a: 0.4 + z * 0.55 };
  }

  addSnow(s, col, r) {
    const amount = r * 0.55 * (this.state.accum || 1);
    for (let i = -7; i <= 7; i++) {
      const c = col + i;
      if (c < 0 || c >= s.h.length) continue;
      s.h[c] = Math.min(s.h[c] + amount * 0.45 * Math.exp(-(i * i) / 14), s.max);
    }
  }

  drawSnowCover(g, dt, snowy) {
    for (const s of this.surfaces) {
      const h = s.h;
      let any = false;
      if (!snowy) for (let i = 0; i < h.length; i++) { h[i] = Math.max(0, h[i] - dt * 0.12); }
      for (let i = 0; i < h.length; i++) if (h[i] > 0.3) { any = true; break; }
      if (!any) continue;
      // jævn sneen lidt ud
      for (let pass = 0; pass < 2; pass++) for (let i = 1; i < h.length - 1; i++) h[i] = h[i] * 0.9 + (h[i - 1] + h[i + 1]) * 0.05;
      const n = h.length;
      const x0 = s.left, base = s.top + (s.key === "bottom" ? 0 : 1.5);
      const taper = (i) => {
        const x = i * 4, edge = Math.max(s.radius * 0.9, 1);
        const a = Math.min(1, x / edge, (s.w - x) / edge);
        return a <= 0 ? 0 : a * a * (3 - 2 * a);
      };
      g.beginPath();
      g.moveTo(x0, base);
      let px = x0, py = base;
      for (let i = 0; i < n; i += 2) {
        const x = x0 + i * 4 + 2, y = base - h[i] * taper(i);
        g.quadraticCurveTo(px, py, (px + x) / 2, (py + y) / 2);
        px = x; py = y;
      }
      g.quadraticCurveTo(px, py, x0 + s.w, base);
      g.closePath();
      const grd = g.createLinearGradient(0, base - s.max, 0, base);
      grd.addColorStop(0, "#ffffff"); grd.addColorStop(0.7, "#eef5fb"); grd.addColorStop(1, "#c9d8e4");
      g.fillStyle = grd;
      g.fill();
      g.strokeStyle = "rgba(255,255,255,0.9)"; g.lineWidth = 0.8; g.stroke();
    }
  }
}
