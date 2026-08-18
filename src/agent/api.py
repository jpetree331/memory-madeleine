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
    # Nightly consolidation — the memory's sleep cycle
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from . import consolidate
        sched = BackgroundScheduler()
        sched.add_job(consolidate.run, "cron", hour=config.NIGHTLY_HOUR,
                      id="nightly_consolidation")
        sched.start()
        logger.info("consolidation scheduled nightly at %02d:00", config.NIGHTLY_HOUR)
    except Exception as e:
        logger.error("scheduler failed to start (service continues): %s", e)
    # Warm the embedder off the critical path — the first recall after a
    # restart otherwise pays the full bge-m3 lazy-load (~15s)
    def _warm():
        try:
            from . import embeddings
            embeddings.embed(["warmup"])
            logger.info("embedder warm")
        except Exception as e:
            logger.warning("embedder warmup failed (will lazy-load): %s", e)
    import threading
    threading.Thread(target=_warm, daemon=True).start()
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
    mood_text: str | None = None       # cheap flavor: current register, colors recall
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
                              mood_text=req.mood_text,
                              debug=req.debug)


# ── Observatory endpoints (addendum) — read-only instruments ──────────────────

@app.get("/api/scopes")
def scopes():
    """Every sky the Observatory can look at — one scope per agent/world."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT scope, COUNT(*) AS episodes FROM episodes "
                        "GROUP BY scope ORDER BY COUNT(*) DESC")
            eps = {r["scope"]: r["episodes"] for r in cur.fetchall()}
            cur.execute("SELECT DISTINCT scope FROM facts")
            for r in cur.fetchall():
                eps.setdefault(r["scope"], 0)
    return {"scopes": [{"scope": s, "episodes": n} for s, n in eps.items()]}


@app.get("/api/stats")
def stats(scope: str | None = None):
    """Counts + last consolidation summary — the Overview cards."""
    import glob
    import json as _json
    where = "WHERE scope=%s" if scope else ""
    params = (scope,) if scope else ()
    out = {}
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT status, COUNT(*) AS c FROM facts {where} GROUP BY status",
                            params)
                out["facts"] = {r["status"]: r["c"] for r in cur.fetchall()}
                cur.execute(
                    f"SELECT COUNT(*) FILTER (WHERE strength >= 1.0) AS strong, "
                    f"COUNT(*) FILTER (WHERE strength >= 0.5 AND strength < 1.0) AS mid, "
                    f"COUNT(*) FILTER (WHERE strength < 0.5) AS faint, "
                    f"COUNT(*) FILTER (WHERE quarantined) AS quarantined, "
                    f"COUNT(*) FILTER (WHERE pinned) AS pinned "
                    f"FROM episodes {where}", params)
                out["episodes"] = dict(cur.fetchone())
                cur.execute("SELECT COUNT(*) AS c FROM edges")
                out["edges"] = cur.fetchone()["c"]
                cur.execute("SELECT COUNT(*) AS c FROM entities")
                out["entities"] = cur.fetchone()["c"]
                cur.execute(f"SELECT COUNT(*) AS c FROM raw_exchanges "
                            f"{where.replace('WHERE', 'WHERE') if where else ''} ", params)
                out["raw_exchanges"] = cur.fetchone()["c"]
    except Exception as e:
        logger.error("stats failed: %s", e)
        return {"error": "db unavailable"}
    runs = sorted(glob.glob(str(config.REPO_ROOT / "data" / "logs" / "consolidate-*.json")))
    if runs:
        try:
            out["last_consolidation"] = _json.loads(Path(runs[-1]).read_text(encoding="utf-8"))
        except Exception:
            pass
    return out


@app.get("/api/episodes")
def episodes_list(scope: str | None = None, q: str | None = None,
                  quarantined: bool | None = None, pinned: bool | None = None,
                  sort: str = "occurred_at", page: int = 1, page_size: int = 50):
    """Paged episode browser. Register text search via q."""
    sort_col = sort if sort in ("occurred_at", "salience", "strength", "recall_count",
                                "created_at") else "created_at"
    clauses, params = [], []
    if scope:
        clauses.append("scope=%s"); params.append(scope)
    if q:
        clauses.append("(register ILIKE %s OR trace ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if quarantined is not None:
        clauses.append("quarantined=%s"); params.append(quarantined)
    if pinned is not None:
        clauses.append("pinned=%s"); params.append(pinned)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM episodes {where}", params)
            total = cur.fetchone()["c"]
            cur.execute(
                f"SELECT id, scope, trace, register, salience, strength, quarantined, "
                f"pinned, recall_count, occurred_at, created_at, last_recalled_at "
                f"FROM episodes {where} ORDER BY {sort_col} DESC NULLS LAST "
                f"LIMIT %s OFFSET %s", params + [page_size, (page - 1) * page_size])
            rows = [dict(r) for r in cur.fetchall()]
    return {"total": total, "episodes": rows}


@app.get("/api/episodes/{episode_id}")
def episode_dossier(episode_id: int):
    """Full dossier: trace, linked entities + facts, revision history."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM episodes WHERE id=%s", (episode_id,))
            ep = cur.fetchone()
            if not ep:
                raise HTTPException(404, "Episode not found")
            ep = {k: v for k, v in dict(ep).items()
                  if k not in ("register_emb", "flavor")}
            cur.execute(
                "SELECT en.id, en.key, en.name, en.kind, e.weight FROM edges e "
                "JOIN entities en ON en.id = e.dst_id "
                "WHERE e.src_kind='episode' AND e.src_id=%s AND e.dst_kind='entity'",
                (episode_id,))
            ep["entities"] = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, content, kind, status FROM facts "
                        "WHERE source_episode_id=%s", (episode_id,))
            ep["facts"] = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, trace, strength, rewritten_at, reason "
                        "FROM episode_revisions WHERE episode_id=%s "
                        "ORDER BY rewritten_at DESC", (episode_id,))
            ep["revisions"] = [dict(r) for r in cur.fetchall()]
    return ep


