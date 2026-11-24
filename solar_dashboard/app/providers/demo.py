"""Realistiske demo-data, så dashboardet kan ses før alt er sat op.

Hver del (sol/batteri, bil, lader, Tuya-enheder) bruges kun som demo hvis den rigtige
udbyder ikke er slået til. Demo-felter er markeret med "demo": true i API'et.
"""
from __future__ import annotations

import math
import random
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..energy import EnergyTracker
from ..store import Store, iso, utcnow

BAT_CAP = 15.0    # kWh
CAR_CAP = 58.0    # kWh (ID.3 Pro)

DEMO_DEVICES = [
    {"id": "demo-stue", "name": "Stue loftlampe", "category": "dj", "icon": "lamp-ceiling", "on": True, "brightness": 80},
    {"id": "demo-kokken", "name": "Køkken spots", "category": "dj", "icon": "lightbulb", "on": False, "brightness": 100},
    {"id": "demo-kaffe", "name": "Kaffemaskine", "category": "cz", "icon": "coffee", "on": True, "power_w": 3.2},
    {"id": "demo-vask", "name": "Vaskemaskine", "category": "cz", "icon": "washing-machine", "on": True, "power_w": 318.0},
    {"id": "demo-ude", "name": "Udendørslys", "category": "cz", "icon": "lamp-floor", "on": False, "power_w": 0.0},
    {"id": "demo-tv", "name": "TV stik", "category": "cz", "icon": "tv", "on": False, "power_w": 0.0},
    {"id": "demo-sove", "name": "Soveværelse", "category": "wsdcg", "icon": "thermometer", "on": None, "temp": 20.8, "humidity": 46},
    {"id": "demo-bad", "name": "Varmeblæser bad", "category": "qn", "icon": "heater", "on": False, "power_w": 0.0},
    {"id": "demo-dor", "name": "Hoveddør", "category": "mcs", "icon": "door-open", "on": None, "open": False, "battery": 90},
]


