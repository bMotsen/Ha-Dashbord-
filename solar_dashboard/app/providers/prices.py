"""Timepris på strøm i Danmark: spotpris + nettarif + Energinet + elafgift + moms.

Kilder (gratis, ingen nøgle):
  * Energi Data Service (Energinet) - datasæt "DayAheadPrices" (spot, 15 min / time) og
    "DatahubPricelist" (netselskabernes tariffer, Energinets tariffer og elafgift).
  * elprisenligenu.dk - bruges som reserve til spotprisen.

Alle priser i kr/kWh. Spot og tariffer er ekskl. moms; "total" er inkl. moms.
"""
from __future__ import annotations

import json
import logging
import math
import threading
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..config import DATA_DIR
from ..store import Store, iso, load_json, save_json, utcnow

LOG = logging.getLogger(__name__)

EDS = "https://api.energidataservice.dk/dataset"
ELPRIS = "https://www.elprisenligenu.dk/api/v1/prices/{y}/{m:02d}-{d:02d}_{area}.json"

# Kendte netselskaber (GLN + ChargeTypeCode for nettarif C). Tjek dit eget med
#   python tools/find_tariff.py "<navn på netselskab>"
# og skriv evt. grid_gln + grid_codes direkte i config.yaml.
GRID_COMPANIES: dict[str, dict[str, Any]] = {
    "radius": {"name": "Radius Elnet", "gln": "5790000610099", "codes": ["DT_C_01"]},
    "cerius": {"name": "Cerius", "gln": "5790000705184", "codes": ["30TR_C_ET"]},
    "n1": {"name": "N1", "gln": "5790001089030", "codes": ["CD", "CD R"]},
    "trefor": {"name": "TREFOR El-net", "gln": "5790000392261", "codes": ["C"]},
    "konstant": {"name": "Konstant Net", "gln": "5790000704842", "codes": ["151-NT01T", "151-NRA04T"]},
}

# Standard tidsperioder i tarifmodellen (lavlast / højlast / spidslast)
def _period(hour: int) -> str:
    if hour < 6:
        return "low"
    if 17 <= hour < 21:
        return "peak"
    return "high"


def _season(d: date) -> str:
    return "summer" if 4 <= d.month <= 9 else "winter"


# Kun til demo-visning (typisk C-kunde nettarif, kr/kWh ekskl. moms)
DEMO_TARIFF = {"winter": {"low": 0.15, "high": 0.45, "peak": 1.35}, "summer": {"low": 0.15, "high": 0.23, "peak": 0.59}}


