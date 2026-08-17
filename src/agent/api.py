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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, memory

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


class RetainReq(BaseModel):
    scope: str = "companion"
    speaker: str                       # 'user' | 'agent' | 'system'
    content: str
    occurred_at: str | None = None
    source_ref: str | None = None      # backfill provenance, e.g. 'rowan.messages:18234'


class RecallReq(BaseModel):
    scope: str = "companion"
    query: str
    fact_budget_tokens: int | None = None
    assoc_budget_tokens: int | None = None
    debug: bool = False


@app.post("/api/retain")
def retain(req: RetainReq):
    """Fire-and-forget write: raw exchange lands synchronously (durable),
    extraction runs in a daemon thread. Returns immediately."""
    if not req.content.strip():
        raise HTTPException(422, "Empty content")
    if req.speaker not in ("user", "agent", "system"):
        raise HTTPException(422, "speaker must be user | agent | system")
    try:
        exchange_id = memory.retain(req.scope, req.speaker, req.content.strip(),
                                    occurred_at=req.occurred_at,
                                    source_ref=req.source_ref)
    except Exception as e:
        logger.error("retain failed at the raw layer: %s", e)
        raise HTTPException(503, "raw store unavailable")
    return {"ok": True, "exchange_id": exchange_id}


@app.post("/api/recall")
def recall(req: RecallReq):
    """Two-phase retrieval: semantic facts (guaranteed budget) + spreading-
    activation associations (optional budget, labeled, never mixed into
    facts). debug=true adds seeds, per-hop activations, and packing counts —
    the Observatory's recall debugger runs on it."""
    if not req.query.strip():
        raise HTTPException(422, "Empty query")
    return memory.recall_full(req.scope, req.query.strip(),
                              fact_budget_tokens=req.fact_budget_tokens,
                              assoc_budget_tokens=req.assoc_budget_tokens,
                              debug=req.debug)


# StaticFiles mounted LAST so API routes win (dashboard arrives Sprint 7)
_DIST = config.REPO_ROOT / "dashboard" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.agent.api:app", host="127.0.0.1", port=config.PORT)
