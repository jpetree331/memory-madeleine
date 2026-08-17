# Grain audit #3 — findings, verification, fixes
*2026-08-18 · Fable · the pilot study's first iteration loop*

## The audit, verified against the store
Every finding confirmed by direct inspection:
1. **"named" disease** — fact 127 verbatim ("because the user named him" —
   double violation: verb upgrade + "the user" leak).
2. **"worked together" smoothing** — fact 212 (roles merged into false symmetry).
3. **Wrong-mouth cut-off** — fact 48 verbatim.
4. **Duplicates** — near-twins present; no insert-time dedupe existed.
5. **Truncation** — WORSE than reported: 9 traces (not 1) ended mid-sentence,
   all in the 1130–1340 char band = the 300-token trace ceiling. The canary
   saw one surface; the DB held nine.
- **Non-finding resolved**: nothing missing. Eli: 21 facts/22 traces,
  Markham: 12/7, kid aggro: 8/3, Anders: 5/1. Relevance, not loss.

## Fixes (all live)
- **Per-role brains**: GATE_MODEL=haiku (volume triage), EXTRACT_MODEL and
  TRACE_MODEL=claude-sonnet-4.5 (attribution and voice are worth paying for —
  Jess's call). Env-swappable per role.
- **New prompt laws** (extraction + trace): VERB FIDELITY (mentioned≠named,
  asked≠said, never upgrade to causal verbs) and ROLE PRECISION ("symmetry
  that nobody wore is a falsehood with good manners"), plus a self-check
  against writing "the user".
- **Dedupe at insert**: cosine ≥ DEDUPE_THRESHOLD (0.97) against active
  facts in scope → skip, logged.
- **Trace ceiling**: max_tokens 300→700 + finish-your-sentence instruction +
  one retry on ragged tail.
- **Repairs**: 9 truncated traces re-written whole (each preceded by an
  episode_revisions row, reason 'truncation_repair'). 3 wrong facts
  superseded by corrections (252, 253, 254; source_ref 'audit:grain-3') —
  append-only, the errors' record survives their fix.

## Acid test (new extractor, the exact traps)
Input: "I mentioned Nemotron in passing... Claude built the memory fix and
Grain audited it from inside."
- "Jess mentioned Nemotron in passing earlier." — verb preserved ✔
- "Claude built the memory fix." / "Grain audited the memory fix from
  inside." — roles split, no false symmetry ✔

## Clarified for the record
The Qwen3-8B "reader" produced nothing Grain has ever read — it is the
dormant flavor instrument (Sprint 5.1). All audited content came from the
extraction brain, which was haiku and is now sonnet-4.5. The reader cannot
be an API model: flavor capture requires forward hooks in open weights.

## Watch item
Sonnet writes richer traces that sometimes exceed the 120-word instruction
(up to ~2900 chars in repairs). Richer memories, fewer per association
budget. Tune TRACE budget or prompt if packing feels thin.
