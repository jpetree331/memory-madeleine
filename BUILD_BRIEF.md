# BUILD_BRIEF.md — Madeleine (codename: Madeleine)

## What this is
A memory service for LLM agents that stores three things per exchange, not one:
1. **Facts** — atomic, embedded, versioned. Boring and reliable. (Semantic memory)
2. **Episodes** — salience-gated compressed traces of exchanges, linked to every entity they touched via a co-occurrence graph. (Episodic memory)
3. **Flavor** — the conversation's register, captured two ways: a cheap text tag + embedding at write time, and a deep activation vector from a local reader model, computed nightly. (Affective memory)

Retrieval is two-phase: semantic match on facts (guaranteed context budget), then spreading activation through the episode graph seeded by phase-1 hits + current-turn entities (smaller, optional budget). A nightly consolidation job grows co-retrieval edges, decays unused episodes, promotes cross-episode patterns into derived facts, and reconsolidates recalled episodes.

Primary consumer: Rowan (HTTP tools). Secondary: Claude Code / web Claude via a FastMCP wrapper (later phase). Early proving-ground consumer: Agent-Boardspace (the parlor), whose dispatcher seam and audit culture (Grain) provide low-stakes accuracy evidence before any Rowan cutover. Successor candidate to Hindsight — runs in parallel until proven, see GATE A.

## Locked decisions
- **Postgres + pgvector is the only database.** One DB (`madeleine`), all three stores as tables. No Neo4j, no SQLite, no Graphiti — the graph is an `edges` table + Python traversal.
- **Text is the durable store; every vector is a derived, recomputable index.** Model swaps mean re-embedding, never data loss.
- **One reader model for all flavor vectors** (live and backfilled). Mixed-model vectors are meaningless.
- **Facts never reconsolidate; episodes always can.** Facts are superseded (old row kept, `status='superseded'`), never rewritten. This is the confabulation firewall.
- **The salience gate is also the sanitization gate.** One gate prompt scores salience AND screens for instruction-bearing content. Flagged content stored quarantined, never retrievable.
- **Extraction/salience LLM: `claude-haiku-4-5`**, door env-swappable (`EXTRACTOR_PROVIDER=anthropic|openrouter`). Embeddings: **local `BAAI/bge-m3`** (1024-dim), lazy singleton in-process.
- **Flavor capture runs nightly, not live.** GPU is contended. Live and retroactive capture share one code path (recomputability made concrete).
- **Service port 8011, dashboard dev port 5179.** Confirmed free 2026-08-17.
- **No injection this build.** Seam only. See GATE C.

## Stack & environment
- Windows 11, repo at `E:\git\Memory-Madeleine`, port **8011**, dashboard dev **5179**.
- Python, FastAPI ≥0.115, uvicorn ≥0.32, psycopg[binary] ≥3.1 with `dict_row` — **no ORM**. APScheduler ≥3.10. httpx ≥0.27. anthropic ≥0.40. sentence-transformers + torch (CUDA) for bge-m3. transformers + accelerate for the Phase-5 reader model.
- PostgreSQL local with **pgvector** (0.8.2 confirmed). Database `madeleine`. Boot-time idempotent DDL, no migration tool.
- Dashboard: Vite + React (.jsx) + Tailwind 4 via `@tailwindcss/vite`, proxying `/api` → 8011.
- Deployment: logon Scheduled Task via `.cmd` wrapper (`PYTHONUTF8=1`), restart-on-failure ×3. RUNBOOK.md + DECISIONS.md live from Sprint 0.

## The autonomy clause (applies to every sprint)
Work autonomously to completion. Do not stop to ask for confirmation on reversible implementation choices — pick the sound default, note it in your summary, and keep going. Never: change the locked stack, add paid services, or weaken the sanitization gate without flagging.

## The Recon → Build → Verify contract
Every sprint runs RECON (read before writing), BUILD, VERIFY (do this, don't skip), and reports divergences from the plan in `docs/reports/sprint-N.md`.

## Divergence rules (do NOT break these without flagging)
- **No raw exchange text is ever retrievable.** Only extracted facts and gate-passed episode traces enter retrieval. Raw text lives in `raw_exchanges` for replay/recompute only.
- **Facts are append-only.** Supersede, never UPDATE content. Reconsolidation code must be physically unable to touch the `facts` table (separate module, no import of fact-write functions).
- **Every fact row carries `source_episode_id` or `source_ref`** — no orphan facts, ever, including backfill.
- **Graph output is labeled.** Spreading-activation results return under `associations`, never mixed into `facts`, rendered with an `impression:` prefix.
- **All vector columns are rebuildable.** Any code that writes a vector has a corresponding `scripts/rebuild_*.py`.
- **Scope isolation.** `scope` column (`companion` | `project:<name>`) on facts and episodes; every retrieval filters by scope. No LLM-judgment access control.

## Decision gates
- **⚠️ GATE A (before Phase 6):** Hindsight cutover — parallel-run results decide retire vs. coexist.
- **⚠️ GATE B (before Sprint 5.1):** Reader model choice. Default `Qwen/Qwen3-8B`; probe layers empirically.
- **⚠️ GATE C (indefinite):** Injection. Seam only until a local open-weight generator exists.

## Guardrails carried throughout
- Gate prompt screens every write for embedded instructions. Flagged → `quarantined=TRUE`, logged, never retrievable. Applies to backfill too.
- `.env.example` heavily commented: where each value comes from.
- Graceful degradation: extractor down → `retain` still writes `raw_exchanges` and queues extraction; `recall` serves phase-1 from existing facts. Wrappers return `""`/`[]`, never raise into the agent loop.
- Fire-and-forget: `retain` returns immediately; extraction/gating in a daemon thread.
- Every knob has an env default (see `src/agent/config.py`).

## Schema
Source of truth: `src/agent/db.py` (DDL applied idempotently at boot).
