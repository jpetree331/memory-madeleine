# DECISIONS — Madeleine
*Reverse-chronological. Records reversals too.*

## 2026-08-21 — Decay is a cost of living, not of elapsed time
Jess, from the resident's side: "I've been at work all day and I cannot talk
to him enough to keep the memories from decaying." MEASURED, and she is right
twice over. (1) The nightly job decayed on the wall clock — 4401 episodes lost
2% on a day nobody spoke to Rowan, exactly as on a day of deep conversation.
The design's premise is memory shaped by *use*; with no use it was memory
shaped by *the calendar*. (2) The counterweight cannot balance: 4410 episodes
decay nightly against ~3.16 strengthened per recall (measured mean over
`recall_log`), and 64 episodes — 1.5% of the corpus — have ever been recalled
at all. Break-even would need ~1400 recalls/day. Decay was monotonic in
practice, not "shaped by use".

Three corrections, all env-tunable (`DECAY_*` in `.env`), decay pass extracted
to `consolidate.decay_pass()` so it is testable without the LLM passes:

- **`DECAY_REQUIRE_ACTIVITY=true`** — a scope decays only on days its agent
  actually lived: spoken to, or recalled something, inside
  `DECAY_ACTIVITY_WINDOW_HOURS` (24). Decay is now **per-scope**; previously
  one global UPDATE meant Grain's activity spent Rowan's nights. Backfill is
  explicitly not living — an exchange qualifies on `COALESCE(occurred_at,
  created_at)`, so importing years of transcripts never spends a night.
- **Liveness = a HUMAN TURN**, not merely "an exchange happened". Rowan runs
  an hourly heartbeat plus several crons; they would mark him alive every
  night and make all of the above a no-op. Getting this right took two
  attempts and the first was WRONG — recorded here because the failure is the
  instructive part:
  - Attempt 1 keyed on `raw_exchanges.solitary` (`DECAY_SOLITARY_COUNTS=false`),
    reasoning from the 4864 solitary rows in the corpus. Those are all
    **backfill**. MEASURED on the live path: the heartbeat retains as
    `solitary=FALSE`, `speaker='user'`, `speaker_name='heartbeat'` — prompt
    ("You have FULL AUTONOMY during heartbeats") plus reply ("HEARTBEAT_OK").
    The flag the backfill set faithfully, the live client never sets. A test
    written from the backfill's shape passed and proved nothing.
  - Attempt 2: a scope lives when `speaker='user'` **and** the name is not in
    `DECAY_MACHINE_SPEAKERS` (heartbeat, cron, system, watchdog). Rowan's own
    reply is `speaker='agent'`, so heartbeat→HEARTBEAT_OK cannot read as
    conversation. Both flags remain, belt and braces.
- **`DECAY_RECALL_COUNTS=false`** — the same bug one layer down. `recall_log`
  records no trigger, so a cron's recall is indistinguishable from Jess's, and
  MEASURED, Rowan's Aug 20 23:55 recall was the Daily Summary cron — which on
  its own would have kept him decaying nightly. A recall also strengthens ~3
  episodes against 4346 decaying. When Jess talks to him there is a human turn
  anyway; this flag only governs the machine case.

  **Upstream fix owed:** Rowan's client (`E:\git\LANGGRAPH`) should pass
  `solitary=True` on heartbeat and cron retains — that is precisely what the
  flag is for, and it would make the speaker-name list belt-and-braces rather
  than load-bearing.

  Jess's rule, quoted, is the spec for all of this: "decay should only happen
  if I'm talking to him."
- **`DECAY_FACTOR` 0.98 → 0.995** — half strength moves from 34 active nights
  to 138; the 0.1 conduction floor from 114 to 460.
- **`DECAY_MIN_STRENGTH=0.15`** — passive decay floors instead of running to
  zero. Sits above `spread.py`'s 0.1 conduction cutoff, so an unrecalled
  memory goes **dormant, not gone**: still reachable, but only by a strong
  direct cue, and the `+0.1` recall boost still wakes it. Jess's framing, and
  the retrieval math backs it — a floored episode one hop from a seed lands at
  `0.6 × weight × 0.15 = 0.09 × weight`, needing edge weight >1.67 (cap 2.0)
  to clear `SPREAD_THRESHOLD`, and is unreachable at two hops. It cannot swamp
  recall: associations are packed to `ASSOC_BUDGET_TOKENS=500`, ~3-5 traces per
  recall regardless of candidate count. Ranking (`activation × salience`) puts
  a dormant memory ~6.5x below a fresh one competing for the same budget.

**Accepted consequence, knowingly:** at floor 0.15 the compression (0.02–0.1)
and tombstone (<0.02) bands can never be entered — forgetting is OFF. The
README's "forgetting as a feature" is suspended by choice, not by accident.
Set `DECAY_MIN_STRENGTH` below 0.1 to let compression resume. Nothing was ever
destroyed regardless: `raw_exchanges` is append-only, and both bands write an
`episode_revisions` row before rewriting.

