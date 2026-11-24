// VW ID.3 i Moonstone Grey (sort tag, honeycomb C-søjle) på 22" fælge i RS 6-stil (5 dobbelte V-eger).
// Tegnet som SVG, så den er skarp på alle skærme. Bilen vender mod venstre.

const P = (cx, cy, r, deg) => {
  const a = (deg * Math.PI) / 180;
  return `${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`;
};

function wheel(cx, cy) {
  let arms = "";
  let edges = "";
  for (let i = 0; i < 5; i++) {
    const a = i * 72 - 90;
    for (const s of [-1, 1]) {
      const pts = [P(cx, cy, 6.6, a + s * 3 - 15), P(cx, cy, 6.6, a + s * 3 + 15), P(cx, cy, 19.8, a + s * 10.5 + 6), P(cx, cy, 19.8, a + s * 10.5 - 6)];
      arms += `<polygon points="${pts.join(" ")}" fill="url(#cSpoke)"/>`;
      edges += `<polyline points="${P(cx, cy, 7, a + s * 3 + (s > 0 ? 14 : -14))} ${P(cx, cy, 19.6, a + s * 10.5 + (s > 0 ? 5.6 : -5.6))}" fill="none" stroke="rgba(255,255,255,.42)" stroke-width=".6"/>`;
    }
  }
  const nuts = [0, 1, 2, 3, 4].map((i) => {
    const [x, y] = P(cx, cy, 4.4, i * 72 - 54).split(",");
    return `<circle cx="${x}" cy="${y}" r=".75" fill="#9aa1a9"/>`;
  }).join("");
  // bremsekaliber (rød) bag egerne
  const cal = `M${P(cx, cy, 17.2, 200)} A17.2 17.2 0 0 1 ${P(cx, cy, 17.2, 246)} L${P(cx, cy, 11.4, 246)} A11.4 11.4 0 0 0 ${P(cx, cy, 11.4, 200)} Z`;
  return `<g>
    <circle cx="${cx}" cy="${cy}" r="26" fill="#0a0c0f"/>
    <circle cx="${cx}" cy="${cy}" r="25" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="1.3"/>
    <circle cx="${cx}" cy="${cy}" r="21.4" fill="url(#cLip)"/>
    <circle cx="${cx}" cy="${cy}" r="20.1" fill="#0d1014"/>
    <circle cx="${cx}" cy="${cy}" r="15.6" fill="url(#cDisc)"/>
    <circle cx="${cx}" cy="${cy}" r="10.6" fill="#24282d"/>
    <path d="${cal}" fill="url(#cCaliper)"/>
    ${arms}${edges}
    <circle cx="${cx}" cy="${cy}" r="6.6" fill="url(#cSpoke)" stroke="rgba(255,255,255,.22)" stroke-width=".5"/>
    ${nuts}
    <circle cx="${cx}" cy="${cy}" r="2.9" fill="#121417" stroke="#80878f" stroke-width=".45"/>
  </g>`;
}

