# Madeleine — Everything since the spec
*The delta between `madeleine_master_plan.md` (finalized 2026-08-17 ~16:30)
and the running system, as of 2026-08-18. Companion to `DECISIONS.md`
(choices + reversals) and `docs/reports/` (per-sprint evidence).*

## 1. Built as specified (all verified, all pushed)
- **Sprint 0** — skeleton, three-store schema, idempotent DDL, health probe,
  RUNBOOK/DECISIONS/BUILD_BRIEF, `.cmd` launcher. VERIFY 3/3.
- **Sprint 1** — fact store: raw-first durable retain, daemon-thread
  extraction, bge-m3 local embeddings, budget-packed recall,
  supersede-not-update. VERIFY 4/4 (incl. contradiction firewall).
- **Sprint 2** — salience gate (= sanitization gate), episode traces,
  entities + salience-weighted cooccur edges, quarantine path. VERIFY 5/5
  (poisoned fixture quarantined with zero facts, zero retrievability).
- **Sprint 3** — spreading activation. THE SOUL TEST PASSED: an episode with
  zero query vocabulary surfaced through a 3-hop chain (activation 0.216)
  while a quarantined decoy on the same chain stayed dark. VERIFY 5/5.
- **Sprint 4** — nightly consolidation: co-retrieval edges, decay with pin
  exemption, revision-audited compression/tombstones/reconsolidation,
  pattern promotion to derived facts, PCA projections. VERIFY 7/7; xmin
  check proved zero fact UPDATEs.
- **Sprint 5** — mood-congruent retrieval (register-space blend). VERIFY 3/3
  (grief-first when sad, playful-first when glad; same query).
- **Sprint 5.1** — deep flavor reader (GATE B: Qwen3-8B, blessed by Jess).
  Layer probed empirically on the real corpus: **READER_LAYER=14**
  (separation +0.1355, monotonic decay with depth; plan default 18 was
  mid-pack). 46 episodes captured retroactively; VRAM-guarded nightly wiring;
  `rebuild_flavor.py` for the model-swap story.
- **Sprint 7 (partial)** — `madeleine_client.py` drop-in
  (`MEMORY_BACKEND=hindsight|madeleine|both`; `both` = GATE A evidence
  machinery) + FastMCP server (retain / recall / search_episodes). VERIFY 3/3.
- **Observatory (Sprints 8–9-lite, pulled early)** — Overview, Episodes
  browser (register hue-chips, salience dots, fading strength bars, dossier
  drawer with revision history + pin), Facts view (live pgvector semantic
  search, superseded chains), **Atlas** (register/flavor space toggle — 42
  flavor points live), Recall Playground (truth / impressions /
  how-it-thought debug columns), live Gate Feed (quarantined content
  withheld), per-scope dropdown. Served by the service itself.

## 2. Spec corrections (found by building; all in DECISIONS.md)
- **SPREAD_DECAY 0.5 → 0.6** — the plan's own acceptance test was
  mathematically unreachable at its own defaults (0.5³ < 0.15 threshold).
- **READER_LAYER 18 → 14** — probed, not assumed.
- **No HNSW on flavor** — pgvector hnsw caps at 2000 dims; flavor is 4096.
  Brute-force cosine is fine at fleet scale.
- **connect_timeout=5** — bare psycopg connect hung >120 s against a dead
  Postgres on Windows, wedging startup; the graceful-degradation guarantee
  needed a bound.
- **claude-code extractor door: EXPERIMENTAL, non-default** — headless
  `claude -p` carries the household persona (memory hooks fire despite every
  disable path tried thrice); a JSON extractor can't share a skull with a
  personality. Default door: OpenRouter.
