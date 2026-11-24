"""Webserver: leverer dashboardet og et JSON-API med al data."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import WEB_DIR, load_config
from .energy import EnergyTracker
from .providers.demo import DemoProvider
from .providers.prices import PriceProvider
from .providers.weather import WeatherProvider, demo_weather
from .store import Store, iso

LOG = logging.getLogger("dashboard")

cfg = load_config()
tz = ZoneInfo(cfg["timezone"])
store = Store()
force_demo = bool(cfg.get("demo"))
demo_ok = force_demo or bool(cfg.get("demo_when_disabled", True))

prices = PriceProvider(cfg["prices"], store, tz, demo_fallback=demo_ok)
solar_live = not force_demo and bool(cfg["solplanet"].get("enabled") and cfg["solplanet"].get("host"))
tracker = EnergyTracker(tz, price_lookup=prices.price_at, source="solplanet" if solar_live else "demo")

threads: list = []
solplanet = vw = tuya = None
demo_parts: set[str] = set()

if solar_live:
    from .providers.solplanet import SolplanetProvider

    solplanet = SolplanetProvider(cfg["solplanet"], store, tracker)
    threads.append(solplanet)
elif demo_ok:
    demo_parts.add("solar")

if not force_demo and cfg["vw"].get("enabled") and cfg["vw"].get("username"):
    from .providers.vw import VWProvider

    vw = VWProvider(cfg["vw"], store)
    threads.append(vw)
elif demo_ok:
    demo_parts.add("car")

if not force_demo and cfg["tuya"].get("enabled"):
    from .providers.tuya import TuyaProvider

    tuya = TuyaProvider(cfg["tuya"], store)
    threads.append(tuya)
elif demo_ok:
    demo_parts.update({"devices", "charger"})

if not force_demo and cfg["prices"].get("enabled", True):
    threads.append(prices)

wcfg = cfg["weather"]
weather_live = (not force_demo and wcfg.get("enabled", True)
                and wcfg.get("latitude") not in (None, "") and wcfg.get("longitude") not in (None, ""))
if weather_live:
    threads.append(WeatherProvider(wcfg, store, tz))
elif demo_ok:
    demo_parts.add("weather")

demo = DemoProvider(store, tracker, tz, demo_parts) if demo_parts else None
if demo:
    threads.append(demo)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for t in threads:
        t.start()
    LOG.info("Startet: %s", ", ".join(t.name for t in threads) or "intet")
    yield
    for t in threads:
        stop = getattr(t, "stop", None)
        if stop:
            stop()
    tracker.save()


app = FastAPI(title="Solar Dashboard", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)


@app.get("/api/state")
def api_state() -> JSONResponse:
    snap = store.snapshot()
    snap["prices"] = prices.snapshot()
    if not weather_live and demo_ok:
        snap["weather"] = demo_weather(tz, wcfg.get("demo_effect") or "snow")
    snap["energy"] = tracker.summary()
    snap["server_time"] = iso(datetime.now(tz))
    snap["ui"] = {
        "title": cfg["ui"].get("title"),
        "refresh_seconds": cfg["ui"].get("refresh_seconds", 5),
        "night_dim": cfg["ui"].get("night_dim"),
        "car_name": cfg["vw"].get("name") or "ID.3",
        "cheap_window_hours": cfg["prices"].get("cheap_window_hours", 3),
        "demo_parts": sorted(demo_parts),
        "weather_effects": wcfg.get("effects", "full"),
    }
    return JSONResponse(snap, headers={"Cache-Control": "no-store"})


def _toggle(dev_id: str, value: bool | None) -> dict:
    try:
        if dev_id.startswith("demo-") and demo is not None:
            return demo.toggle(dev_id, value)
        if tuya is None:
            raise HTTPException(404, "Tuya er ikke sat op")
        return tuya.toggle(dev_id, value)
    except KeyError as err:
        raise HTTPException(404, f"Ukendt enhed {dev_id}") from err
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        LOG.warning("Kunne ikke skifte %s: %s", dev_id, err)
        raise HTTPException(502, str(err)) from err


@app.post("/api/devices/{dev_id}/toggle")
def api_toggle(dev_id: str, body: dict | None = Body(default=None)) -> dict:
    value = body.get("on") if isinstance(body, dict) else None
    return _toggle(dev_id, value)


@app.post("/api/charger/toggle")
def api_charger(body: dict | None = Body(default=None)) -> dict:
    charger = store.get("charger") or {}
    if not charger.get("id"):
        raise HTTPException(404, "Ingen lader fundet")
    value = body.get("on") if isinstance(body, dict) else None
    return _toggle(charger["id"], value)


@app.post("/api/car/target")
def api_car_target(body: dict = Body(...)) -> dict:
    try:
        level = float(body.get("level"))
    except (TypeError, ValueError) as err:
        raise HTTPException(400, "level mangler") from err
    car = store.get("car") or {}
    try:
        if car.get("demo") and demo is not None:
            return demo.set_target(level)
        if vw is None:
            raise HTTPException(404, "VW er ikke sat op")
        return vw.set_target(level)
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        LOG.warning("Kunne ikke sætte ladegrænse: %s", err)
        raise HTTPException(502, str(err)) from err


@app.get("/api/health")
def api_health() -> dict:
    return {"ok": True, "threads": {t.name: t.is_alive() for t in threads}}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
