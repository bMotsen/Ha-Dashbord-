"""Indlæser config.yaml og fletter den med standardværdier."""
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

LOG = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DASHBOARD_DATA") or BASE_DIR / "data")
WEB_DIR = BASE_DIR / "web"

DEFAULTS: dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8080},
    "timezone": "Europe/Copenhagen",
    # Vis demo-data for de dele der ikke er sat op endnu (så dashboardet altid ser færdigt ud)
    "demo_when_disabled": True,
    # Tving demo-data for ALT (god til at teste udseendet)
    "demo": False,
    "ui": {
        "refresh_seconds": 5,
        "title": "Hjem",
        "night_dim": [23, 6],       # dæmp skærmen fra kl. 23 til 06 (sæt til null for at slå fra)
    },
    "solplanet": {
        "enabled": False,
        "host": "",
        # "auto" prøver https:443, http:8484 og http:80 i den rækkefølge
        "scheme": "auto",
        "port": None,
        "inverter_sn": "",      # tom = find automatisk via getdev.cgi?device=2
        "battery_sn": "",       # tom = prøv inverter-SN, derefter dongle-SN
        "meter_sn": "",         # tom = prøv inverter-SN, derefter dongle-SN
        "poll_seconds": 10,
        "battery_capacity_kwh": None,   # fx 10.0 - bruges til "fuld om"/"tom om"
        # Hvis batteriet ikke rapporterer status (bst): hvilket fortegn har "pb"?
        "battery_power_positive": "discharge",   # "discharge" eller "charge"
        # Måler "pac": positiv = køb fra nettet (Solplanet standard). Sæt true hvis det er omvendt.
        "invert_grid": False,
        # Hvor kommer PV-effekt fra: "auto" (batteri-ppv hvis findes ellers inverter-pac), "battery", "inverter", "strings"
        "pv_source": "auto",
        "verify_tls": False,
    },
    "prices": {
        "enabled": True,
        "area": "DK1",                  # DK1 = Jylland/Fyn, DK2 = Sjælland/øerne
        "source": "energidataservice",  # eller "elprisenligenu"
        "vat": 0.25,
        "supplier_markup": 0.0,         # elhandlerens tillæg kr/kWh ekskl. moms
        "sell_fee": 0.0,                # fradrag på salgspris kr/kWh (handelsomkostning)
        "grid_company": "",             # fx "radius", "cerius", "n1", "trefor" (se app/providers/prices.py)
        "grid_gln": "",                 # alternativt: GLN-nummer for dit netselskab
        "grid_codes": [],               # ... og ChargeTypeCode(s) for din nettarif
        # Manuel nettarif (kr/kWh ekskl. moms) hvis du ikke vil bruge Datahub:
        # manual_tariff:
        #   winter: {low: 0.15, high: 0.45, peak: 1.35}
        #   summer: {low: 0.15, high: 0.23, peak: 0.60}
        "manual_tariff": None,
        "energinet": {
            "gln": "5790000432752",
            "codes": ["40000", "41000"],   # transmissions-nettarif + systemtarif
            "tax_codes": ["EA-001"],       # elafgift
        },
        # Bruges KUN hvis Energi Data Service ikke svarer og der intet er i cachen
        "fallback": {"energinet": 0.12, "elafgift": 0.008},
        "eur_dkk": 7.46,
        "cheap_window_hours": 3,
        "refresh_minutes": 30,
    },
    "news": {
        "enabled": True,
        "refresh_minutes": 10,
        # egne kilder: [{"name": "TV2 Nord", "feeds": ["https://..."], "limit": 8}]
        "sources": None,
    },
    "weather": {
        "enabled": True,
        "latitude": None,           # fx 55.68 (find dit hus på Google Maps: højreklik -> koordinater)
        "longitude": None,          # fx 12.57
        "name": "",                 # fx "Hjem"
        "refresh_minutes": 10,
        "effects": "full",          # "full", "light" (kun på fliserne, ingen baggrund) eller "off"
        "demo_effect": "snow",      # vejret der vises før lat/lon er sat: snow, rain, clear, cloudy, thunder, fog
    },
    "vw": {
        "enabled": False,
        "username": "",
        "password": "",
        "spin": "",
        "vin": "",                  # tom = første elbil på kontoen
        "name": "ID.3",
        "interval_seconds": 300,    # VW tillader minimum 180 sek
        "battery_capacity_kwh": 58,
    },
    "tuya": {
        "enabled": False,
        "region": "eu",
        "api_key": "",
        "api_secret": "",
        "api_device_id": "",        # et vilkårligt af dine Tuya enheds-ID'er
        "use_local": True,          # styr/aflæs over LAN når IP + local key kendes (hurtigere)
        "devices_file": "devices.json",    # fra `python -m tinytuya wizard` (valgfri)
        "snapshot_file": "snapshot.json",  # fra `python -m tinytuya scan` (valgfri)
        "scan_network": True,       # find enheders IP automatisk på netværket
        "poll_local_seconds": 10,
        "poll_cloud_seconds": 60,
        "refresh_devices_minutes": 360,   # hent ny enhedsliste fra skyen (nye enheder dukker op af sig selv)
        "hide": [],                 # ID'er eller navne der ikke skal vises
        "rename": {},               # {"enheds-id": "Nyt navn"}
        "order": [],                # ID'er eller navne i ønsket rækkefølge
        "ev_charger_id": "",        # tom = find automatisk (Tuya kategori "qccdz")
        "show_charger_in_devices": False,
        "confirm_charger_toggle": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path or os.environ.get("DASHBOARD_CONFIG", BASE_DIR / "config.yaml"))
    user_cfg: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
        LOG.info("Indlæste konfiguration fra %s", path)
    else:
        LOG.warning("Ingen %s fundet - kører med standardindstillinger (demo)", path)
    cfg = _deep_merge(DEFAULTS, user_cfg)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return cfg


def resolve_path(p: str) -> Path:
    """Relativ sti tolkes i forhold til projektmappen."""
    pp = Path(p)
    return pp if pp.is_absolute() else BASE_DIR / pp