class PriceProvider(threading.Thread):
    def __init__(self, cfg: dict, store: Store, tz: ZoneInfo, demo_fallback: bool = True) -> None:
        super().__init__(name="prices", daemon=True)
        self.cfg = cfg
        self.store = store
        self.tz = tz
        self.demo_fallback = demo_fallback
        self.http = httpx.Client(timeout=20.0, headers={"User-Agent": "solar-dashboard/1.0"})
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.spot: dict[str, float] = {}           # "YYYY-MM-DDTHH" (lokal tid) -> kr/kWh
        self.tariff_cache = load_json(DATA_DIR / "tariffs.json", {})
        self.spot_cache_path = DATA_DIR / "spot.json"
        self.spot.update(load_json(self.spot_cache_path, {}))
        self.error: str | None = None
        self.tariff_note: str = ""
        self.demo = False
        self.updated: datetime | None = None
        self.spot_source = ""

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ loop
    def run(self) -> None:
        refresh_s = max(int(self.cfg.get("refresh_minutes") or 30), 5) * 60
        while not self._stop.is_set():
            wait = refresh_s
            try:
                self.refresh()
                now = datetime.now(self.tz)
                tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%dT00")
                if now.hour >= 13 and tomorrow not in self.spot:
                    wait = 600  # morgendagens priser kommer ca. kl. 13 - kig oftere efter dem
            except Exception as err:  # noqa: BLE001
                LOG.warning("Elpriser: %s", err)
                self.error = str(err)
                wait = 300
            self._stop.wait(wait)

    def refresh(self) -> None:
        now = datetime.now(self.tz)
        start = (now - timedelta(days=1)).date()
        end = (now + timedelta(days=2)).date()
        spot: dict[str, float] = {}
        errors = []
        sources = [self.cfg.get("source", "energidataservice")]
        sources += [s for s in ("energidataservice", "elprisenligenu") if s not in sources]
        for src in sources:
            try:
                spot = self._fetch_eds(start, end) if src == "energidataservice" else self._fetch_elpris(start, end)
                if spot:
                    self.spot_source = src
                    break
            except Exception as err:  # noqa: BLE001
                errors.append(f"{src}: {err}")
        if not spot:
            raise RuntimeError("Ingen spotpriser: " + "; ".join(errors))
        try:
            self._refresh_tariffs()
        except Exception as err:  # noqa: BLE001
            LOG.warning("Tariffer: %s (bruger cache/reserve)", err)
        with self._lock:
            keep_from = (now - timedelta(days=2)).strftime("%Y-%m-%dT00")
            self.spot = {k: v for k, v in {**self.spot, **spot}.items() if k >= keep_from}
            self.error = None
            self.demo = False
            self.updated = utcnow()
        save_json(self.spot_cache_path, self.spot)
        LOG.info("Elpriser opdateret fra %s (%d timer)", self.spot_source, len(spot))

    # ------------------------------------------------------------------ spot
    def _group_hourly(self, rows: list[tuple[datetime, float]]) -> dict[str, float]:
        buckets: dict[str, list[float]] = {}
        for t, p in rows:
            buckets.setdefault(t.astimezone(self.tz).strftime("%Y-%m-%dT%H"), []).append(p)
        return {k: mean(v) for k, v in buckets.items()}

    def _fetch_eds(self, start: date, end: date) -> dict[str, float]:
        area = self.cfg.get("area", "DK1")
        eur = float(self.cfg.get("eur_dkk") or 7.46)
        for dataset in ("DayAheadPrices", "Elspotprices"):
            params = {
                "start": f"{start.isoformat()}T00:00",
                "end": f"{end.isoformat()}T00:00",
                "filter": json.dumps({"PriceArea": [area]}),
                "limit": "2000",
            }
            r = self.http.get(f"{EDS}/{dataset}", params=params)
            if r.status_code >= 400:
                continue
            records = r.json().get("records") or []
            rows: list[tuple[datetime, float]] = []
            for rec in records:
                t_local = rec.get("TimeDK") or rec.get("HourDK")
                t_utc = rec.get("TimeUTC") or rec.get("HourUTC")
                if t_local:
                    t = datetime.fromisoformat(t_local).replace(tzinfo=self.tz)
                elif t_utc:
                    t = datetime.fromisoformat(t_utc).replace(tzinfo=ZoneInfo("UTC"))
                else:
                    continue
                dkk = rec.get("DayAheadPriceDKK", rec.get("SpotPriceDKK"))
                if dkk is None:
                    e = rec.get("DayAheadPriceEUR", rec.get("SpotPriceEUR"))
                    if e is None:
                        continue
                    dkk = float(e) * eur
                rows.append((t, float(dkk) / 1000.0))  # kr/MWh -> kr/kWh
            if rows:
                return self._group_hourly(rows)
        return {}

    def _fetch_elpris(self, start: date, end: date) -> dict[str, float]:
        area = self.cfg.get("area", "DK1")
        rows: list[tuple[datetime, float]] = []
        d = start
        while d <= end:
            r = self.http.get(ELPRIS.format(y=d.year, m=d.month, d=d.day, area=area))
            if r.status_code == 200:
                for rec in r.json():
                    rows.append((datetime.fromisoformat(rec["time_start"]), float(rec["DKK_per_kWh"])))
            d += timedelta(days=1)
        return self._group_hourly(rows)

    # ------------------------------------------------------------------ tariffs
    def _grid_def(self) -> tuple[str, list[str], str]:
        gln = self.cfg.get("grid_gln") or ""
        codes = list(self.cfg.get("grid_codes") or [])
        name = "netselskab"
        preset = GRID_COMPANIES.get((self.cfg.get("grid_company") or "").lower().replace(" ", ""))
        if preset:
            gln = gln or preset["gln"]
            codes = codes or preset["codes"]
            name = preset["name"]
        return gln, codes, name

    def _fetch_pricelist(self, gln: str, codes: list[str], chargetype: str | None) -> list[dict]:
        flt: dict[str, list[str]] = {"GLN_Number": [gln], "ChargeTypeCode": codes}
        if chargetype:
            flt["ChargeType"] = [chargetype]
        params = {"filter": json.dumps(flt), "sort": "ValidFrom DESC", "limit": "200"}
        r = self.http.get(f"{EDS}/DatahubPricelist", params=params)
        r.raise_for_status()
        return r.json().get("records") or []

    def _refresh_tariffs(self) -> None:
        cache = dict(self.tariff_cache)
        en = self.cfg.get("energinet") or {}
        groups = {
            "energinet": (en.get("gln"), en.get("codes") or [], None),
            "elafgift": (en.get("gln"), en.get("tax_codes") or [], None),
        }
        gln, codes, _ = self._grid_def()
        if gln and codes and not self.cfg.get("manual_tariff"):
            groups["nettarif"] = (gln, codes, "D03")
        for key, (g, c, ct) in groups.items():
            if not g or not c:
                continue
            recs = self._fetch_pricelist(g, c, ct)
            if recs:
                cache[key] = recs
            else:
                LOG.warning("Ingen tarif-poster fundet for %s (GLN %s, koder %s)", key, g, c)
        self.tariff_cache = cache
        save_json(DATA_DIR / "tariffs.json", cache)

    @staticmethod
    def _record_price(records: list[dict], t: datetime) -> float | None:
        """Summen af alle gyldige koder på tidspunktet t (lokal tid)."""
        naive = t.replace(tzinfo=None)
        best: dict[str, dict] = {}
        for rec in records:
            try:
                vf = datetime.fromisoformat(rec["ValidFrom"])
                vt = datetime.fromisoformat(rec["ValidTo"]) if rec.get("ValidTo") else None
            except Exception:  # noqa: BLE001
                continue
            if vf <= naive and (vt is None or naive < vt):
                code = rec.get("ChargeTypeCode", "")
                if code not in best or vf > datetime.fromisoformat(best[code]["ValidFrom"]):
                    best[code] = rec
        if not best:
            return None
        total = 0.0
        for rec in best.values():
            p = rec.get(f"Price{t.hour + 1}")
            if p is None:
                p = rec.get("Price1")
            total += float(p or 0.0)
        return total

    def _tariffs_at(self, t: datetime, demo: bool = False) -> dict[str, float | None]:
        fb = self.cfg.get("fallback") or {}
        energinet = self._record_price(self.tariff_cache.get("energinet", []), t)
        elafgift = self._record_price(self.tariff_cache.get("elafgift", []), t)
        manual = self.cfg.get("manual_tariff") or (DEMO_TARIFF if demo and not self.tariff_cache.get("nettarif") else None)
        if manual:
            season = manual.get(_season(t.date())) or {}
            net = season.get(_period(t.hour))
        else:
            net = self._record_price(self.tariff_cache.get("nettarif", []), t)
        return {
            "nettarif": net,
            "energinet": energinet if energinet is not None else fb.get("energinet"),
            "elafgift": elafgift if elafgift is not None else fb.get("elafgift"),
        }

    # ------------------------------------------------------------------ demo
    def _demo_spot(self) -> dict[str, float]:
        now = datetime.now(self.tz)
        out = {}
        for day in (0, 1):
            d0 = (now + timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
            for h in range(24):
                base = 0.55 + 0.35 * math.exp(-((h - 8) ** 2) / 6) + 0.6 * math.exp(-((h - 18) ** 2) / 5)
                base -= 0.25 * math.exp(-((h - 13) ** 2) / 8)  # sol midt på dagen
                base -= 0.18 * math.exp(-((h - 3) ** 2) / 4)
                out[(d0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H")] = round(base + 0.04 * day, 3)
        return out

    # ------------------------------------------------------------------ read
    def _hour_row(self, key: str, spot: float, demo: bool = False) -> dict:
        t = datetime.strptime(key, "%Y-%m-%dT%H").replace(tzinfo=self.tz)
        tar = self._tariffs_at(t, demo)
        supplier = float(self.cfg.get("supplier_markup") or 0.0)
        vat_rate = float(self.cfg.get("vat") or 0.0)
        parts = [spot, tar["nettarif"] or 0.0, tar["energinet"] or 0.0, tar["elafgift"] or 0.0, supplier]
        ex_vat = sum(parts)
        vat = ex_vat * vat_rate
        return {
            "start": t.isoformat(),
            "hour": t.hour,
            "date": t.date().isoformat(),
            "spot": round(spot, 4),
            "nettarif": None if tar["nettarif"] is None else round(tar["nettarif"], 4),
            "energinet": None if tar["energinet"] is None else round(tar["energinet"], 4),
            "elafgift": None if tar["elafgift"] is None else round(tar["elafgift"], 4),
            "supplier": round(supplier, 4),
            "vat": round(vat, 4),
            "total": round(ex_vat + vat, 4),
            "sell": round(spot - float(self.cfg.get("sell_fee") or 0.0), 4),
        }

    def price_at(self, t: datetime) -> tuple[float, float] | None:
        key = t.astimezone(self.tz).strftime("%Y-%m-%dT%H")
        with self._lock:
            spot = self.spot.get(key)
        demo = False
        if spot is None and self.demo_fallback:
            spot, demo = self._demo_spot().get(key), True
        if spot is None:
            return None
        row = self._hour_row(key, spot, demo)
        return row["total"], row["sell"]

    def snapshot(self) -> dict:
        now = datetime.now(self.tz)
        today = now.strftime("%Y-%m-%dT00")
        with self._lock:
            spot = dict(self.spot)
            demo = self.demo
        if not any(k >= today for k in spot) and self.demo_fallback:
            spot = self._demo_spot()
            demo = True
        rows = [self._hour_row(k, v, demo) for k, v in sorted(spot.items()) if k >= today]
        if not rows:
            return {"ok": False, "error": self.error or "Ingen priser endnu", "demo": False}

        # prisniveau pr. dag (billig / normal / dyr)
        by_day: dict[str, list[float]] = {}
        for r in rows:
            by_day.setdefault(r["date"], []).append(r["total"])
        for r in rows:
            vals = sorted(by_day[r["date"]])
            lo = vals[int(len(vals) * 0.33)]
            hi = vals[min(int(len(vals) * 0.67), len(vals) - 1)]
            r["level"] = "low" if r["total"] <= lo else "high" if r["total"] >= hi else "mid"

        cur_key = now.strftime("%Y-%m-%dT%H")
        current = next((r for r in rows if datetime.fromisoformat(r["start"]).strftime("%Y-%m-%dT%H") == cur_key), None)

        # billigste sammenhængende vindue fra nu af (til fx opladning af bilen)
        n = max(int(self.cfg.get("cheap_window_hours") or 3), 1)
        future = [r for r in rows if datetime.fromisoformat(r["start"]) >= now.replace(minute=0, second=0, microsecond=0)]
        cheapest = None
        for i in range(0, max(len(future) - n + 1, 0)):
            win = future[i:i + n]
            avg = sum(r["total"] for r in win) / n
            if cheapest is None or avg < cheapest["avg"]:
                cheapest = {"start": win[0]["start"], "end": (datetime.fromisoformat(win[-1]["start"]) + timedelta(hours=1)).isoformat(),
                            "avg": round(avg, 4), "hours": n}

        today_vals = [r["total"] for r in rows if r["date"] == now.date().isoformat()]
        _, _, grid_name = self._grid_def()
        has_net = any(r["nettarif"] is not None for r in rows)
        return {
            "ok": True,
            "demo": demo,
            "error": self.error,
            "area": self.cfg.get("area", "DK1"),
            "source": "demo" if demo else self.spot_source,
            "updated": iso(self.updated),
            "now": current,
            "hours": rows,
            "cheapest": cheapest,
            "today": {"min": min(today_vals), "max": max(today_vals), "avg": round(mean(today_vals), 4)} if today_vals else None,
            "has_tomorrow": any(r["date"] > now.date().isoformat() for r in rows),
            "grid_company": ("demo" if demo and not self.cfg.get("manual_tariff") else
                             "manuel" if self.cfg.get("manual_tariff") else (grid_name if has_net else None)),
            "vat_rate": self.cfg.get("vat"),
        }
