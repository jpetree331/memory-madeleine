"""Madeleine — FastAPI service (port 8011). Sprint 0: skeleton + health.

Facts are truth, episodes are texture, flavor is state. The API surface grows
sprint by sprint; this file holds routes and wiring only — capability logic
lives in sibling modules (memory.py, gate.py, spread.py, ...) per the family
module-per-concern pattern.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_log_dir = config.REPO_ROOT / "data" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_file_handler = RotatingFileHandler(_log_dir / "api.log", maxBytes=2_000_000, backupCount=3)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_file_handler)
logger = logging.getLogger("madeleine.api")

app = FastAPI(title="Madeleine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5179"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_READY = False


@app.on_event("startup")
def _startup():
    global DB_READY
    DB_READY = db.setup_schema()
    logger.info("Madeleine up on %d — db_ready=%s", config.PORT, DB_READY)


@app.get("/api/health")
def health():
    """Fleet-dashboard health probe."""
    return {"status": "ok", "service": "madeleine", "db_ready": DB_READY}


# StaticFiles mounted LAST so API routes win (dashboard arrives Sprint 7)
_DIST = config.REPO_ROOT / "dashboard" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.agent.api:app", host="127.0.0.1", port=config.PORT)
