# Sprint 4 report — Nightly consolidation
*2026-08-17 · Fable*

## Done
- `consolidate.py`: co-retrieval edges (from the new `recall_log` evidence
  table — additive DDL, required by the plan's own spec), decay ×0.98 with
  pin exemption, decay-compression and tombstoning with `episode_revisions`
  audit rows before EVERY rewrite (divergence rule, held), pattern promotion
  to append-only `derived` facts with evidence edges, reconsolidation of
  recalled episodes using their actual recall contexts, and the Observatory
  projection pass (numpy-SVD PCA of register embeddings → reg_proj_x/y).
- APScheduler wired at NIGHTLY_HOUR; `scripts/run_consolidation.py` manual
  trigger (same code path). Run summaries to data/logs (.log + .json).
- FIREWALL BY CONSTRUCTION: consolidate.py imports zero fact-write functions.

## VERIFY results (7/7)
- decay applied (0.980); pinned episode untouched (1.000)
- reconsolidation drifted a recalled trace toward its recall contexts;
  original preserved in episode_revisions ("gift" → "toolbox, letting the
  weight of it..."), diff logged
- 3-episode pattern promoted to one derived fact with derived_from edges to
  all three ("Jess pushes through fatigue to continue work on projects...")
- **xmin comparison: zero pre-existing fact rows UPDATEd**
- compression + tombstone both audited; tombstoned episode's edges pruned
- co-retrieval edge grown from 3 shared recalls (weight 0.9)
- 8 register projections computed

## Fixes found by VERIFY
- pgvector rows can arrive as Vector objects despite register_vector —
  `_as_array` normalizes (measured, first run failed the projection pass).
- Haiku decorates rewrites with markdown headings despite instructions —
  `_clean_llm_text` strips them (measured: "# Trace Rewrite").

# Sprint 5 report — Cheap flavor: mood-congruent retrieval
*2026-08-17 · Fable*

## Done
- `recall` accepts `mood_text`; ranking blends register-space cosine:
  `rank = activation × salience × (1 + MOOD_WEIGHT × cos(register, mood))`.
  `mood_similarity` surfaced on association items. Moodless recall unchanged.

## VERIFY results (3/3)
- Same lake-house query: sorrowful mood surfaces the funeral episode first,
  playful mood surfaces the cannonball contest first — the order flips.
- Similarity values surfaced; moodless path regression-clean.
State-dependent recall exists. Sad states surface sad memories, cheaply.
