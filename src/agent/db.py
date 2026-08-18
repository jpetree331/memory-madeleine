"""Madeleine — PostgreSQL layer. One database, three stores:

  raw_exchanges — replay store; NEVER retrieved. Text is the durable truth;
                  every vector in this schema is a derived, recomputable index.
  facts         — semantic memory. Append-only: superseded, never rewritten.
  episodes      — episodic memory. Salience-gated traces; reconsolidate freely.
  entities/edges — the snowflake: co-occurrence graph for spreading activation.

No ORM, boot-time idempotent DDL, dict_row — the family pattern.
"""
from __future__ import annotations

import logging

import psycopg
from psycopg.rows import dict_row

from . import config

logger = logging.getLogger("madeleine.db")

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS raw_exchanges (      -- replay store, never retrieved
  id SERIAL PRIMARY KEY,
  scope TEXT NOT NULL DEFAULT 'companion',
  speaker TEXT NOT NULL,                        -- 'user' | 'agent' | 'system'
  content TEXT NOT NULL,
  source_ref TEXT,                              -- e.g. 'rowan.messages:18234' for backfill
  occurred_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS episodes (
  id SERIAL PRIMARY KEY,
  scope TEXT NOT NULL DEFAULT 'companion',
  trace TEXT NOT NULL,                          -- compressed narrative: arc, turns, feel
  register TEXT,                                -- cheap flavor: one-line texture tag
  register_emb VECTOR(1024),                    -- bge-m3 of register text
  flavor VECTOR(4096),                          -- deep layer; NULL until Phase 5
  salience REAL NOT NULL,
  strength REAL NOT NULL DEFAULT 1.0,           -- decays nightly, boosted on recall
  quarantined BOOLEAN NOT NULL DEFAULT FALSE,   -- gate flagged; excluded from ALL retrieval
  exchange_start INT REFERENCES raw_exchanges(id),
  exchange_end INT REFERENCES raw_exchanges(id),
  occurred_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_recalled_at TIMESTAMPTZ,
  recall_count INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS facts (
  id SERIAL PRIMARY KEY,
  scope TEXT NOT NULL DEFAULT 'companion',
  content TEXT NOT NULL,
  embedding VECTOR(1024),
  kind TEXT NOT NULL DEFAULT 'stated',          -- 'stated' | 'derived'
  status TEXT NOT NULL DEFAULT 'active',        -- 'active' | 'superseded'
  superseded_by INT REFERENCES facts(id),
  source_episode_id INT REFERENCES episodes(id) ON DELETE SET NULL,
  source_ref TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS entities (
  id SERIAL PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,                     -- canonical slug: 'rowan', 'older-son'
  name TEXT NOT NULL,
  kind TEXT,                                    -- 'person' | 'project' | 'place' | 'concept'
  summary TEXT
);

CREATE TABLE IF NOT EXISTS edges (
  id SERIAL PRIMARY KEY,
  src_kind TEXT NOT NULL, src_id INT NOT NULL,  -- 'episode' | 'entity' | 'fact'
  dst_kind TEXT NOT NULL, dst_id INT NOT NULL,
  kind TEXT NOT NULL,                           -- 'cooccur' | 'co_retrieval' | 'derived_from'
  weight REAL NOT NULL DEFAULT 1.0,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (src_kind, src_id, dst_kind, dst_id, kind)
);

-- extraction queue marker: NULL = queued/unprocessed (Sprint 1)
ALTER TABLE raw_exchanges ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;
-- source-side privacy marker (Rowan ingest): retrieval ignores it today;
-- future public-facing guardrails can filter derived facts/episodes via
-- provenance joins. Signal preserved, policy deferred.
ALTER TABLE raw_exchanges ADD COLUMN IF NOT EXISTS private BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS episode_revisions (   -- reconsolidation audit trail
  id SERIAL PRIMARY KEY,                          -- (Observatory addendum)
  episode_id INT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  trace TEXT NOT NULL,                            -- the trace as it was BEFORE rewrite
  strength REAL,
  rewritten_at TIMESTAMPTZ DEFAULT NOW(),
  reason TEXT                                     -- 'reconsolidation' | 'decay_compress' | 'tombstone'
);
CREATE INDEX IF NOT EXISTS idx_revisions_ep ON episode_revisions (episode_id);

ALTER TABLE episodes ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;  -- true event time, from the source exchange
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS proj_x REAL;      -- flavor projection, nightly
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS proj_y REAL;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS reg_proj_x REAL;  -- register-emb projection
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS reg_proj_y REAL;

CREATE TABLE IF NOT EXISTS recall_log (          -- co-retrieval evidence (Sprint 4)
  id SERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  query TEXT,                                     -- for reconsolidation context
  fact_ids INT[] NOT NULL DEFAULT '{}',
  episode_ids INT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recall_log_time ON recall_log (created_at);

CREATE TABLE IF NOT EXISTS gate_log (            -- live feed source; also great debugging
  id SERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  salience REAL,
  register TEXT,
  decision TEXT NOT NULL,                        -- 'episode' | 'facts_only' | 'quarantined' | 'skipped'
  exchange_id INT REFERENCES raw_exchanges(id),
  episode_id INT REFERENCES episodes(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges (src_kind, src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges (dst_kind, dst_id);
CREATE INDEX IF NOT EXISTS idx_facts_emb ON facts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_ep_register ON episodes USING hnsw (register_emb vector_cosine_ops);
-- HNSW on episodes.flavor deferred to Phase 5: build after backfill fills it.
"""


def get_connection():
    if not config.DATABASE_URL:
        raise ValueError("MADELEINE_DATABASE_URL is required — set it in .env")
    # connect_timeout: a dead/unreachable Postgres must fail in seconds, not
    # hang the startup event for minutes (MEASURED 2026-08-17: bare connect to
    # a dead local port hung >120s on Windows; the graceful-degradation
    # guarantee depends on this bound)
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row,
                           connect_timeout=5)


def setup_schema() -> bool:
    """Idempotent boot DDL. Returns True on success, False when the database
    is unreachable — the service stays up and serves /api/health regardless
    (graceful degradation is a brief guardrail, not an aspiration)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
        logger.info("schema ready (idempotent DDL applied)")
        return True
    except Exception as e:
        logger.error("schema setup failed — serving health only: %s", e)
        return False
