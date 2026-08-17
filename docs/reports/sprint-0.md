# Sprint 0 report — Skeleton, schema, health
*2026-08-17 · Fable*

## Done
- Repo skeleton per agent-backend archetype at `E:\git\Memory-Madeleine`
  (divergence from plan's assumed `E:\git\madeleine` — DECISIONS S0-1).
- Full brief schema as boot-time idempotent DDL in `src/agent/db.py`:
  raw_exchanges / episodes / facts / entities / edges, pgvector columns,
  HNSW indexes on facts.embedding and episodes.register_emb (flavor HNSW
  deferred per plan).
- `/api/health` returns `{status, service, db_ready}` — db_ready surfaces
  degradation state to the fleet dashboard.
- `.env.example` (commented), `.env` (derived DSN, never committed), RUNBOOK,
  DECISIONS, `.cmd` launcher, requirements pinned at scaffold.

## RECON results
- Ports 8011 / 5179 confirmed free against machine claims table.
- Postgres 18.3 local; pgvector **0.8.2** available; database `madeleine`
  created; `CREATE EXTENSION vector` succeeded.

## VERIFY results
- Health 200 on boot 1. ✔
- Restart: DDL re-ran idempotently, health 200. ✔
- Dead-DB test (simulated via unreachable DSN — real Postgres is shared
  fleet infrastructure, not killed; DECISIONS S0-3): **first attempt FAILED
  and found a real bug** — bare `psycopg.connect` to a dead local port hangs
  >120 s on Windows, wedging the startup event, so the service never served.
  Fixed with `connect_timeout=5` in `get_connection`. Re-verified:
  setup_schema returns False in ~10 s, service serves `db_ready: false`. ✔

## Divergences
- S0-1 repo root, S0-2 extractor door env-swappable (openrouter default until
  a dedicated Anthropic key exists), S0-3 dead-DB simulation — all recorded
  in DECISIONS.md.
- `connect_timeout=5` added beyond plan text (required to honor the plan's own
  graceful-degradation guardrail; measured evidence in db.py comment).

## Next
Sprint 1 — fact store: retain + recall (phase-1 retrieval), bge-m3 lazy
singleton, extractor via swappable door, supersede logic.