@app.post("/api/episodes/{episode_id}/pin")
def episode_pin(episode_id: int):
    """Toggle pin (exempt from decay). One of the two mutating controls —
    memory is edited by living, not by clicking."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE episodes SET pinned = NOT pinned WHERE id=%s "
                        "RETURNING pinned", (episode_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Episode not found")
    return {"pinned": row["pinned"]}


class QuarantineReq(BaseModel):
    action: str   # 'approve' (un-quarantine) | 'deny' (keep dark)


@app.post("/api/quarantine/{episode_id}")
def quarantine_review(episode_id: int, req: QuarantineReq):
    """Human review of gate flags — the second of the two mutating controls.
    approve = the episode rejoins retrieval; deny = stays dark. Logged."""
    if req.action not in ("approve", "deny"):
        raise HTTPException(422, "action must be approve | deny")
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT quarantined FROM episodes WHERE id=%s", (episode_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Episode not found")
            if req.action == "approve":
                cur.execute("UPDATE episodes SET quarantined=FALSE WHERE id=%s",
                            (episode_id,))
    logger.info("quarantine review: episode %d %sd", episode_id, req.action)
    return {"episode_id": episode_id, "action": req.action,
            "quarantined": req.action != "approve"}


@app.get("/api/facts")
def facts_list(scope: str | None = None, q: str | None = None,
               status: str | None = None, kind: str | None = None,
               sort: str = "created_at", page: int = 1, page_size: int = 50):
    """The semantic store, visible. With q: live pgvector cosine search —
    the raw RAG view. Without: paged listing, newest first (or by true
    event date with sort=occurred_at)."""
    sort_col = sort if sort in ("created_at", "occurred_at") else "created_at"
    clauses, params = [], []
    if scope:
        clauses.append("scope=%s"); params.append(scope)
    if status:
        clauses.append("status=%s"); params.append(status)
    if kind:
        clauses.append("kind=%s"); params.append(kind)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    if q and q.strip():
        from . import embeddings
        from pgvector.psycopg import register_vector
        try:
            qvec = embeddings.embed([q.strip()])[0]
        except Exception as e:
            logger.error("facts search embed failed: %s", e)
            raise HTTPException(503, "embedder unavailable")
        with db.get_connection() as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, scope, content, kind, status, superseded_by, "
                    f"source_episode_id, source_ref, created_at, occurred_at, "
                    f"1 - (embedding <=> %s::vector) AS similarity FROM facts "
                    f"{where + (' AND' if where else 'WHERE')} embedding IS NOT NULL "
                    f"ORDER BY embedding <=> %s::vector LIMIT %s",
                    [qvec] + params + [qvec, page_size])
                rows = [dict(r) for r in cur.fetchall()]
        return {"total": len(rows), "facts": rows, "mode": "semantic"}
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM facts {where}", params)
            total = cur.fetchone()["c"]
            cur.execute(
                f"SELECT id, scope, content, kind, status, superseded_by, "
                f"source_episode_id, source_ref, created_at, occurred_at "
                f"FROM facts {where} "
                f"ORDER BY {sort_col} DESC NULLS LAST LIMIT %s OFFSET %s",
                params + [page_size, (page - 1) * page_size])
            rows = [dict(r) for r in cur.fetchall()]
    return {"total": total, "facts": rows, "mode": "list"}


@app.get("/api/atlas")
def atlas(scope: str | None = None, space: str = "register"):
    """Projected memory landscape. Register space until Phase-5 flavor exists."""
    col = "reg_proj_x, reg_proj_y" if space == "register" else "proj_x, proj_y"
    where = "AND scope=%s" if scope else ""
    params = (scope,) if scope else ()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, {col.split(',')[0].strip()} AS x, "
                f"{col.split(',')[1].strip()} AS y, register, salience, strength, "
                f"occurred_at FROM episodes "
                f"WHERE {col.split(',')[0].strip()} IS NOT NULL AND NOT quarantined "
                f"{where}", params)
            return {"points": [dict(r) for r in cur.fetchall()], "space": space}


@app.get("/api/gate/feed")
def gate_feed(after_id: int = 0, limit: int = 50):
    """Live feed (polled). Quarantined rows show decision, never content."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT g.id, g.scope, g.salience, g.register, g.decision, g.created_at, "
                "CASE WHEN g.decision != 'quarantined' THEN LEFT(r.content, 90) "
                "ELSE NULL END AS preview "
                "FROM gate_log g LEFT JOIN raw_exchanges r ON r.id = g.exchange_id "
                "WHERE g.id > %s ORDER BY g.id DESC LIMIT %s", (after_id, limit))
            return {"rows": [dict(r) for r in cur.fetchall()]}


@app.get("/api/consolidation/runs")
def consolidation_runs():
    import glob
    import json as _json
    out = []
    for p in sorted(glob.glob(str(config.REPO_ROOT / "data" / "logs" / "consolidate-*.json")),
                    reverse=True)[:30]:
        try:
            out.append(_json.loads(Path(p).read_text(encoding="utf-8")))
        except Exception:
            continue
    return {"runs": out}


# StaticFiles mounted LAST so API routes win (dashboard arrives Sprint 7)
_DIST = config.REPO_ROOT / "dashboard" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.agent.api:app", host="127.0.0.1", port=config.PORT)
