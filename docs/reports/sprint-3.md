# Sprint 3 report — Spreading activation
*2026-08-17 · Fable*

## Done
- `spread.py` — seeded traversal (query-entity match + provenance pointers
  from phase-1 fact hits), per-hop decay × edge weight × episode strength,
  thresholded collection, activation×salience ranking, greedy budget packing,
  recall-strengthening (+0.1, cap 2.0), full per-hop debug trace for the
  Observatory's recall debugger. Two batched queries per hop, not a recursive
  CTE — chosen for debuggability (the debugger wants per-hop activations).
- `recall_full` — two-phase retrieval; associations labeled and separate,
  `context_block` renders them with the `impression:` prefix. Phase-2 failure
  degrades to facts-only.
- API `/api/recall` upgraded in place; `debug: true` supported.

## VERIFY results (scripts/verify-sprint3.py, hand-built fixture, self-cleaning)
- **PASS — THE SOUL TEST.** Query: "that Patsy Cline song keeps coming back
  to me." The red-Plymouth episode — whose trace shares ZERO vocabulary with
  the query (no song, no music, no radio) — surfaced via pure 3-hop graph
  spread at activation 0.216. A quarantined decoy wired into the same chain
  stayed dark. **The design's central claim is now a passing test.**
- **PASS** factual query: correct fact, zero associations. The graph
  contributes nothing when nothing is owed.
- **PASS** 10-token association budget squeeze respected.
- **PASS** recalled episode strengthened (recall_count 1, strength 1.10) —
  memory learns from being used.
- **PASS** graph output labeled `impression:` — color, never citation.

## Divergence (measured, recorded)
- **SPREAD_DECAY default 0.5 → 0.6** (DECISIONS S3-1). The plan's defaults
  made its own acceptance test unreachable: 0.5³ = 0.125 < threshold 0.15 for
  every weight-1.0 three-hop chain. First verify run failed on exactly this;
  0.6³ = 0.216 clears with margin while 4-hop activation (0.13) still dies.
  The predicted "retrieval tuning is where the iteration lives" arrived on
  day one and was caught by the acceptance test doing its job.

## Next
Sprint 4 — nightly consolidation: co-retrieval edges, decay, pattern
promotion, reconsolidation (with episode_revisions audit trail, born-native).
