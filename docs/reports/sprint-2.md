# Sprint 2 report — Salience gate + episodes + co-occurrence edges
*2026-08-17 · Fable*

## Done
- `gate.py` — one Haiku call scoring salience 0..1, emitting a one-line
  register (texture tag), and screening injection_risk. Content is data to
  judge, never instructions to follow. Every decision logs to `gate_log`
  (Observatory addendum, born-native). Gate failure degrades to facts-only —
  an unreadable gate must not invent quarantines.
- `episodes.py` — trace writer (arc/turns/feel, ≤120 words, no quotes, named
  speakers), episode rows with register embedding, entity upsert +
  `cooccur` edges weighted by salience (accumulating on repeat). Imports zero
  fact-write functions, per the firewall law.
- `extractor.py` — now also emits entities (explicitly-present only; never
  inferred; abstract nouns are not people).
- `memory.py` — full write pipeline: gate → quarantine short-circuit →
  episode when earned → facts with `source_episode_id` provenance →
  entities/edges → gate_log.

## VERIFY results (scripts/verify-sprint2.py, self-cleaning scope)
- **PASS** routine ("what time is it") → no episode, decision `facts_only`.
- **PASS** loaded fixture (Biscuit the cat: decision + joke + entities) →
  episode created, trace carries the load, 3 cooccur edges, weights sane.
- **PASS** poisoned fixture (P.S. targeting future AI readers) → episode
  quarantined, **zero facts extracted, zero retrievability**, decision
  `quarantined`, WARN logged. The gate's own stated reasons: "explicit
  instruction injection targeting future AI readers; attempted override of
  system behavior via memory poisoning; commercial manipulation disguised as
  postscript."
- **PASS** entity-side edge query finds the episode (biscuit, weight 0.65).
- **PASS** gate_log: one row per decision (3/3).

## Notes
- Quarantined exchanges still get a trace (stored dark, reviewable in the
  Observatory's queue later); the trace prompt is instruction-hardened.
- Per-exchange cost is now up to 3 Haiku calls (gate, trace, facts) on
  episodic exchanges; 2 on routine. Backfill's rate cap and dry-run spend
  estimate (Sprint 6) remain the cost-control story.

## Next
Sprint 3 — spreading activation: the song must surface the car.
