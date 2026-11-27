"""Vejret fra Open-Meteo (gratis, ingen nøgle) - bruges til vejr-chip, prognose og vejr-effekter.

https://open-meteo.com  (data fra bl.a. DMI's HARMONIE-model for Danmark)
"""
from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from ..store import Store, iso, utcnow

LOG = logging.getLogger(__name__)
URL = "https://api.open-meteo.com/v1/forecast"

# WMO-vejrkode -> (dansk tekst, ikon, effekt)
WMO: dict[int, tuple[str, str, str]] = {
    0: ("Klart", "clear", "clear"),
    1: ("Overvejende klart", "partly", "clear"),
    2: ("Delvist skyet", "partly", "cloudy"),
    3: ("Overskyet", "cloudy", "cloudy"),
    45: ("Tåge", "fog", "fog"),
    48: ("Rimtåge", "fog", "fog"),
    51: ("Let støvregn", "drizzle", "drizzle"),
    53: ("Støvregn", "drizzle", "drizzle"),
    55: ("Kraftig støvregn", "drizzle", "rain"),
    56: ("Let isslag", "sleet", "sleet"),
    57: ("Isslag", "sleet", "sleet"),
    61: ("Let regn", "rain", "rain"),
    63: ("Regn", "rain", "rain"),
    65: ("Kraftig regn", "rain", "heavy-rain"),
    66: ("Let isregn", "sleet", "sleet"),
    67: ("Isregn", "sleet", "sleet"),
    71: ("Let sne", "snow", "snow"),
    73: ("Sne", "snow", "snow"),
    75: ("Kraftigt snefald", "snow", "heavy-snow"),
    77: ("Snekorn", "snow", "snow"),
    80: ("Lette regnbyger", "showers", "rain"),
    81: ("Regnbyger", "showers", "rain"),
    82: ("Kraftige regnbyger", "showers", "heavy-rain"),
    85: ("Snebyger", "snow", "snow"),
    86: ("Kraftige snebyger", "snow", "heavy-snow"),
    95: ("Torden", "thunder", "thunder"),
    96: ("Torden med hagl", "thunder", "thunder"),
    99: ("Kraftig torden med hagl", "thunder", "thunder"),
}


def describe(code: int | None) -> tuple[str, str, str]:
    return WMO.get(int(code), ("Ukendt", "cloudy", "cloudy")) if code is not None else ("–", "cloudy", "none")


