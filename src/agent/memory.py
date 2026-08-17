"""Madeleine — the fact store: retain (write path) + recall phase 1 (read path).

retain is fire-and-forget: the raw exchange is written synchronously (text is
the durable store), extraction runs in a daemon thread. If the extractor is
down, the exchange stays queued (extracted_at IS NULL) and a later sweep can
pick it up — memory never blocks the conversation, and raw text is never lost.

Facts are append-only: superseded, never rewritten (the confabulation
firewall). Raw exchanges are NEVER retrievable — replay/recompute only.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from pgvector.psycopg import register_vector

from . import config, db, embeddings, extractor

logger = logging.getLogger("madeleine.memory")

_NEAR_FACTS_FOR_SUPERSEDE = 5
_RECALL_CANDIDATES = 24


def _conn():
    conn = db.get_connection()
    register_vector(conn)
    return conn


# ── Write path ─────────────────────────────────────────────────────────────────

def retain(scope: str, speaker: str, content: str,
           occurred_at: str | None = None,
           source_ref: str | None = None) -> int:
    """Write the raw exchange (synchronous, durable), then extract in the
    background. Returns the raw_exchanges id immediately."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_exchanges (scope, speaker, content, source_ref, occurred_at) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (scope, speaker, content, source_ref, occurred_at),
            )
            exchange_id = cur.fetchone()["id"]
    threading.Thread(target=_extract_worker, args=(exchange_id,), daemon=True).start()
    return exchange_id


def _extract_worker(exchange_id: int) -> None:
    """Extraction pass for one raw exchange. Failure leaves the row queued
    (extracted_at IS NULL) — visible, retryable, never fatal."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM raw_exchanges WHERE id=%s", (exchange_id,))
                row = cur.fetchone()
        if not row:
            return
        exchange_text = f"{row['speaker']}: {row['content']}"
        near = _nearest_facts(row["scope"], row["content"], _NEAR_FACTS_FOR_SUPERSEDE)
        result = extractor.extract_facts(exchange_text, near)
        if result is None:
            logger.warning("extraction queued (extractor unavailable) for exchange %d", exchange_id)
            return
        facts = result["facts"]
        vectors = embeddings.embed(facts) if facts else []
        near_ids = {f["id"] for f in near}
        valid_supersede = [i for i in result["superseded_ids"] if i in near_ids]
        with _conn() as conn:
            with conn.cursor() as cur:
                new_ids = []
                for text, vec in zip(facts, vectors):
                    cur.execute(
                        "INSERT INTO facts (scope, content, embedding, source_ref) "
                        "VALUES (%s, %s, %s, %s) RETURNING id",
                        (row["scope"], text, vec, f"raw:{exchange_id}"),
                    )
                    new_ids.append(cur.fetchone()["id"])
                # Supersede = status flip + pointer; content is never touched
                for old_id in valid_supersede:
                    cur.execute(
                        "UPDATE facts SET status='superseded', superseded_by=%s "
                        "WHERE id=%s AND status='active'",
                        (new_ids[0] if new_ids else None, old_id),
                    )
                cur.execute("UPDATE raw_exchanges SET extracted_at=NOW() WHERE id=%s",
                            (exchange_id,))
        logger.info("exchange %d: %d facts, %d superseded",
                    exchange_id, len(facts), len(valid_supersede))
    except Exception as e:
        logger.error("extract worker failed for exchange %d: %s", exchange_id, e)


# ── Read path (phase 1: semantic facts) ────────────────────────────────────────

def _nearest_facts(scope: str, query: str, k: int) -> list[dict]:
    try:
        qvec = embeddings.embed([query])[0]
    except Exception as e:
        logger.error("embedding failed for recall: %s", e)
        return []
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content, created_at, 1 - (embedding <=> %s::vector) AS similarity "
                "FROM facts WHERE scope=%s AND status='active' AND embedding IS NOT NULL "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (qvec, scope, qvec, k),
            )
            return [dict(r) for r in cur.fetchall()]


def recall(scope: str, query: str,
           fact_budget_tokens: int | None = None) -> list[dict]:
    """Top-k cosine on active facts in scope, greedy-packed to the token
    budget (~4 chars/token estimate). Returns [] on any failure — memory
    degrades, conversations continue."""
    budget = fact_budget_tokens or config.FACT_BUDGET_TOKENS
    try:
        candidates = _nearest_facts(scope, query, _RECALL_CANDIDATES)
    except Exception as e:
        logger.error("recall failed: %s", e)
        return []
    packed, spent = [], 0
    for f in candidates:
        cost = max(1, len(f["content"]) // 4)
        if spent + cost > budget:
            continue
        spent += cost
        packed.append({"id": f["id"], "content": f["content"],
                       "created_at": f["created_at"],
                       "similarity": round(float(f["similarity"]), 4)})
    return packed
