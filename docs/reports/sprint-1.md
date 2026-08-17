# Sprint 1 report — Fact store: retain + recall (phase-1 retrieval)
*2026-08-17 · Fable*

## Done
- `memory.py` — retain (raw exchange synchronous + daemon-thread extraction),
  recall (cosine top-k over active facts in scope, greedy-packed to budget),
  supersede as status-flip + pointer (content physically untouched).
- `extractor.py` — swappable-door LLM client (anthropic | openrouter, same
  claude-haiku-4-5 brain). Extraction prompt encodes the Grain-audit laws:
  speakers named explicitly, abstract nouns are not people, intentions are
  not events. Strict-JSON contract with fence tolerance.
- `embeddings.py` — bge-m3 lazy singleton, local, 1024-dim normalized.
- `memory_tools.py` — degradation-safe wrappers (family signature pairing).
- API: `POST /api/retain` (fire-and-forget), `POST /api/recall`.
- DDL: `raw_exchanges.extracted_at` as the visible extraction queue marker.

## VERIFY results (scripts/verify-sprint1.py, self-cleaning scope)
- **PASS** retain+extract 10 fixtures — 14 facts, **zero orphan facts**
  (every row carries provenance; divergence rule held).
- **PASS** recall accuracy — 5/5 queries hit (threshold ≥4).
- **PASS** contradiction supersede — old fact kept AND superseded, new active.
  The append-only firewall works as designed.
- **PASS** keyless degradation — raw exchange written, row visibly queued
  (`extracted_at IS NULL`), no crash, no loss.

## Notes & lessons
- Schema edits require a `setup_schema` rerun before out-of-process scripts
  see them (first verify run failed on the not-yet-applied `extracted_at`
  column; service restart applied it). Boot-time DDL covers the service; the
  verify scripts now assume a current schema.
- Observatory addendum DDL (episode_revisions, gate_log, pinned/projection
  columns) folded in this session — born-native rather than retrofitted, so
  Sprint 2's gate and Sprint 4's consolidation can write their instruments'
  tables from day one.

## Next
Sprint 2 — the salience gate (also the sanitization gate), episodes, and the
first co-occurrence edges. The snowflake begins.
