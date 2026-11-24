"""Dagens energiregnskab: kWh, kroner for salg/køb og en kurve over dagen.

Bruger enhedens egne tællere når de findes (mest præcist), ellers
integreres effekten over tid. Gemmes på disk så en genstart ikke nulstiller dagen.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .config import DATA_DIR
from .store import load_json, save_json

LOG = logging.getLogger(__name__)

METRICS = ("pv", "load", "import", "export", "charge", "discharge")
BUCKET_MIN = 5
MAX_GAP_S = 120  # længere huller integreres ikke (fx når Pi'en har været slukket)

PriceLookup = Callable[[datetime], Optional[tuple[float, float]]]


class EnergyTracker:
    def __init__(self, tz: ZoneInfo, price_lookup: PriceLookup | None = None, name: str = "energy_today",
                 source: str = "") -> None:
        self.tz = tz
        self.price_lookup = price_lookup
        self.path = DATA_DIR / f"{name}.json"
        self._lock = threading.RLock()
        self._last_save = 0.0
        self.source = source
        loaded = load_json(self.path, None)
        today = datetime.now(self.tz).date().isoformat()
        if loaded and loaded.get("date") == today and loaded.get("source", "") == source:
            self.s = loaded
        else:  # ny dag, eller skift fra demo til rigtige data
            same = loaded and loaded.get("source", "") == source
            self.s = self._new_day(today, yesterday=self._summarize(loaded) if same else None)
        self.s["source"] = source

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _new_day(date: str, yesterday: dict | None = None) -> dict:
        return {
            "date": date,
            "kwh": {m: 0.0 for m in METRICS},
            "baseline": {},
            "money": {"export_dkk": 0.0, "import_dkk": 0.0},
            "history": [],
            "bucket": None,
            "last_ts": None,
            "yesterday": yesterday,
        }

    def _summarize(self, s: dict) -> dict:
        k = s.get("kwh", {})
        load = k.get("load", 0.0)
        pv = k.get("pv", 0.0)
        imp = k.get("import", 0.0)
        exp = k.get("export", 0.0)
        return {
            "date": s.get("date"),
            "pv_kwh": round(pv, 2),
            "load_kwh": round(load, 2),
            "import_kwh": round(imp, 2),
            "export_kwh": round(exp, 2),
            "charge_kwh": round(k.get("charge", 0.0), 2),
            "discharge_kwh": round(k.get("discharge", 0.0), 2),
            "export_dkk": round(s.get("money", {}).get("export_dkk", 0.0), 2),
            "import_dkk": round(s.get("money", {}).get("import_dkk", 0.0), 2),
            "self_sufficiency": round(max(0.0, min(1.0, (load - imp) / load)) * 100) if load > 0.05 else None,
            "self_consumption": round(max(0.0, min(1.0, (pv - exp) / pv)) * 100) if pv > 0.05 else None,
        }

    # ------------------------------------------------------------------ update
    def update(
        self,
        powers_w: dict[str, float],
        today_kwh: dict[str, float | None] | None = None,
        totals_kwh: dict[str, float | None] | None = None,
        now: datetime | None = None,
    ) -> None:
        """powers_w: pv, load, grid (+ = køb), battery (+ = opladning)."""
        now = now or datetime.now(self.tz)
        today_kwh = today_kwh or {}
        totals_kwh = totals_kwh or {}
        with self._lock:
            if now.date().isoformat() != self.s["date"]:
                self._flush_bucket()
                self.s = self._new_day(now.date().isoformat(), yesterday=self._summarize(self.s))
                self.s["source"] = self.source

            grid = powers_w.get("grid") or 0.0
            bat = powers_w.get("battery") or 0.0
            p_kw = {
                "pv": max(powers_w.get("pv") or 0.0, 0.0) / 1000,
                "load": max(powers_w.get("load") or 0.0, 0.0) / 1000,
                "import": max(grid, 0.0) / 1000,
                "export": max(-grid, 0.0) / 1000,
                "charge": max(bat, 0.0) / 1000,
                "discharge": max(-bat, 0.0) / 1000,
            }

            dt_h = 0.0
            recent = False  # kroner tælles kun når forrige måling er frisk (ellers kendes prisen ikke)
            if self.s["last_ts"]:
                dt = (now - datetime.fromisoformat(self.s["last_ts"])).total_seconds()
                if 0 < dt <= MAX_GAP_S:
                    dt_h = dt / 3600
                recent = 0 < dt <= 600
            self.s["last_ts"] = now.isoformat()

            kwh = self.s["kwh"]
            base = self.s["baseline"]
            delta: dict[str, float] = {}
            for m in METRICS:
                old = kwh.get(m, 0.0)
                if today_kwh.get(m) is not None:
                    new = float(today_kwh[m])
                elif totals_kwh.get(m) is not None:
                    tot = float(totals_kwh[m])
                    if m not in base or tot - base[m] < old - 0.5:
                        base[m] = tot - old  # første måling i dag eller tæller nulstillet
                    new = tot - base[m]
                else:
                    new = old + p_kw[m] * dt_h
                delta[m] = max(new - old, 0.0)
                kwh[m] = new

            if self.price_lookup and recent:
                prices = self.price_lookup(now)
                if prices:
                    buy, sell = prices
                    self.s["money"]["import_dkk"] += delta["import"] * buy
                    self.s["money"]["export_dkk"] += delta["export"] * sell

            self._add_to_bucket(now, p_kw)
            if now.timestamp() - self._last_save > 60:
                self._last_save = now.timestamp()
                save_json(self.path, self.s)

    def _add_to_bucket(self, now: datetime, p_kw: dict[str, float]) -> None:
        slot = now.replace(minute=(now.minute // BUCKET_MIN) * BUCKET_MIN, second=0, microsecond=0)
        key = slot.strftime("%H:%M")
        b = self.s.get("bucket")
        if b and b["t"] != key:
            self._flush_bucket()
            b = None
        if not b:
            b = {"t": key, "n": 0, "pv": 0.0, "load": 0.0, "grid": 0.0, "bat": 0.0}
            self.s["bucket"] = b
        b["n"] += 1
        b["pv"] += p_kw["pv"]
        b["load"] += p_kw["load"]
        b["grid"] += p_kw["import"] - p_kw["export"]
        b["bat"] += p_kw["charge"] - p_kw["discharge"]

    def _flush_bucket(self) -> None:
        b = self.s.get("bucket")
        if b and b["n"]:
            n = b["n"]
            self.s["history"].append({
                "t": b["t"],
                "pv": round(b["pv"] / n, 3),
                "load": round(b["load"] / n, 3),
                "grid": round(b["grid"] / n, 3),
                "bat": round(b["bat"] / n, 3),
            })
        self.s["bucket"] = None

    # ------------------------------------------------------------------ demo
    def prefill(self, fn: Callable[[datetime], dict[str, float]], step_s: int = 60) -> None:
        """Fyld dagen ud fra midnat til nu med en syntetisk kurve (bruges i demo)."""
        with self._lock:
            if self.s["history"]:
                return
            now = datetime.now(self.tz)
            t = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self.s["last_ts"] = None
            while t < now - timedelta(seconds=step_s):
                self.update(fn(t), now=t)
                t += timedelta(seconds=step_s)

    # ------------------------------------------------------------------ read
    def summary(self) -> dict:
        with self._lock:
            out = self._summarize(self.s)
            hist = list(self.s["history"])
            b = self.s.get("bucket")
            if b and b["n"]:
                n = b["n"]
                hist.append({"t": b["t"], "pv": round(b["pv"] / n, 3), "load": round(b["load"] / n, 3),
                             "grid": round(b["grid"] / n, 3), "bat": round(b["bat"] / n, 3)})
            out["history"] = hist
            out["yesterday"] = self.s.get("yesterday")
            return out

    def save(self) -> None:
        with self._lock:
            save_json(self.path, self.s)
