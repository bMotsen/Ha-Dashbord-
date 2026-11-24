"""Fælles, trådsikker tilstand som udbyderne skriver til og API'et læser fra."""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, key: str, **fields: Any) -> None:
        with self._lock:
            cur = self._data.setdefault(key, {})
            cur.update(fields)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._data.get(key, default))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)


def load_json(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except Exception:  # noqa: BLE001
        LOG.warning("Kunne ikke læse %s - starter forfra", path, exc_info=True)
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomisk skrivning så en strømafbrydelse ikke efterlader en halv fil."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, default=str)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001
        LOG.warning("Kunne ikke gemme %s", path, exc_info=True)