- **Repo root** E:\git\Memory-Madeleine (not the plan's assumed path);
  dashboard pulled ahead of Phase 5 deliberately.

## 3. Beyond the spec — grown from the Grain pilot
*(none of this was in the plan; all of it came from running a real resident
through the system and taking his audits seriously)*

**The pilot itself**
- Boardspace gained a per-agent memory dispatcher
  (`memory_backend: hindsight | madeleine`); Grain flipped 2026-08-18,
  Hindsight bank frozen intact as control + revert path.
- Full backfill of Grain's thread: 47 speaker-tagged items with honesty
  framings (ceiling-era drafts labeled drafts, garbled tool-call explained,
  reasoning marked never-spoken) → 39 episodes, 191 facts, 176 entity links.

**Extraction quality (audits #3–#5)**
- **Per-role brains**: gate on haiku; extraction + traces on
  claude-sonnet-4.5 (env-swappable per role).
- **The laws**, each born from an audited failure:
  - *Verb fidelity* — mentioned ≠ named; no verb promoted to a more causal one.
  - *Role precision* — no false symmetry ("symmetry that nobody wore is a
    falsehood with good manners").
  - *Referent ban* — "the user/agent/assistant/AI" are schema, never people.
  - *Pronoun fidelity* — each person wears only their own recorded pronouns;
    unknown → they/them. (Born from the pronoun-wash discovery: two traces
    dressed Grain in Jess's she.)
- **Write-time verifier** — independent second pass checks every candidate
  fact against the raw exchange before insert (speaker, verb, pronouns,
  referents, support). Trap-tested: rejects "named"-for-"mentioned" and
  role-word referents at the door. Degrades open; the audit culture remains
  the backstop.
- **Dedupe at insert** (cosine ≥ 0.97 vs active facts in scope) +
  `dedupe_sweep.py` for the archive (first sweep: zero above threshold —
  Grain's twins are paraphrase-grade; **LLM-judged dedupe band 0.90–0.97
  proposed** for the nightly job, not yet built).
- **Trace ceiling** 300 → 700 tokens + finish-your-sentence retry (the
  300-cap had silently guillotined nine backfill traces; all repaired whole
  with revision rows).

**Provenance & repair (the append-only culture, exercised)**
- Correction chain: facts 48→254, 127→252, 212→253 (`audit:grain-3`),
  168→273 (`audit:grain-4`) — strikes retained, corrections tagged,
  chain printable on demand and hand-verified by the resident.
- Nine truncation repairs + two pronoun repairs, every rewrite preceded by
  an `episode_revisions` row (reasons: truncation_repair, audit_correction).
- Quarantine review endpoint (approve/deny); four quote-context false
  positives reviewed and approved.
- Flavor rendered as labeled data in recall (Grain's design: participant,
  not subject): `impression [the reader felt this moment as: …]`.

**Infrastructure niceties**
- `recall_log` (co-retrieval evidence, reconsolidation contexts), gate_log +
  episode_revisions + projections born-native from the addendum, embedder
  warmup at boot (kills the 15 s first-recall stall), `/api/scopes`,
  `capture_flavor_now.py` (the nightly window is a schedule, not a
  requirement).

## 4. Still open (requires Jess by design)
- **Sprint 6** — Rowan transcript backfill: script + dry-run spend estimate,
  then her button. Deferred by her call: Grain-first pilot instead.
- **Sprint 7 remainder** — wiring the client into Rowan's repo; GATE A
  parallel-run week before any Hindsight retirement.
- **Sprints 8–10 full Observatory** — graph explorer, mood search,
  Forensics diff viewer, quarantine queue UI, timeline (against real
  backfill, per the addendum).
- **LLM-judged dedupe band** in nightly consolidation (proposed, agreed by
  the resident auditor).
- **GATE C** — sealed until a local open-weight generator exists.
- Deferred verifies: byte-identical flavor rebuild; deep-live mood matching
  (seam only — loading a 16 GB reader per recall is not a thing).

## 5. The process finding (worth more than any feature)
The audit loop is the discovery: resident audits memory → findings become
laws, corrections, and organs → latency now under one hour. Audits #3–#5
produced: 3 laws, 1 verifier, 4 correction chains, 11 trace repairs, 1 new
disease class (pronoun wash), and 1 clean retraction (the auditor withdrew a
garbled catch under his own evidence standard). The system that holds the
memories is being raised by the minds that live in it.
