"""Tæller for elbil-laderen: samlet kWh, kroner og antal opladninger (gemmes, så genstart ikke nulstiller)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .config import DATA_DIR
from .store import load_json, save_json

LOG = logging.getLogger(__name__)
PriceLookup = Callable[[datetime], Optional[tuple[float, float]]]


class ChargerStats:
    def __init__(self, tz: ZoneInfo, price_lookup: PriceLookup | None = None, offset_kwh: float = 0.0) -> None:
        self.tz = tz
        self.price_lookup = price_lookup
        self.offset = float(offset_kwh or 0)
        self.path = DATA_DIR / "charger_stats.json"
        self._lock = threading.RLock()
        self.s = load_json(self.path, None) or {
            "since": datetime.now(tz).date().isoformat(), "total_kwh": 0.0, "total_dkk": 0.0,
            "sessions": 0, "last_kwh": None, "days": {},
        }
        self._saved = 0.0

    def update(self, view: dict) -> None:
        k = view.get("session_kwh") if view else None
        if not view or not view.get("ok") or k is None:
            return
        now = datetime.now(self.tz)
        with self._lock:
            last = self.s.get("last_kwh")
            if last is None:
                delta = k
            elif k >= last - 0.001:
                delta = k - last
            else:  # tælleren er nulstillet = ny opladning
                delta = k
                self.s["sessions"] += 1
            if last is None and k > 0:
                self.s["sessions"] += 1
            self.s["last_kwh"] = k
            if delta > 0.0005:
                price = None
                if self.price_lookup:
                    p = self.price_lookup(now)
                    price = p[0] if p else None
                dkk = delta * price if price is not None else 0.0
                self.s["total_kwh"] += delta
                self.s["total_dkk"] += dkk
                day = self.s["days"].setdefault(now.date().isoformat(), {"kwh": 0.0, "dkk": 0.0})
                day["kwh"] += delta
                day["dkk"] += dkk
                cutoff = (now - timedelta(days=400)).date().isoformat()
                self.s["days"] = {d: v for d, v in self.s["days"].items() if d >= cutoff}
            if now.timestamp() - self._saved > 60 or delta > 0.0005:
                self._saved = now.timestamp()
                save_json(self.path, self.s)

    def summary(self) -> dict:
        now = datetime.now(self.tz)
        with self._lock:
            days = self.s.get("days", {})
            month = now.strftime("%Y-%m")
            week0 = (now - timedelta(days=6)).date().isoformat()
            m = [v for d, v in days.items() if d.startswith(month)]
            w = [v for d, v in days.items() if d >= week0]
            return {
                "since": self.s.get("since"),
                "total_kwh": round(self.s["total_kwh"] + self.offset, 1),
                "total_dkk": round(self.s["total_dkk"], 0),
                "month_kwh": round(sum(v["kwh"] for v in m), 1),
                "month_dkk": round(sum(v["dkk"] for v in m), 0),
                "week_kwh": round(sum(v["kwh"] for v in w), 1),
                "sessions": self.s.get("sessions", 0),
            }
