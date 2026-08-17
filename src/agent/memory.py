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

from . import config, db, embeddings, episodes, extractor, gate

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
    """Full write pipeline for one raw exchange:

      gate → (quarantine short-circuit) → episode when salient → facts →
      entities + co-occurrence edges → gate_log

    Failure at any LLM stage leaves the row queued (extracted_at IS NULL) —
    visible, retryable, never fatal. Raw text is already durable."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM raw_exchanges WHERE id=%s", (exchange_id,))
                row = cur.fetchone()
        if not row:
            return
        exchange_text = f"{row['speaker']}: {row['content']}"

        # 1. The gate — salience AND sanitization, one judgment
        g = gate.assess(exchange_text)

        # 2. Injection risk: quarantined episode, NO facts, raw kept, loud log
        if g["injection_risk"]:
            trace = episodes.write_trace(exchange_text) or \
                "(quarantined before trace generation)"
            with _conn() as conn:
                ep_id = episodes.create(
                    conn, scope=row["scope"], trace=trace, register=g["register"],
                    salience=g["salience"], quarantined=True,
                    exchange_id=exchange_id, occurred_at=row["occurred_at"])
                gate.log_decision(conn, row["scope"], "quarantined", g,
                                  exchange_id, ep_id)
                with conn.cursor() as cur:
                    cur.execute("UPDATE raw_exchanges SET extracted_at=NOW() WHERE id=%s",
                                (exchange_id,))
            logger.warning("QUARANTINED exchange %d (episode %d): %s",
                           exchange_id, ep_id, "; ".join(g["reasons"]))
            return

        # 3. Episode, when the exchange earns one
        episode_id = None
        episodic = g["salience"] >= config.SALIENCE_THRESHOLD
        if episodic:
            trace = episodes.write_trace(exchange_text)
            if trace:
                with _conn() as conn:
                    episode_id = episodes.create(
                        conn, scope=row["scope"], trace=trace.strip(),
                        register=g["register"], salience=g["salience"],
                        quarantined=False, exchange_id=exchange_id,
                        occurred_at=row["occurred_at"])
            else:
                logger.warning("trace generation failed for exchange %d — "
                               "facts proceed, episode skipped", exchange_id)

        # 4. Facts (+ entities) — Sprint 1 path, now with episode provenance
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
                        "INSERT INTO facts (scope, content, embedding, source_ref, "
                        "source_episode_id) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (row["scope"], text, vec, f"raw:{exchange_id}", episode_id),
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
            # 5. The snowflake grows: entities + co-occurrence edges
            linked = 0
            if episode_id is not None and result.get("entities"):
                linked = episodes.link_entities(conn, episode_id,
                                                result["entities"], g["salience"])
            gate.log_decision(conn, row["scope"],
                              "episode" if episode_id else "facts_only",
                              g, exchange_id, episode_id)
        logger.info("exchange %d: salience=%.2f episode=%s facts=%d entities=%d superseded=%d",
                    exchange_id, g["salience"], episode_id, len(facts),
                    linked, len(valid_supersede))
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
