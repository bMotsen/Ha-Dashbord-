"""VW ID.3 via Volkswagen-kontoen (samme login som "Volkswagen"-appen).

Bruger biblioteket CarConnectivity (efterfølgeren til WeConnect-python):
  pip install carconnectivity carconnectivity-connector-volkswagen
VW tillader højst en opdatering hvert 3. minut, så standard er hvert 5. minut.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from ..config import DATA_DIR
from ..store import Store, iso, utcnow

LOG = logging.getLogger(__name__)


def _val(obj: Any, *path: str) -> Any:
    """Sikker opslag i CarConnectivity-objekter: _val(vehicle, "charging", "state")."""
    cur = obj
    for p in path:
        if cur is None:
            return None
        cur = getattr(cur, p, None)
    if cur is None:
        return None
    if getattr(cur, "enabled", True) is False:
        return None
    v = getattr(cur, "value", cur)
    if hasattr(v, "value") and not isinstance(v, (int, float, str, datetime)):
        v = v.value  # Enum -> streng
    return v


class VWProvider(threading.Thread):
    def __init__(self, cfg: dict, store: Store) -> None:
        super().__init__(name="vw", daemon=True)
        self.cfg = cfg
        self.store = store
        self._stop = threading.Event()
        self.cc = None

    def stop(self) -> None:
        self._stop.set()

    def _connect(self) -> None:
        from carconnectivity import carconnectivity  # importeres først her (tungt bibliotek)

        conn_cfg: dict[str, Any] = {
            "username": self.cfg["username"],
            "password": self.cfg["password"],
            "interval": max(int(self.cfg.get("interval_seconds") or 300), 180),
        }
        if self.cfg.get("spin"):
            conn_cfg["spin"] = str(self.cfg["spin"])
        config = {
            "carConnectivity": {
                "log_level": "warning",
                "connectors": [{"type": "volkswagen", "config": conn_cfg}],
                "plugins": [],
            }
        }
        self.cc = carconnectivity.CarConnectivity(
            config=config,
            tokenstore_file=str(DATA_DIR / "vw_tokenstore.json"),
            cache_file=str(DATA_DIR / "vw_cache.json"),
        )

    def run(self) -> None:
        interval = max(int(self.cfg.get("interval_seconds") or 300), 180)
        while not self._stop.is_set():
            wait = interval
            try:
                if self.cc is None:
                    self._connect()
                self.cc.fetch_all()
                self.cc.persist()
                self.store.set("car", self.parse())
            except Exception as err:  # noqa: BLE001
                LOG.warning("VW: %s", err)
                cur = self.store.get("car") or {}
                msg = str(err)
                low = msg.lower()
                if "authorization url" in low or "weconnect failure" in low:
                    msg = "VW's login-server svarer ikke. Prøver igen om lidt"
                elif "password" in low or "credentials" in low or "unauthorized" in low:
                    msg = "VW afviste e-mail/kodeord"
                elif "terms" in low or "consent" in low:
                    msg = "Godkend VW's nye vilkår i Volkswagen-appen"
                cur.update({"ok": False, "error": msg, "source": "vw", "name": self.cfg.get("name", "ID.3")})
                self.store.set("car", cur)
                self.cc = None if "auth" in str(err).lower() or "login" in str(err).lower() else self.cc
                wait = 600
            self._stop.wait(wait)

    def _vehicle(self):
        garage = self.cc.get_garage() if self.cc else None
        if garage is None:
            return None
        vin = (self.cfg.get("vin") or "").upper()
        if vin:
            return garage.get_vehicle(vin)
        vehicles = garage.list_vehicles()
        for v in vehicles:
            if hasattr(v, "charging"):
                return v
        return vehicles[0] if vehicles else None

    def set_climate(self, start: bool) -> dict:
        v = self._vehicle()
        if v is None:
            raise RuntimeError("Ingen bil fundet")
        cmd = v.climatization.commands.commands.get("start-stop") if v.climatization.commands else None
        if cmd is None or not getattr(cmd, "enabled", True):
            raise RuntimeError("Bilen understøtter ikke fjernstyret klima")
        cmd.value = "start" if start else "stop"
        car = self.store.get("car") or {}
        car["climatization"] = "heating" if start else "off"
        self.store.set("car", car)
        return {"on": start}

    def set_target(self, level: float) -> dict:
        level = max(50, min(100, int(round(level / 10.0)) * 10))
        v = self._vehicle()
        if v is None:
            raise RuntimeError("Ingen bil fundet")
        tl = v.charging.settings.target_level
        if not getattr(tl, "enabled", False):
            raise RuntimeError("Bilen understøtter ikke at ændre ladegrænsen")
        tl.set_value(float(level))
        car = self.store.get("car") or {}
        car["target_soc"] = level
        self.store.set("car", car)
        return {"target_soc": level}

    def parse(self) -> dict:
        v = self._vehicle()
        if v is None:
            raise RuntimeError("Ingen bil fundet på VW-kontoen")
        drive = v.get_electric_drive() if hasattr(v, "get_electric_drive") else None
        state = _val(v, "charging", "state")
        eta = _val(v, "charging", "estimated_date_reached")
        rng = _val(drive, "range")
        rng_unit = getattr(getattr(drive, "range", None), "unit", None)
        if rng is not None and rng_unit is not None and "mi" in str(getattr(rng_unit, "value", rng_unit)).lower():
            rng = rng * 1.609
        return {
            "ok": True,
            "demo": False,
            "source": "vw",
            "updated": iso(utcnow()),
            "name": self.cfg.get("name") or _val(v, "model") or "ID.3",
            "model": _val(v, "model"),
            "vin": _val(v, "vin"),
            "soc": _val(drive, "level"),
            "range_km": round(rng) if rng is not None else None,
            "charging_state": state,          # off / ready_for_charging / charging / conservation / error / discharging
            "charging": state == "charging",
            "charge_power_kw": _val(v, "charging", "power"),
            "charge_type": _val(v, "charging", "type"),
            "plug": _val(v, "charging", "connector", "connection_state"),   # connected / disconnected
            "plug_lock": _val(v, "charging", "connector", "lock_state"),
            "target_soc": _val(v, "charging", "settings", "target_level"),
            "eta": eta.isoformat() if isinstance(eta, datetime) else None,
            "odometer_km": _val(v, "odometer"),
            "outside_temp": _val(v, "outside_temperature"),
            "climatization": _val(v, "climatization", "state"),
            "vehicle_state": _val(v, "state"),
            "battery_capacity_kwh": self.cfg.get("battery_capacity_kwh"),
        }
