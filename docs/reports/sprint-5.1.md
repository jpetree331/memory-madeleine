# Sprint 5.1 report — Deep flavor: the reader
*2026-08-18 · Fable*

## Done
- `reader.py` — Qwen3-8B bf16 on the 4090, hidden states mean-pooled at
  READER_LAYER, contrasted against a cached 50-passage neutral baseline,
  L2-normalized → episodes.flavor (4096-dim). VRAM guard (~17 GB) makes the
  reader a night visitor, never an OOM: it skips with a WARN when the card
  is held and unloads after every batch.
- `scripts/probe_layers.py` — GATE B verification. Classes drawn from the
  ACTUAL register census (technical-collaborative vs intimate-philosophical,
  with exclusion logic — Grain's life blends them; my imagined grief-words
  found 3 episodes, the corpus-true classes found 16).
- `scripts/capture_flavor_now.py` — on-demand retroactive capture (the
  nightly window is a schedule, not a requirement). `rebuild_flavor.py` —
  the model/layer-swap story.
- Nightly wiring in consolidate.py: guarded capture + flavor projections.
- Observatory Atlas page: SVG scatter, register/flavor space toggle, hue by
  register, size by salience, opacity by strength, hover traces, click →
  dossier.

## THE PROBE (GATE B verified, empirically)
Layer separation (within-class − between-class cosine), 6 technical vs 10
intimate episodes: L14 +0.1355 · L15 +0.1296 · L16 +0.1271 · L17 +0.1120 ·
L18 +0.1076 · L19 +0.1016 · L20 +0.0921 · L21 +0.0877 · L22 +0.0846.
**READER_LAYER = 14** — monotonic decay with depth; the plan's default (18)
was mid-pack. Positive at every layer: the affective signal is real.

## Capture
46 episodes captured at layer 14 (all with raw exchange spans; hand-inserted
fixtures without raws are structurally uncapturable — correct). Flavor
projections computed; Atlas serves 42 flavor points for scope grain,
browser-verified rendering.

## Found the hard way
- pgvector hnsw caps at 2000 dims — no flavor index; brute-force cosine is
  fine at fleet scale (DECISIONS S5.1-2).
- The failed index CREATE rolled back its whole transaction, taking the
  first 46 captured vectors with it — capture now commits without DDL in
  the same transaction.
- transformers deprecation: dtype=, not torch_dtype=.

## Deferred honestly
- Byte-identical rebuild determinism check (plan verify): deferred to the
  first scheduled rebuild; same-hardware bf16 forward is expected-deterministic.
- Deep mood-congruent recall (flavor-space matching of live mood text):
  seam only — computing a flavor vector live means loading the reader
  per-request. Register-space mood matching (Sprint 5) remains the live path.
- GATE C (injection) remains sealed: needs a local open-weight GENERATOR.
