"""Start med:  python -m app"""
import logging

import uvicorn

from .config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpcore", "tinytuya", "carconnectivity"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

if __name__ == "__main__":
    cfg = load_config()
    uvicorn.run("app.main:app", host=cfg["server"]["host"], port=int(cfg["server"]["port"]), log_level="warning")