export function carSVG(charging) {
  const W = 340;
  return `<svg viewBox="0 0 ${W} 132" preserveAspectRatio="xMaxYMid meet" aria-hidden="true">
  <defs>
    <linearGradient id="cPaint" gradientUnits="userSpaceOnUse" x1="0" y1="12" x2="0" y2="118">
      <stop offset="0" stop-color="#c3c9cb"/><stop offset=".33" stop-color="#a3abae"/><stop offset=".47" stop-color="#8f979b"/>
      <stop offset=".53" stop-color="#7c8589"/><stop offset=".78" stop-color="#6a7378"/><stop offset="1" stop-color="#40474d"/>
    </linearGradient>
    <linearGradient id="cSheen" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".38" stop-color="#fff" stop-opacity=".10"/>
      <stop offset=".55" stop-color="#fff" stop-opacity=".22"/><stop offset=".7" stop-color="#fff" stop-opacity=".06"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="cGround" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2fae84" stop-opacity="0"/><stop offset="1" stop-color="#2fae84" stop-opacity=".22"/>
    </linearGradient>
    <linearGradient id="cGlass" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4b6274"/><stop offset=".45" stop-color="#121c26"/><stop offset="1" stop-color="#263a48"/>
    </linearGradient>
    <linearGradient id="cBlack" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2c3238"/><stop offset="1" stop-color="#0a0c0f"/></linearGradient>
    <linearGradient id="cLower" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".28"/></linearGradient>
    <linearGradient id="cLip" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9aa1a8"/><stop offset=".5" stop-color="#3b4046"/><stop offset="1" stop-color="#15181b"/></linearGradient>
    <linearGradient id="cSpoke" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5d646c"/><stop offset=".5" stop-color="#363b41"/><stop offset="1" stop-color="#1b1e22"/></linearGradient>
    <radialGradient id="cDisc"><stop offset=".55" stop-color="#3a3e43"/><stop offset=".8" stop-color="#6d737a"/><stop offset="1" stop-color="#4a4f55"/></radialGradient>
    <linearGradient id="cCaliper" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff3b4e"/><stop offset="1" stop-color="#a50d22"/></linearGradient>
    <radialGradient id="cShadow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#000" stop-opacity=".6"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
    <pattern id="cHoney" width="4.2" height="7.27" patternUnits="userSpaceOnUse">
      <path d="M2.1 0 L4.2 1.21 V3.63 L2.1 4.85 L0 3.63 V1.21 Z M2.1 4.85 V7.27 M0 3.63 L-2.1 4.85 M4.2 3.63 L6.3 4.85" fill="none" stroke="rgba(190,205,215,.28)" stroke-width=".45"/>
    </pattern>
    <clipPath id="cBodyClip"><path d="M30 115 C23 114 20 110 20 104 L20 80 C20 70 21 60 23 52 L40 20.5 C42 17.5 45 16 50 15.6 C85 12.5 140 9.8 190 12 C196 12.5 201 14.5 205 17 L252 55 C270 57.5 292 60 306 63 C316 65 321 70 322 78 L322 98 C322 106 319 111 312 114 L293.5 115 A29 29 0 1 0 246.5 115 L95.8 115 A29 29 0 1 0 48.8 115 Z"/></clipPath>
  </defs>

  <ellipse cx="170" cy="123.5" rx="158" ry="7.5" fill="url(#cShadow)"/>
  <g transform="translate(${W} 0) scale(-1 1)">
    <circle cx="72.3" cy="98" r="28.6" fill="#06080a"/>
    <circle cx="270" cy="98" r="28.6" fill="#06080a"/>

    <!-- karrosseri -->
    <g clip-path="url(#cBodyClip)">
      <rect x="0" y="0" width="340" height="132" fill="url(#cPaint)"/>
      <rect x="0" y="0" width="340" height="132" fill="url(#cSheen)"/>
      <rect x="0" y="80" width="340" height="40" fill="url(#cGround)"/>
      <path d="M98 109.5 C140 110 200 110 245 109.5 L245 90 C200 92 140 92 99 90 Z" fill="url(#cLower)"/>
      <!-- sort tag, søjler og vinduesramme -->
      <path d="M24.5 50 L40 20.5 C42 17.5 45 16 50 15.6 C85 12.5 140 9.8 190 12 C196 12.5 201 14.5 205 17 L251 54.5 C246 54.6 242 54.6 238 54.4 C180 52.8 110 50.8 80 50.2 C66 49.5 52 46 42 43 C36 44.5 30 47 24.5 50 Z" fill="url(#cBlack)"/>
      <!-- ruder -->
      <path d="M236 53.8 L198.5 22.2 C196.5 20.6 193.5 19.8 190 19.8 L163 19.6 L162 52.2 C185 52.8 215 53.4 236 53.8 Z" fill="url(#cGlass)"/>
      <path d="M157 52 L158 19.3 L102 19.3 C96 19.4 92 20.5 89.5 23 L80 50.2 C105 50.9 130 51.5 157 52 Z" fill="url(#cGlass)"/>
      <path d="M205 17.5 L251 54.5 L247 54.5 L202.5 19.5 Z" fill="#41576a" opacity=".85"/>
      <path d="M78.5 49.6 L87.6 22.6 C89 20.4 91 19.5 94 19.3 L52 18.2 C48 18.3 45.6 19.5 44 22 L34.5 39.8 C36 40.8 39 42 42 43 C54 46.6 66 48.9 78.5 49.6 Z" fill="url(#cHoney)"/>
      <path d="M24.5 50 L39.4 21.6 L43.4 20 L29.5 48.6 Z" fill="url(#cGlass)" opacity=".9"/>
      <path d="M128 19.7 L146 19.6 L128 51.6 L110 51.2 Z M196 21 L205 28 L188 53.2 L177 53 Z" fill="#fff" opacity=".07"/>
      <path d="M52 16.9 C88 13.6 140 11.4 188 13.4" fill="none" stroke="rgba(255,255,255,.22)" stroke-width=".8"/>
      <!-- linjer, døre og detaljer -->
      <path d="M318 74 C285 69 250 66.5 200 65.5 C150 64.5 80 63.5 20 63" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.4" transform="translate(0 1.3)"/>
      <path d="M318 74 C285 69 250 66.5 200 65.5 C150 64.5 80 63.5 20 63" fill="none" stroke="rgba(255,255,255,.6)" stroke-width=".85"/>
      <g fill="none" stroke="rgba(28,33,38,.5)" stroke-width=".7">
        <path d="M244.5 57 C243 72 242.5 86 245 99"/><path d="M160 52.5 L159.5 109.5"/><path d="M76.5 51 C79 64 88 74 99 79.5"/>
      </g>
      <path d="M204 63.8 L219 63.8 M120 62.8 L134 62.8" stroke="#3a4147" stroke-width="1.7" stroke-linecap="round"/>
      <path d="M204.5 62.9 L218.5 62.9 M120.5 61.9 L133.5 61.9" stroke="rgba(255,255,255,.55)" stroke-width=".6" stroke-linecap="round"/>
      <path d="M95.8 115 L246.5 115 L246 109.5 C200 110.2 140 110.2 96.5 109.5 Z" fill="#1b1f23"/>
      <!-- front: lygte og grill -->
      <path d="M298 64.5 C306 65 314 66.8 320.5 71.5 L320 74 C313 70.5 305 68.8 297.5 68.3 Z" fill="#f4f9ff" style="filter:drop-shadow(0 0 3px #fff)"/>
      <path d="M309 99 C315 99 320 98 322 96.5 L322 98 C322 106 319 111 312 114 L300 114.6 C302 108 305 102 309 99 Z" fill="#15181c"/>
      <!-- bag: baglygte, diffuser og ladeklap -->
      <path d="M22.4 52.6 L37 53.6 C37.6 53.7 37.9 54.2 37.7 54.7 L36.8 57.8 L21.5 57.3 Z" fill="#d1102c" style="filter:drop-shadow(0 0 3px #ff2747)"/>
      <path d="M20 98 L20 104 C20 110 23 114 30 115 L48.8 115 L47 109 C38 106 29 102 20 98 Z" fill="#15181c"/>
      <rect x="35.5" y="64" width="11" height="7" rx="1.8" fill="${charging ? "#0e1a17" : "none"}" stroke="rgba(30,35,40,.55)" stroke-width=".6"/>
    </g>
    <!-- spejl -->
    <path d="M240 51.5 C243 47.5 250 46 257 46.8 C259 47 260 48.5 259.5 50 L257.5 53 C252 53.6 245 53.4 241 52.8 Z" fill="url(#cBlack)"/>
    ${charging ? `
    <path d="M41 67.5 C30 82 16 95 -12 112" fill="none" stroke="#14181c" stroke-width="4.2" stroke-linecap="round"/>
    <path d="M41 67.5 C30 82 16 95 -12 112" fill="none" stroke="#5af2b5" stroke-width="2" stroke-linecap="round" stroke-dasharray=".1 8" class="flow-anim rev" style="--dur:.9s;--c:#5af2b5"/>
    <circle cx="41" cy="67.5" r="2.6" fill="#5af2b5" style="filter:drop-shadow(0 0 5px #5af2b5)"><animate attributeName="opacity" values="1;.35;1" dur="1.8s" repeatCount="indefinite"/></circle>` : ""}
    ${wheel(72.3, 98)}${wheel(270, 98)}
  </g>
  </svg>`;
}
