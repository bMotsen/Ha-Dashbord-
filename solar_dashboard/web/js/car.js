// VW ID.3 (billede). Bilen vender mod venstre; ladeklappen sidder bagtil til højre.
export function carSVG(charging) {
  return `<div class="car-photo ${charging ? "charging" : ""}"><div class="car-wrap">
    <img src="img/id3.png" alt="VW ID.3" draggable="false">
    ${charging ? `<svg viewBox="0 0 900 387" aria-hidden="true">
      <path d="M770 205 C 830 230, 870 290, 900 345" fill="none" stroke="#14181c" stroke-width="9" stroke-linecap="round"/>
      <path d="M770 205 C 830 230, 870 290, 900 345" fill="none" stroke="#5af2b5" stroke-width="4" stroke-linecap="round" stroke-dasharray=".1 16" class="flow-anim rev" style="--dur:.9s;--c:#5af2b5"/>
      <circle cx="770" cy="205" r="7" fill="#5af2b5" style="filter:drop-shadow(0 0 8px #5af2b5)"><animate attributeName="opacity" values="1;.35;1" dur="1.8s" repeatCount="indefinite"/></circle>
    </svg>` : ""}
  </div></div>`;
}
