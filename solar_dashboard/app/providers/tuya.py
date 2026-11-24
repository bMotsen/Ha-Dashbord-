"""Tuya / Smart Life enheder (stikkontakter, lys, sensorer ... og elbil-laderen).

* Enhedslisten hentes automatisk fra Tuya-skyen -> nye enheder i appen dukker selv op.
* Når en enheds IP og "local key" kendes, aflæses og styres den direkte på LAN (hurtigt, intet API-forbrug).
  Ellers bruges Tuya-skyen.
* Elbil-laderen findes automatisk (Tuya-kategori "qccdz") eller via tuya.ev_charger_id.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import DATA_DIR, resolve_path
from ..store import Store, iso, load_json, save_json, utcnow

LOG = logging.getLogger(__name__)

CATEGORY_ICON = {
    "dj": "lightbulb", "dd": "lightbulb", "fwd": "lightbulb", "dc": "lightbulb", "tgq": "lightbulb",
    "tgkg": "lightbulb", "xdd": "lamp-ceiling", "gyd": "lightbulb", "tyndj": "sun",
    "cz": "plug", "pc": "plug", "kg": "toggle-right", "tdq": "toggle-right", "dlq": "zap", "zndb": "zap",
    "qn": "heater", "rs": "flame", "wk": "thermometer", "wkf": "thermometer", "kt": "snowflake", "znrb": "heater",
    "fs": "fan", "kj": "wind", "cs": "droplets", "jsq": "droplets",
    "wsdcg": "thermometer", "co2bj": "wind", "mcs": "door-open", "pir": "activity", "ywbj": "siren",
    "rqbj": "siren", "sj": "droplets", "sos": "siren",
    "cl": "blinds", "clkg": "blinds", "ckmkzq": "door-open", "ms": "lock", "sp": "cctv",
    "qccdz": "ev-charger", "bh": "coffee", "xxj": "sparkles", "sd": "sparkles", "wnykq": "radio",
}
SWITCH_CODES = ("switch_led", "switch", "switch_1", "switch_on", "power", "led_switch", "switch_charge")
POWER_CODES = ("cur_power", "power", "phase_power", "add_ele_power")
TEMP_CODES = ("temp_current", "va_temperature", "temp_indoor", "temp_value", "temperature")
HUM_CODES = ("humidity_value", "va_humidity", "humidity_indoor", "humidity")
BRIGHT_CODES = ("bright_value_v2", "bright_value", "bright_value_1")

CHARGER_STATE = {
    "charger_charging": "charging", "charging": "charging", "charge": "charging",
    "charger_free": "idle", "free": "idle", "idle": "idle", "standby": "idle",
    "charger_insert": "connected", "insert": "connected", "connected": "connected", "plugged": "connected",
    "charger_wait": "waiting", "wait": "waiting", "waiting": "waiting", "charger_appointment": "waiting",
    "charger_pause": "paused", "pause": "paused",
    "charger_end": "finished", "end": "finished", "charge_end": "finished", "finish": "finished",
    "charger_fault": "fault", "charger_free_fault": "fault", "fault": "fault", "error": "fault",
}
CHARGER_STATE_CODES = ("work_state", "charge_state", "charging_state", "status", "work_status", "state")
CHARGER_POWER_CODES = ("power_total", "charge_power", "cur_power", "power", "total_power", "power_now")
CHARGER_ENERGY_CODES = ("charge_energy_once", "energy_charge", "charge_energy", "once_energy", "session_energy")
CHARGER_CURRENT_CODES = ("charge_cur_set", "charge_current", "set_current", "current_set")


class TuyaDevice:
    def __init__(self, info: dict) -> None:
        self.id: str = info["id"]
        self.info = info
        self.status: dict[str, Any] = {}        # code -> raw værdi
        self.online: bool | None = None
        self.via: str = "cloud"
        self.local_fail = 0
        self.last_seen: float = 0
        self._dev = None
        self._dev_key: tuple | None = None
        self.by_code: dict[str, tuple[str, dict]] = {}
        self.set_mapping(info.get("mapping") or {})

    def set_mapping(self, mapping: dict) -> None:
        self.by_code = {}
        for dp, m in (mapping or {}).items():
            if isinstance(m, dict) and m.get("code"):
                vals = m.get("values") if isinstance(m.get("values"), dict) else {}
                self.by_code[m["code"]] = (str(dp), vals)

    @property
    def name(self) -> str:
        return self.info.get("name") or self.id

    @property
    def category(self) -> str:
        return self.info.get("category") or ""

    def can_local(self) -> bool:
        return bool(self.info.get("ip") and self.info.get("key"))

    def local(self):
        import tinytuya

        key = (self.info.get("ip"), self.info.get("key"), self.info.get("version"))
        if self._dev is None or self._dev_key != key:
            ver = float(self.info.get("version") or 3.3)
            d = tinytuya.Device(self.id, address=self.info["ip"], local_key=self.info["key"], version=ver)
            d.set_socketTimeout(3)
            d.set_socketRetryLimit(1)
            d.set_socketPersistent(False)
            self._dev, self._dev_key = d, key
        return self._dev

    def dps_to_codes(self, dps: dict) -> dict[str, Any]:
        rev = {dp: code for code, (dp, _) in self.by_code.items()}
        return {rev.get(str(k), str(k)): v for k, v in dps.items()}

    def scaled(self, code: str) -> float | None:
        v = self.status.get(code)
        if v is None or isinstance(v, bool):
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        _, vals = self.by_code.get(code, ("", {}))
        scale = vals.get("scale") if isinstance(vals, dict) else None
        if isinstance(scale, int) and scale > 0:
            v = v / (10 ** scale)
        return v

    def unit(self, code: str) -> str:
        _, vals = self.by_code.get(code, ("", {}))
        return str((vals or {}).get("unit") or "")

    def first(self, codes) -> str | None:
        return next((c for c in codes if c in self.status), None)


CAMERA_CATEGORIES = {"sp", "dghsxj", "sgbj"}


class TuyaProvider(threading.Thread):
    def __init__(self, cfg: dict, store: Store) -> None:
        super().__init__(name="tuya", daemon=True)
        self.cfg = cfg
        self.store = store
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.devices: dict[str, TuyaDevice] = {}
        self.cloud = None
        self.pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="tuya-local")
        self.scan_ips: dict[str, dict] = load_json(DATA_DIR / "tuya_scan.json", {})
        self.error: str | None = None
        self._last_list = 0.0
        self._last_cloud = 0.0
        self._last_scan = 0.0

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ device list
    def _cloud(self):
        if self.cloud is None and self.cfg.get("api_key") and self.cfg.get("api_secret"):
            import tinytuya

            first = self.cfg.get("region", "eu")
            regions = [first] + [r for r in ("eu", "eu-w", "us", "us-e", "in", "cn") if r != first]
            err = None
            for region in regions:
                cloud = tinytuya.Cloud(
                    apiRegion=region,
                    apiKey=str(self.cfg["api_key"]).strip(),
                    apiSecret=str(self.cfg["api_secret"]).strip(),
                    apiDeviceID=(str(self.cfg.get("api_device_id") or "").strip() or None),
                    configFile=str(DATA_DIR / "tinytuya.json"),
                )
                err = getattr(cloud, "error", None)
                if not err:
                    if region != first:
                        LOG.info("Tuya: dit projekt ligger i datacenter '%s'", region)
                    self.cloud = cloud
                    break
                if "911" not in str(err) and "clientId" not in str(err) and "sign" not in str(err).lower():
                    break  # anden fejl end forkert datacenter/nøgle - ingen grund til at prøve flere
            if self.cloud is None:
                msg = "Tuya: Access ID/Secret blev afvist i alle datacentre – kopiér dem igen fra iot.tuya.com"
                raise RuntimeError(f"{msg} ({err})")
        return self.cloud

    def _load_device_list(self) -> None:
        devs: dict[str, dict] = {}
        # 1) devices.json fra `tinytuya wizard` (har local keys og ofte IP)
        f = resolve_path(self.cfg.get("devices_file") or "devices.json")
        for d in load_json(f, []) or []:
            if isinstance(d, dict) and d.get("id"):
                devs[d["id"]] = dict(d)
        # 2) Tuya-skyen (nye enheder kommer automatisk med)
        cache_path = DATA_DIR / "tuya_devices.json"
        cloud_list = None
        try:
            cloud = self._cloud()
            if cloud is not None:
                old = load_json(cache_path, [])
                cloud_list = cloud.getdevices(verbose=False, oldlist=old, include_map=True)
                if isinstance(cloud_list, list):
                    save_json(cache_path, cloud_list)
                else:
                    raise RuntimeError(str(cloud_list))
        except Exception as err:  # noqa: BLE001
            LOG.warning("Tuya: kunne ikke hente enhedsliste fra skyen: %s", err)
            self.error = str(err)
            cloud_list = load_json(cache_path, [])
        for d in cloud_list or []:
            if isinstance(d, dict) and d.get("id"):
                merged = devs.get(d["id"], {})
                merged.update({k: v for k, v in d.items() if v not in (None, "")})
                devs[d["id"]] = merged
        # 3) IP-adresser fra snapshot.json / egen netværksscanning / config
        snap = load_json(resolve_path(self.cfg.get("snapshot_file") or "snapshot.json"), {})
        for d in (snap.get("devices") if isinstance(snap, dict) else None) or []:
            if d.get("id") in devs and d.get("ip"):
                devs[d["id"]].setdefault("ip", d["ip"])
                if d.get("ver"):
                    devs[d["id"]].setdefault("version", d["ver"])
        for dev_id, s in self.scan_ips.items():
            if dev_id in devs and s.get("ip"):
                devs[dev_id]["ip"] = s["ip"]
                if s.get("version"):
                    devs[dev_id]["version"] = s["version"]
        for dev_id, ip in (self.cfg.get("ips") or {}).items():
            if dev_id in devs:
                devs[dev_id]["ip"] = ip

        with self._lock:
            for dev_id, info in devs.items():
                if dev_id in self.devices:
                    self.devices[dev_id].info.update(info)
                    self.devices[dev_id].set_mapping(info.get("mapping") or {})
                else:
                    self.devices[dev_id] = TuyaDevice(info)
            for dev_id in list(self.devices):
                if dev_id not in devs:
                    del self.devices[dev_id]
        if not devs and self.cloud is None:
            self.error = "Ingen Tuya-enheder: udfyld tuya.api_key og api_secret i config.yaml"
        LOG.info("Tuya: %d enheder (%d med lokal adgang)", len(devs), sum(1 for d in self.devices.values() if d.can_local()))

    def _scan(self) -> None:
        """Find Tuya-enheders IP på det lokale netværk (UDP broadcast, ca. 20 sek)."""
        try:
            import tinytuya

            found = tinytuya.deviceScan(False, 20, False, False, False, True) or {}
            ips = {}
            for dev_id, d in found.items():
                if isinstance(d, dict) and d.get("ip"):
                    ips[d.get("gwId") or dev_id] = {"ip": d["ip"], "version": d.get("version")}
            if ips:
                self.scan_ips.update(ips)
                save_json(DATA_DIR / "tuya_scan.json", self.scan_ips)
                with self._lock:
                    for dev_id, s in ips.items():
                        if dev_id in self.devices:
                            self.devices[dev_id].info["ip"] = s["ip"]
                            if s.get("version"):
                                self.devices[dev_id].info["version"] = s["version"]
                            self.devices[dev_id].local_fail = 0
                LOG.info("Tuya: netværksscanning fandt %d enheder", len(ips))
        except Exception as err:  # noqa: BLE001
            LOG.warning("Tuya: netværksscanning fejlede: %s", err)

    # ------------------------------------------------------------------ polling
    def _poll_local(self, dev: TuyaDevice) -> None:
        try:
            res = dev.local().status()
            if not isinstance(res, dict) or "dps" not in res:
                raise RuntimeError(res.get("Error") if isinstance(res, dict) else res)
            dev.status.update(dev.dps_to_codes(res["dps"]))
            dev.online, dev.via, dev.local_fail, dev.last_seen = True, "local", 0, time.time()
        except Exception as err:  # noqa: BLE001
            dev.local_fail += 1
            if dev.local_fail >= 3:
                dev.online = False if self.cloud is None else dev.online
            LOG.debug("Tuya lokal %s: %s", dev.name, err)

    def _poll_cloud(self, devs: list[TuyaDevice]) -> None:
        cloud = self._cloud()
        if cloud is None or not devs:
            return
        for i in range(0, len(devs), 20):
            chunk = devs[i:i + 20]
            ids = ",".join(d.id for d in chunk)
            res = cloud.cloudrequest("/v1.0/iot-03/devices/status", query={"device_ids": ids})
            if isinstance(res, dict) and res.get("success") and isinstance(res.get("result"), list):
                by_id = {r.get("id"): r for r in res["result"]}
                for d in chunk:
                    r = by_id.get(d.id)
                    if r:
                        d.status.update({s["code"]: s.get("value") for s in r.get("status", []) if "code" in s})
                        d.via, d.last_seen = "cloud", time.time()
            else:  # reserve: én ad gangen
                for d in chunk:
                    r = cloud.getstatus(d.id)
                    if isinstance(r, dict) and r.get("success"):
                        d.status.update({s["code"]: s.get("value") for s in r.get("result", []) if "code" in s})
                        d.via, d.last_seen = "cloud", time.time()
            # online-status
            try:
                res = cloud.cloudrequest("/v2.0/cloud/thing/batch", query={"device_ids": ids})
                for r in (res or {}).get("result", []) or []:
                    dev = self.devices.get(r.get("id"))
                    if dev and "is_online" in r:
                        dev.online = bool(r["is_online"])
            except Exception:  # noqa: BLE001
                pass

    def run(self) -> None:
        try:
            self._load_device_list()
        except Exception as err:  # noqa: BLE001
            LOG.warning("Tuya: %s", err)
            self.error = str(err)
        self._last_list = time.time()
        if self.cfg.get("scan_network", True) and self.cfg.get("use_local", True):
            threading.Thread(target=self._scan, daemon=True).start()
            self._last_scan = time.time()

        local_s = max(int(self.cfg.get("poll_local_seconds") or 10), 3)
        cloud_s = max(int(self.cfg.get("poll_cloud_seconds") or 60), 15)
        list_s = max(int(self.cfg.get("refresh_devices_minutes") or 360), 10) * 60
        while not self._stop.is_set():
            now = time.time()
            try:
                if now - self._last_list > list_s:
                    self._last_list = now
                    self._load_device_list()
                if self.cfg.get("scan_network", True) and self.cfg.get("use_local", True) and now - self._last_scan > 1800:
                    self._last_scan = now
                    threading.Thread(target=self._scan, daemon=True).start()
                with self._lock:
                    devs = list(self.devices.values())
                use_local = self.cfg.get("use_local", True)
                local = [d for d in devs if use_local and d.can_local() and d.local_fail < 3]
                cloud = [d for d in devs if d not in local]
                list(self.pool.map(self._poll_local, local))
                if cloud and now - self._last_cloud > cloud_s:
                    self._last_cloud = now
                    self._poll_cloud(cloud)
                    for d in cloud:  # prøv LAN igen en gang imellem
                        if d.local_fail >= 3:
                            d.local_fail = 1
                if devs:
                    self.error = None
            except Exception as err:  # noqa: BLE001
                LOG.warning("Tuya: %s", err)
                self.error = str(err)
            self.publish()
            self._stop.wait(local_s)

    # ------------------------------------------------------------------ output
    def _hidden(self, dev: TuyaDevice) -> bool:
        hide = {str(h).lower() for h in self.cfg.get("hide") or []}
        shown = ((self.cfg.get("rename") or {}).get(dev.id) or dev.name).lower()
        return dev.id.lower() in hide or dev.name.lower() in hide or shown in hide

    def _charger(self) -> TuyaDevice | None:
        cid = self.cfg.get("ev_charger_id")
        if cid and cid in self.devices:
            return self.devices[cid]
        return next((d for d in self.devices.values() if d.category == "qccdz"), None)

    def device_view(self, dev: TuyaDevice) -> dict:
        sw = dev.first(SWITCH_CODES)
        name = (self.cfg.get("rename") or {}).get(dev.id) or dev.name
        out: dict[str, Any] = {
            "id": dev.id,
            "name": name,
            "category": dev.category,
            "product": dev.info.get("product_name"),
            "icon": CATEGORY_ICON.get(dev.category, "power"),
            "online": dev.online,
            "via": dev.via,
            "switch_code": sw,
            "on": bool(dev.status.get(sw)) if sw else None,
        }
        pc = dev.first(POWER_CODES)
        if pc:
            out["power_w"] = dev.scaled(pc)
        tc = dev.first(TEMP_CODES)
        if tc:
            out["temp"] = dev.scaled(tc)
        hc = dev.first(HUM_CODES)
        if hc:
            out["humidity"] = dev.scaled(hc)
        bc = dev.first(BRIGHT_CODES)
        if bc and dev.scaled(bc) is not None:
            _, vals = dev.by_code.get(bc, ("", {}))
            mx = float((vals or {}).get("max") or (1000 if bc.endswith("v2") else 255))
            out["brightness"] = round(dev.scaled(bc) / mx * 100) if mx else None
        if "doorcontact_state" in dev.status:
            out["open"] = bool(dev.status["doorcontact_state"])
        if "battery_percentage" in dev.status:
            out["battery"] = dev.scaled("battery_percentage")
        return out

    def charger_view(self, dev: TuyaDevice) -> dict:
        st_code = dev.first(CHARGER_STATE_CODES)
        raw_state = str(dev.status.get(st_code)) if st_code else None
        state = CHARGER_STATE.get((raw_state or "").lower(), raw_state)
        power_kw = None
        pc = dev.first(CHARGER_POWER_CODES)
        if pc:
            v = dev.scaled(pc)
            unit = dev.unit(pc).lower()
            if v is not None:
                power_kw = v if unit == "kw" else v / 1000 if unit == "w" or v > 100 else v
        ec = dev.first(CHARGER_ENERGY_CODES)
        cc = dev.first(CHARGER_CURRENT_CODES)
        sw = dev.first(SWITCH_CODES)
        if state is None and power_kw is not None:
            state = "charging" if power_kw > 0.3 else "idle"
        return {
            "ok": True,
            "demo": False,
            "id": dev.id,
            "name": (self.cfg.get("rename") or {}).get(dev.id) or dev.name,
            "online": dev.online,
            "via": dev.via,
            "state": state,
            "raw_state": raw_state,
            "charging": state == "charging",
            "power_kw": round(power_kw, 2) if power_kw is not None else None,
            "session_kwh": dev.scaled(ec) if ec else None,
            "current_a": dev.scaled(cc) if cc else None,
            "switch_code": sw,
            "on": bool(dev.status.get(sw)) if sw else None,
            "confirm": bool(self.cfg.get("confirm_charger_toggle", True)),
            "updated": iso(utcnow()),
        }

    def publish(self) -> None:
        with self._lock:
            devs = list(self.devices.values())
        charger = self._charger()
        order = [str(o).lower() for o in self.cfg.get("order") or []]

        rename = self.cfg.get("rename") or {}

        def sort_key(d: TuyaDevice):
            shown = (rename.get(d.id) or d.name).lower()
            for i, o in enumerate(order):
                if o in (d.id.lower(), d.name.lower(), shown):
                    return (0, i, "")
            return (1, 0, shown)

        views = []
        for d in sorted(devs, key=sort_key):
            if d.category in CAMERA_CATEGORIES:
                continue
            if self._hidden(d):
                continue
            if d is charger and not self.cfg.get("show_charger_in_devices"):
                continue
            views.append(self.device_view(d))
        self.store.set("devices", {"ok": self.error is None, "error": self.error, "demo": False, "items": views,
                                   "updated": iso(utcnow())})
        if charger is not None:
            self.store.set("charger", self.charger_view(charger))
        self.store.set("cameras", {"demo": False, "items": self.camera_list()})

    # ------------------------------------------------------------------ kameraer
    def camera_list(self) -> list[dict]:
        rename = self.cfg.get("rename") or {}
        out = []
        for d in self.devices.values():
            if d.category in CAMERA_CATEGORIES and not self._hidden(d):
                out.append({"id": d.id, "name": rename.get(d.id) or d.name, "online": d.online})
        for name in (self.cfg.get("rtsp") or {}):
            if not any(c["name"] == name or c["id"] == name for c in out):
                out.append({"id": name, "name": name, "online": True})
        return sorted(out, key=lambda c: c["name"].lower())

    def stream_url(self, cam_id: str) -> str:
        """Adresse til livestream: egen RTSP-adresse fra config, ellers fra Tuya-skyen."""
        rtsp = self.cfg.get("rtsp") or {}
        dev = self.devices.get(cam_id)
        for key in (cam_id, dev.name if dev else None, (self.cfg.get("rename") or {}).get(cam_id)):
            if key and key in rtsp:
                return rtsp[key]
        if dev is None:
            raise KeyError(cam_id)
        cloud = self._cloud()
        if cloud is None:
            raise RuntimeError("Ingen forbindelse til Tuya")
        last = None
        for kind in ("HLS", "RTSP"):
            res = cloud.cloudrequest(f"/v1.0/devices/{cam_id}/stream/actions/allocate", action="POST", post={"type": kind})
            if isinstance(res, dict) and res.get("success") and (res.get("result") or {}).get("url"):
                return res["result"]["url"]
            last = res
        msg = (last or {}).get("msg") if isinstance(last, dict) else str(last)
        raise RuntimeError(f"Tuya gav ingen videoadresse: {msg}. Tjek at 'IoT Video Live Stream' er tilføjet under Service API i dit Tuya-projekt")

    # ------------------------------------------------------------------ control
    def toggle(self, dev_id: str, value: bool | None = None) -> dict:
        with self._lock:
            dev = self.devices.get(dev_id)
        if dev is None:
            raise KeyError(dev_id)
        code = dev.first(SWITCH_CODES)
        if not code:
            raise ValueError("Enheden kan ikke tændes/slukkes")
        new = (not bool(dev.status.get(code))) if value is None else bool(value)
        done = False
        if self.cfg.get("use_local", True) and dev.can_local() and code in dev.by_code:
            try:
                dp = dev.by_code[code][0]
                res = dev.local().set_value(int(dp) if dp.isdigit() else dp, new)
                if isinstance(res, dict) and "Error" in res:
                    raise RuntimeError(res["Error"])
                done = True
            except Exception as err:  # noqa: BLE001
                LOG.info("Tuya lokal styring fejlede for %s (%s) - prøver skyen", dev.name, err)
        if not done:
            cloud = self._cloud()
            if cloud is None:
                raise RuntimeError("Ingen forbindelse til enheden")
            res = cloud.sendcommand(dev.id, {"commands": [{"code": code, "value": new}]})
            if not (isinstance(res, dict) and res.get("success")):
                raise RuntimeError(f"Tuya afviste kommandoen: {res}")
        dev.status[code] = new
        self.publish()
        return {"id": dev.id, "on": new}