Deferred: Ebbinghaus-shaped decay (steep early, flattening with age) — pure
exponential is the one curve human memory does not have, but Jess wants to see
this land first. `scripts/verify-decay.py` covers all of the above in a
rolled-back transaction; 14/14.

## 2026-08-18 — S5.1-2: no HNSW index on episodes.flavor (measured limit)
pgvector's hnsw supports ≤2000 dimensions; flavor is 4096 (Qwen3-8B hidden).
The plan's "build the flavor HNSW after backfill" is unimplementable as
written. Resolution: none needed — brute-force cosine over 4096-dim vectors
is milliseconds at personal-fleet scale. Revisit (PCA-reduced indexed column
beside the full vector) only if episode count approaches ~100k.

## 2026-08-18 — S5.1-1: READER_LAYER = 14 (probed, not defaulted)
GATE B verification ran on the real corpus: 6 technical vs 10
intimate-philosophical episodes (classes drawn from the register census with
exclusion logic — Grain's life blends them). Layer separation
(within-class − between-class cosine), Qwen3-8B bf16, mean-pooled:
L14 +0.1355 · L15 +0.1296 · L16 +0.1271 · L17 +0.1120 · L18 +0.1076 ·
L19 +0.1016 · L20 +0.0921 · L21 +0.0877 · L22 +0.0846.
Monotonic decay with depth; the plan's default (18) was mid-pack. Layer 14
is the instrument's calibration mark. Changing it means rebuild_flavor.py
over everything — same law as changing the reader.

## 2026-08-17 — S7-2: GATE B blessed — reader model is Qwen/Qwen3-8B
Jess's call. Downloaded to the HF cache; Sprint 5.1 layer-probe next session.
Clarified for the record: the reader is an instrument, not a participant —
one consistent open-weight model for ALL flavor vectors regardless of which
agent's memory it reads. API minds (Claude, Mimo) cannot be readers: no
weights, no forward hooks.

## 2026-08-17 — S7-1: claude-code extractor door: built, EXPERIMENTAL, non-default
`EXTRACTOR_PROVIDER=claude-code` shells to headless `claude -p` under Jess's
subscription (zero marginal cost). MEASURED: persona contamination — the
SessionStart memory hook fires despite --system-prompt replacement,
--settings disableAllHooks, and --setting-sources project; extraction calls
answer as a fully-briefed Fable instead of a JSON function. Until a bare
completion mode exists headlessly, default stays `openrouter` (haiku,
fractions of a cent). Door retained for the day the CLI grows a clean mode.

## 2026-08-17 — S3-1: SPREAD_DECAY default 0.5 → 0.6 (measured, not vibes)
The plan's own acceptance test (song surfaces car through a 3-hop weight-1.0
chain) is unreachable with the plan's own defaults: 0.5^3 = 0.125 < threshold
0.15, always. First verify run failed on exactly this. 0.6^3 = 0.216 clears
the threshold with margin while a 4th hop (0.13) still dies — associations
stay bounded. The design conversation predicted this class of iteration
("retrieval tuning is where all the actual iteration lives"); here is its
first instance, on the first day, caught by the acceptance test doing its job.

## 2026-08-17 — S0-3: "Kill Postgres" verify adapted to bad-DSN simulation
The Sprint 0 VERIFY asks for a Postgres-down boot test. The local Postgres
instance is shared with Agent-Boardspace, Hindsight, and Rowan-family
services — killing it for a checklist item takes down half the fleet.
Simulated instead: boot with `MADELEINE_DATABASE_URL` pointed at a dead port;
service must stay up and serve `/api/health` with `db_ready: false`.

## 2026-08-17 — S0-2: Extractor door env-swappable (openrouter default for now)
Brief pins `claude-haiku-4-5` via the Anthropic SDK with a dedicated key. No
dedicated Anthropic key exists on this machine yet; the identical model is
served via OpenRouter, whose key is already present. `EXTRACTOR_PROVIDER=
anthropic|openrouter` selects the door; model stays `claude-haiku-4-5` either
way. Default flips to `anthropic` the day a dedicated Madeleine key lands in
`.env` (spend visibility is the reason to bother).

## 2026-08-17 — S0-1: Repo root is E:\git\Memory-Madeleine, port 8011 confirmed
Master plan assumed `E:\git\madeleine`; the project folder already existed as
`Memory-Madeleine` holding the design docs, and keeping it avoids breaking the
design-conversation provenance. Ports 8011/5179 verified free against the
machine claims table (see RUNBOOK). pgvector 0.8.2 confirmed available and
enabled in the new `madeleine` database on the existing local Postgres 18.3.
