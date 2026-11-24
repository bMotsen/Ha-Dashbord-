"""Start-script til Home Assistant add-on'et.

Læser indstillingerne fra add-on'ets Konfiguration-fane (/data/options.json), henter husets
placering og tidszone fra Home Assistant og fletter en evt. avanceret config.yaml ind fra
/addon_configs/local_solar_dashboard/ (= /config i containeren). Starter derefter dashboardet.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

OPTIONS = Path(os.environ.get("ADDON_OPTIONS", "/data/options.json"))
DATA = Path(os.environ.get("ADDON_DATA", "/data"))
USER_DIR = Path(os.environ.get("ADDON_CONFIG_DIR", "/config"))
APP_DIR = Path(__file__).resolve().parent
PORT = 8765  # skal matche ingress_port i add-on'ets config.yaml

ADVANCED_TEMPLATE = """# Avancerede indstillinger til Solar Dashboard (valgfri).
# Det du skriver her, lægges oven i det du har valgt i add-on'ets Konfiguration-fane.
# Genstart add-on'et efter ændringer. Eksempler (fjern # foran):
#
# prices:
#   grid_gln: "5790000610099"      # dit netselskabs GLN (når netselskab = andet)
#   grid_codes: ["DT_C_01"]
#   cheap_window_hours: 4
#
# tuya:
#   hide: ["Gammel pære"]
#   rename: {"bf12ab34cd56ef78gh90": "Lampe i stuen"}
#   order: ["Stue loftlampe", "Kaffemaskine"]
#
# weather:
#   latitude: 55.676                # kun hvis du vil bruge et andet sted end Home Assistants hjem
#   longitude: 12.568
#
# ui:
#   night_dim: [23, 6]
"""


def log(msg: str) -> None:
    print(f"[solar-dashboard] {msg}", flush=True)


def ha_config() -> dict:
    """Husets placering, navn og tidszone fra Home Assistant."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return {}
    try:
        req = urllib.request.Request("http://supervisor/core/api/config", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as err:  # noqa: BLE001
        log(f"Kunne ikke hente placering fra Home Assistant: {err}")
        return {}


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def main() -> None:
    opt = json.loads(OPTIONS.read_text()) if OPTIONS.exists() else {}
    ha = ha_config()
    USER_DIR.mkdir(parents=True, exist_ok=True)
    adv_file = USER_DIR / "config.yaml"
    if not adv_file.exists():
        adv_file.write_text(ADVANCED_TEMPLATE, encoding="utf-8")
    advanced = yaml.safe_load(adv_file.read_text(encoding="utf-8")) or {}

    s = lambda k: (opt.get(k) or "").strip() if isinstance(opt.get(k), str) else opt.get(k)  # noqa: E731
    grid = s("grid_company")
    cfg = {
        "server": {"host": "0.0.0.0", "port": PORT},
        "timezone": ha.get("time_zone") or "Europe/Copenhagen",
        "demo_when_disabled": bool(opt.get("demo_when_disabled", True)),
        "solplanet": {
            "enabled": (s("solplanet_host") or "").lower() != "demo",
            "host": s("solplanet_host") or "auto",
            "battery_capacity_kwh": opt.get("battery_capacity_kwh"),
        },
        "prices": {
            "area": s("price_area") or "DK1",
            "grid_company": "" if grid in (None, "", "andet") else grid,
            "supplier_markup": float(opt.get("supplier_markup") or 0),
            "sell_fee": float(opt.get("sell_fee") or 0),
        },
        "vw": {
            "enabled": bool(s("vw_username")),
            "username": s("vw_username") or "",
            "password": opt.get("vw_password") or "",
            "name": s("car_name") or "ID.3",
        },
        "tuya": {
            "enabled": bool(s("tuya_api_key")),
            "api_key": s("tuya_api_key") or "",
            "api_secret": opt.get("tuya_api_secret") or "",
            "api_device_id": s("tuya_device_id") or "",
            "devices_file": str(USER_DIR / "devices.json"),
            "snapshot_file": str(USER_DIR / "snapshot.json"),
        },
        "weather": {
            "latitude": ha.get("latitude"),
            "longitude": ha.get("longitude"),
            "name": ha.get("location_name") or "",
            "effects": s("weather_effects") or "full",
        },
    }
    cfg = deep_merge(cfg, advanced)
    cfg["server"] = {"host": "0.0.0.0", "port": PORT}

    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "dashboard_config.yaml"
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.chmod(out, 0o600)

    live = [n for n, on in ((f"Solplanet ({cfg['solplanet']['host']})", cfg["solplanet"]["enabled"]), ("VW", cfg["vw"]["enabled"]),
                            ("Tuya", cfg["tuya"]["enabled"]), ("vejr", cfg["weather"]["latitude"] is not None)) if on]
    log(f"Live: {', '.join(live) or 'intet endnu (demo-data)'} · elpris {cfg['prices']['area']}")
    log(f"Dashboard på port {PORT} – åbn 'Energi' i sidepanelet eller http://<home-assistant-ip>:{PORT}/?kiosk=1")

    env = dict(os.environ, DASHBOARD_CONFIG=str(out), DASHBOARD_DATA=str(DATA / "dashboard"))
    os.chdir(APP_DIR)
    os.execvpe(sys.executable, [sys.executable, "-m", "app"], env)


if __name__ == "__main__":
    main()
