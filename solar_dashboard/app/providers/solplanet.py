"""Solplanet (AISWEI) hybrid-inverter + batteri via donglens lokale HTTP-API.

Endepunkter (samme som Home Assistant-integrationen "home-assistant-solplanet" bruger):
  getdev.cgi?device=2              -> liste over invertere  {"inv":[{"isn": "...", "model": "..."}]}
  getdev.cgi                       -> dongle-info            {"psn": "...", ...}
  getdevdata.cgi?device=2&sn=SN    -> inverter  (pac W, etd 0.1 kWh, tmp 0.1 °C, vpv 0.1 V, ipv 0.01 A ...)
  getdevdata.cgi?device=3&sn=SN    -> elmåler   (pac W: + = køb / - = salg, itd/otd 0.01 kWh, iet/oet 0.1 kWh)
  getdevdata.cgi?device=4&sn=SN    -> batteri   (soc %, pb W, bst 1=hvile 2=lader 3=aflader, ppv W, tb 0.1 °C, vb 0.01 V)

Nyere dongle-firmware svarer på https (port 443, selvsigneret certifikat), ældre på http port 8484.
Kør `python tools/solplanet_probe.py <ip>` for at se de rå data fra netop din dongle.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from ..energy import EnergyTracker
from ..store import Store, iso, utcnow

LOG = logging.getLogger(__name__)

INVERTER_STATUS = {0: "Venter", 1: "Normal", 2: "Fejl", 4: "Tjekker"}
BATTERY_STATUS = {1: "idle", 2: "charging", 3: "discharging", 4: "fault"}


def _num(d: dict, key: str, scale: float = 1.0) -> float | None:
    v = d.get(key) if d else None
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v) * scale
    except (TypeError, ValueError):
        return None


class SolplanetClient:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.host = cfg["host"]
        self.base: str | None = None
        self.http = httpx.Client(timeout=8.0, verify=bool(cfg.get("verify_tls")))
        self.inverter_sn: str = cfg.get("inverter_sn") or ""
        self.dongle_sn: str = ""
        self.meter_sn: str | None = cfg.get("meter_sn") or None
        self.battery_sn: str | None = cfg.get("battery_sn") or None
        self.model: str = ""

    def _candidates(self) -> list[str]:
        scheme = (self.cfg.get("scheme") or "auto").lower()
        port = self.cfg.get("port")
        if scheme != "auto":
            port = port or (443 if scheme == "https" else 8484)
            return [f"{scheme}://{self.host}:{port}"]
        return [f"https://{self.host}:443", f"http://{self.host}:8484", f"http://{self.host}:80"]

    def get(self, endpoint: str) -> Any:
        assert self.base
        r = self.http.get(f"{self.base}/{endpoint}")
        r.raise_for_status()
        txt = r.text.strip()
        if not txt or not txt.startswith(("{", "[")):
            raise ValueError(f"Uventet svar fra {endpoint}: {txt[:80]!r}")
        return r.json()

    def connect(self) -> None:
        last_err: Exception | None = None
        for base in self._candidates():
            self.base = base
            try:
                inv = self.get("getdev.cgi?device=2")
                lst = inv.get("inv") or []
                if not self.inverter_sn and lst:
                    self.inverter_sn = lst[0].get("isn", "")
                if lst:
                    self.model = lst[0].get("model", "") or ""
                LOG.info("Solplanet: forbundet til %s (inverter %s %s)", base, self.inverter_sn, self.model)
                try:
                    dongle = self.get("getdev.cgi")
                    self.dongle_sn = dongle.get("psn") or dongle.get("sn") or ""
                except Exception:  # noqa: BLE001
                    pass
                return
            except Exception as err:  # noqa: BLE001
                last_err = err
                LOG.debug("Solplanet: %s svarede ikke: %s", base, err)
        self.base = None
        raise ConnectionError(f"Kan ikke nå Solplanet-dongle på {self.host}: {last_err}")

    def _device_data(self, device: int, sn_attr: str) -> dict:
        """Hent data for meter/batteri. SN er ikke ens på alle firmwares, så vi prøver flere."""
        known = getattr(self, sn_attr)
        tries = [known] if known else [self.inverter_sn, self.dongle_sn, ""]
        for sn in dict.fromkeys(t for t in tries if t is not None):
            try:
                q = f"getdevdata.cgi?device={device}" + (f"&sn={sn}" if sn else "")
                data = self.get(q)
                if isinstance(data, dict) and len(data) > 1:
                    if not known:
                        setattr(self, sn_attr, sn)
                    return data
            except Exception:  # noqa: BLE001
                continue
        return {}

    def read(self) -> dict[str, dict]:
        if not self.base:
            self.connect()
        inverter = self.get(f"getdevdata.cgi?device=2&sn={self.inverter_sn}") if self.inverter_sn else {}
        meter = self._device_data(3, "meter_sn")
        battery = self._device_data(4, "battery_sn")
        return {"inverter": inverter or {}, "meter": meter, "battery": battery}


class SolplanetProvider(threading.Thread):
    def __init__(self, cfg: dict, store: Store, tracker: EnergyTracker) -> None:
        super().__init__(name="solplanet", daemon=True)
        self.cfg = cfg
        self.store = store
        self.tracker = tracker
        self.client = SolplanetClient(cfg)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval = max(int(self.cfg.get("poll_seconds") or 10), 3)
        backoff = interval
        while not self._stop.is_set():
            try:
                raw = self.client.read()
                self.store.set("solar", self.parse(raw))
                backoff = interval
            except Exception as err:  # noqa: BLE001
                LOG.warning("Solplanet: %s", err)
                self.client.base = None  # find forbindelsen igen næste gang
                cur = self.store.get("solar") or {}
                cur.update({"ok": False, "error": str(err), "source": "solplanet"})
                self.store.set("solar", cur)
                backoff = min(backoff * 2, 120)
            self._stop.wait(backoff)

    # ------------------------------------------------------------------ parsing
    def parse(self, raw: dict[str, dict]) -> dict:
        inv, meter, bat = raw["inverter"], raw["meter"], raw["battery"]
        cfg = self.cfg

        # --- PV
        pv_strings = None
        vpv, ipv = inv.get("vpv"), inv.get("ipv")
        if isinstance(vpv, list) and isinstance(ipv, list):
            pv_strings = sum((v or 0) * 0.1 * (i or 0) * 0.01 for v, i in zip(vpv, ipv))
        src = cfg.get("pv_source", "auto")
        ppv = _num(bat, "ppv")
        pac = _num(inv, "pac")
        if src == "battery":
            pv = ppv
        elif src == "inverter":
            pv = pac
        elif src == "strings":
            pv = pv_strings
        else:
            pv = ppv if ppv is not None else (pv_strings if (bat and pv_strings is not None) else pac)
        pv = max(pv or 0.0, 0.0)

        # --- Net (+ = køb)
        grid = _num(meter, "pac")
        if grid is not None and cfg.get("invert_grid"):
            grid = -grid

        # --- Batteri (+ = opladning)
        soc = _num(bat, "soc")
        battery_w = None
        bst = bat.get("bst") if bat else None
        state = BATTERY_STATUS.get(bst) if isinstance(bst, int) else None
        pb = _num(bat, "pb")
        if pb is not None:
            if state == "charging":
                battery_w = abs(pb)
            elif state == "discharging":
                battery_w = -abs(pb)
            else:
                battery_w = pb if cfg.get("battery_power_positive") == "charge" else -pb
        if state is None and battery_w is not None:
            state = "charging" if battery_w > 30 else "discharging" if battery_w < -30 else "idle"

        # --- Forbrug = PV + køb - salg - batteriopladning
        load = None
        if grid is not None:
            load = max(pv + grid - (battery_w or 0.0), 0.0)
        elif pac is not None:
            load = None  # uden måler kan forbruget ikke beregnes

        # --- Dagens tællere fra enheden (når de findes)
        today = {
            "import": _num(meter, "itd", 0.01),
            "export": _num(meter, "otd", 0.01),
        }
        if not bat and _num(inv, "etd") is not None:
            today["pv"] = _num(inv, "etd", 0.1)  # ren solcelle-inverter: etd = dagens produktion
        totals = {
            "import": _num(meter, "iet", 0.1),
            "export": _num(meter, "oet", 0.1),
        }
        if load is not None:
            self.tracker.update(
                {"pv": pv, "load": load, "grid": grid or 0.0, "battery": battery_w or 0.0},
                today_kwh=today,
                totals_kwh=totals,
            )

        cap = cfg.get("battery_capacity_kwh")
        eta_min = None
        if cap and soc is not None and battery_w:
            if battery_w > 50:
                eta_min = round((100 - soc) / 100 * cap / (battery_w / 1000) * 60)
            elif battery_w < -50:
                eta_min = round(soc / 100 * cap / (-battery_w / 1000) * 60)

        return {
            "ok": True,
            "source": "solplanet",
            "demo": False,
            "updated": iso(utcnow()),
            "model": self.client.model,
            "pv_w": round(pv),
            "load_w": round(load) if load is not None else None,
            "grid_w": round(grid) if grid is not None else None,
            "battery_w": round(battery_w) if battery_w is not None else None,
            "battery_soc": soc,
            "battery_soh": _num(bat, "soh"),
            "battery_state": state,
            "battery_temp": _num(bat, "tb", 0.1),
            "battery_voltage": _num(bat, "vb", 0.01),
            "battery_capacity_kwh": cap,
            "battery_eta_min": eta_min,
            "has_battery": bool(bat),
            "inverter_temp": _num(inv, "tmp", 0.1),
            "inverter_status": INVERTER_STATUS.get(inv.get("flg") if isinstance(inv.get("flg"), int) else -1),
            "inverter_pac_w": pac,
        }