class WeatherProvider(threading.Thread):
    def __init__(self, cfg: dict, store: Store, tz: ZoneInfo) -> None:
        super().__init__(name="weather", daemon=True)
        self.cfg = cfg
        self.store = store
        self.tz = tz
        self.http = httpx.Client(timeout=20.0, headers={"User-Agent": "solar-dashboard/1.0"})
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval = max(int(self.cfg.get("refresh_minutes") or 10), 5) * 60
        while not self._stop.is_set():
            wait = interval
            try:
                self.store.set("weather", self.fetch())
            except Exception as err:  # noqa: BLE001
                LOG.warning("Vejr: %s", err)
                cur = self.store.get("weather") or {}
                cur.update({"ok": bool(cur.get("current")), "error": str(err)})
                self.store.set("weather", cur)
                wait = 300
            self._stop.wait(wait)

    def fetch(self) -> dict:
        params = {
            "latitude": self.cfg["latitude"],
            "longitude": self.cfg["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,is_day,precipitation,rain,showers,"
                       "snowfall,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "hourly": "temperature_2m,weather_code,precipitation_probability,precipitation,is_day,wind_speed_10m,wind_direction_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_sum,"
                     "precipitation_probability_max,wind_speed_10m_max",
            "timezone": str(self.tz),
            "wind_speed_unit": "ms",
            "forecast_days": 6,
        }
        r = self.http.get(URL, params=params)
        r.raise_for_status()
        return self.parse(r.json())

    def parse(self, d: dict) -> dict:
        cur = d.get("current") or {}
        now = datetime.now(self.tz)
        hourly = []
        h = d.get("hourly") or {}
        for i, t in enumerate(h.get("time") or []):
            tt = datetime.fromisoformat(t).replace(tzinfo=self.tz)
            if tt < now.replace(minute=0, second=0, microsecond=0) or len(hourly) >= 24:
                continue
            code = h["weather_code"][i]
            hourly.append({
                "time": tt.isoformat(),
                "temp": h["temperature_2m"][i],
                "code": code,
                "icon": describe(code)[1],
                "is_day": bool(h.get("is_day", [1] * (i + 1))[i]),
                "precip": h.get("precipitation", [0] * (i + 1))[i],
                "precip_prob": (h.get("precipitation_probability") or [None] * (i + 1))[i],
                "wind": (h.get("wind_speed_10m") or [None] * (i + 1))[i],
                "wind_dir": (h.get("wind_direction_10m") or [None] * (i + 1))[i],
            })
        # "overskyet" i de aktuelle data men nedbør i prognosen for denne time (eller målt nedbør): brug det
        code = cur.get("weather_code")
        temp = cur.get("temperature_2m")
        if code is not None and code < 51 and hourly and (hourly[0]["code"] or 0) >= 51:
            code = hourly[0]["code"]
        precip = cur.get("precipitation") or 0.0
        snowfall = cur.get("snowfall") or 0.0
        if code is not None and code < 51 and (snowfall > 0.05 or precip > 0.05):
            code = 71 if (snowfall > 0.05 or (temp is not None and temp <= 1.0)) else 61
        text, ic, effect = describe(code)
        days = []
        dd = d.get("daily") or {}
        for i, t in enumerate(dd.get("time") or []):
            code = dd["weather_code"][i]
            days.append({
                "date": t,
                "code": code,
                "icon": describe(code)[1],
                "text": describe(code)[0],
                "max": dd["temperature_2m_max"][i],
                "min": dd["temperature_2m_min"][i],
                "precip": (dd.get("precipitation_sum") or [None] * (i + 1))[i],
                "precip_prob": (dd.get("precipitation_probability_max") or [None] * (i + 1))[i],
                "wind": (dd.get("wind_speed_10m_max") or [None] * (i + 1))[i],
                "sunrise": (dd.get("sunrise") or [None] * (i + 1))[i],
                "sunset": (dd.get("sunset") or [None] * (i + 1))[i],
            })
        intensity = cur.get("precipitation") or 0.0
        return {
            "ok": True,
            "demo": False,
            "updated": iso(utcnow()),
            "place": self.cfg.get("name") or "",
            "current": {
                "temp": cur.get("temperature_2m"),
                "feels_like": cur.get("apparent_temperature"),
                "humidity": cur.get("relative_humidity_2m"),
                "code": code,
                "text": text,
                "icon": ic,
                "effect": effect,
                "is_day": bool(cur.get("is_day", 1)),
                "precip": intensity,
                "snowfall": cur.get("snowfall"),
                "cloud_cover": cur.get("cloud_cover"),
                "wind": cur.get("wind_speed_10m"),
                "wind_dir": cur.get("wind_direction_10m"),
                "gusts": cur.get("wind_gusts_10m"),
            },
            "hourly": hourly,
            "daily": days,
        }


def demo_weather(tz: ZoneInfo, effect: str = "snow") -> dict:
    """Vejr til demo-visning."""
    now = datetime.now(tz)
    code = {"snow": 73, "rain": 63, "clear": 0, "cloudy": 3, "thunder": 95, "fog": 45, "drizzle": 53}.get(effect, 73)
    text, ic, eff = describe(code)
    is_day = 8 <= now.hour < 16
    hourly = []
    for i in range(24):
        t = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=i)
        c = code if i < 5 else 3 if i < 12 else 2
        hourly.append({"time": t.isoformat(), "temp": round(-1.5 + 2.5 * math.sin((t.hour - 9) / 24 * 2 * math.pi), 1),
                       "code": c, "icon": describe(c)[1], "is_day": 8 <= t.hour < 16, "precip": 0.6 if i < 5 else 0,
                       "precip_prob": 80 if i < 5 else 20,
                       "wind": round(4 + 2 * math.sin(i / 4), 1), "wind_dir": 250 + i * 3})
    days = []
    for i, (c, mx, mn) in enumerate([(code, 1, -3), (2, 3, -2), (61, 5, 1), (3, 4, 0), (0, 2, -4), (71, 0, -3)]):
        d = (now + timedelta(days=i)).date().isoformat()
        days.append({"date": d, "code": c, "icon": describe(c)[1], "text": describe(c)[0], "max": mx, "min": mn,
                     "wind": 6 + i, "precip": 2.1 if c in (73, 61, 71, 63) else 0, "precip_prob": 70 if c in (73, 61, 71, 63) else 10,
                     "sunrise": f"{d}T08:21", "sunset": f"{d}T15:52"})
    return {
        "ok": True, "demo": True, "updated": iso(utcnow()), "place": "",
        "current": {"temp": -0.8, "feels_like": -4.6, "humidity": 91, "code": code, "text": text, "icon": ic,
                    "effect": eff, "is_day": is_day, "precip": 0.8, "snowfall": 0.6, "cloud_cover": 100,
                    "wind": 4.2, "wind_dir": 250, "gusts": 8.5},
        "hourly": hourly, "daily": days,
    }