class DemoProvider(threading.Thread):
    def __init__(self, store: Store, tracker: EnergyTracker, tz: ZoneInfo, parts: set[str]) -> None:
        super().__init__(name="demo", daemon=True)
        self.store = store
        self.tracker = tracker
        self.tz = tz
        self.parts = parts            # {"solar", "car", "charger", "devices"}
        self._stop = threading.Event()
        self.rng = random.Random(42)
        self.bat_soc = 28.0
        self.car_soc = 34.0
        self.car_target = 80.0
        self.session_kwh = 0.0
        self.last_t: datetime | None = None
        self.last: dict = {}
        self.devices = [dict(d) for d in DEMO_DEVICES]
        self.charger_enabled = True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ simulation
    def _pv(self, t: datetime) -> float:
        h = t.hour + t.minute / 60
        if not 6.0 < h < 20.0:
            return 0.0
        base = 7200 * math.sin(math.pi * (h - 6) / 14) ** 1.6
        cloud = 1 - 0.28 * max(0.0, math.sin(h * 2.3)) ** 12
        return max(base * cloud * (1 + self.rng.uniform(-0.02, 0.02)), 0.0)

    def _house(self, t: datetime) -> float:
        h = t.hour + t.minute / 60
        w = 320 + 650 * math.exp(-((h - 7.3) ** 2) / 0.6) + 1300 * math.exp(-((h - 18.2) ** 2) / 1.4)
        w += 450 if 14.5 < h < 16.2 else 0  # vaskemaskine
        return w * (1 + self.rng.uniform(-0.05, 0.05))

    def step(self, t: datetime) -> dict:
        dt_h = 0.0
        if self.last_t is not None:
            dt_h = max(min((t - self.last_t).total_seconds(), 300), 0) / 3600
            if self.last_t.date() != t.date():
                self.session_kwh = 0.0
        self.last_t = t
        h = t.hour + t.minute / 60
        pv = self._pv(t)
        house = self._house(t)

        # batteriet lades først, derefter bilen på solens overskud (bilen kom hjem kl. 12:30)
        rest = pv - house
        if rest > 0:
            bat = min(rest, 1100.0) if self.bat_soc < 97 else 0.0
        else:
            bat = -min(-rest, 3000.0) if self.bat_soc > 12 else 0.0
        car = 0.0
        surplus = rest - max(bat, 0.0)
        if self.charger_enabled and self.car_soc < self.car_target and h >= 12.5 and surplus > 1700:
            car = min(3680.0, surplus - 300)
        self.car_soc = min(self.car_soc + car / 1000 * dt_h / CAR_CAP * 100, 100.0)
        self.session_kwh += car / 1000 * dt_h
        self.bat_soc = max(min(self.bat_soc + bat / 1000 * dt_h / BAT_CAP * 100, 100.0), 0.0)
        grid = house + car + bat - pv
        load = house + car
        self.last = {"pv": pv, "house": house, "car": car, "battery": bat, "grid": grid, "load": load}
        return {"pv": pv, "load": load, "grid": grid, "battery": bat}

    # ------------------------------------------------------------------ publish
    def publish(self, now: datetime) -> None:
        p = self.last
        if "solar" in self.parts:
            bat = p["battery"]
            eta = None
            if bat > 50:
                eta = round((100 - self.bat_soc) / 100 * BAT_CAP / (bat / 1000) * 60)
            elif bat < -50:
                eta = round(self.bat_soc / 100 * BAT_CAP / (-bat / 1000) * 60)
            self.store.set("solar", {
                "ok": True, "demo": True, "source": "demo", "updated": iso(utcnow()), "model": "ASW10kH-T3 (demo)",
                "pv_w": round(p["pv"]), "load_w": round(p["load"]), "grid_w": round(p["grid"]),
                "battery_w": round(bat), "battery_soc": round(self.bat_soc), "battery_soh": 99,
                "battery_state": "charging" if bat > 30 else "discharging" if bat < -30 else "idle",
                "battery_temp": 23.4, "battery_voltage": 204.6, "battery_capacity_kwh": BAT_CAP,
                "battery_eta_min": eta, "has_battery": True, "inverter_temp": 41.5, "inverter_status": "Normal",
            })
        charging = p["car"] > 100
        if "charger" in self.parts:
            self.store.set("charger", {
                "ok": True, "demo": True, "id": "demo-lader", "name": "Elbil lader", "online": True, "via": "demo",
                "state": "charging" if charging else ("connected" if self.car_soc < self.car_target else "finished"),
                "charging": charging, "power_kw": round(p["car"] / 1000, 2) if charging else 0.0,
                "session_kwh": round(self.session_kwh, 1), "current_a": 16, "switch_code": "switch",
                "on": self.charger_enabled, "confirm": True, "updated": iso(utcnow()),
            })
        if "car" in self.parts:
            remaining_h = None
            if charging:
                remaining_h = (self.car_target - self.car_soc) / 100 * CAR_CAP / max(p["car"] / 1000, 0.5)
            self.store.set("car", {
                "ok": True, "demo": True, "source": "demo", "updated": iso(utcnow()), "name": "ID.3", "model": "ID.3",
                "soc": round(self.car_soc), "range_km": round(self.car_soc / 100 * 410),
                "charging_state": "charging" if charging else "ready_for_charging",
                "charging": charging, "charge_power_kw": round(p["car"] / 1000, 1) if charging else 0.0,
                "charge_type": "ac" if charging else "off", "plug": "connected", "plug_lock": "locked",
                "target_soc": self.car_target,
                "eta": (now + timedelta(hours=remaining_h)).isoformat() if remaining_h else None,
                "odometer_km": 24873, "outside_temp": 9.5, "climatization": "off", "vehicle_state": "parked",
                "battery_capacity_kwh": CAR_CAP,
            })
        if "devices" in self.parts:
            items = []
            for d in self.devices:
                v = dict(d)
                v.update({"online": True, "via": "demo", "switch_code": "switch_1" if d["on"] is not None else None})
                if v.get("power_w") is not None and not v["on"]:
                    v["power_w"] = 0.0
                items.append(v)
            self.store.set("devices", {"ok": True, "demo": True, "items": items, "updated": iso(utcnow())})

    def run(self) -> None:
        if "solar" in self.parts:
            self.tracker.prefill(self.step)
        else:  # varm simulationen op så bil/lader har realistiske tal
            t = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
            while t < datetime.now(self.tz):
                self.step(t)
                t += timedelta(minutes=2)
        while not self._stop.is_set():
            now = datetime.now(self.tz)
            powers = self.step(now)
            if "solar" in self.parts:
                self.tracker.update(powers, now=now)
            self.publish(now)
            self._stop.wait(3)

    # ------------------------------------------------------------------ control
    def set_target(self, level: float) -> dict:
        self.car_target = max(50, min(100, int(round(level / 10.0)) * 10))
        self.publish(datetime.now(self.tz))
        return {"target_soc": self.car_target}

    def toggle(self, dev_id: str, value: bool | None = None) -> dict:
        if dev_id == "demo-lader":
            self.charger_enabled = (not self.charger_enabled) if value is None else bool(value)
            self.step(datetime.now(self.tz))
            self.publish(datetime.now(self.tz))
            return {"id": dev_id, "on": self.charger_enabled}
        for d in self.devices:
            if d["id"] == dev_id and d["on"] is not None:
                d["on"] = (not d["on"]) if value is None else bool(value)
                self.publish(datetime.now(self.tz))
                return {"id": dev_id, "on": d["on"]}
        raise KeyError(dev_id)
