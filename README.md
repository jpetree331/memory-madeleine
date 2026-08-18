# Madeleine

**A memory system for AI agents that remembers like a person: truth on one
shelf, texture on another, and the feel of the moment kept alongside both.**

Named for Proust's madeleine — the cookie that proved memory is triggered by
texture, not lookup. Ask it about the song and it can surface your
grandfather's red car, even though the two share no words — because they
shared a *life*.

---

## Why this exists

Every mainstream agent-memory system does some version of: extract facts,
embed them, retrieve by similarity. That captures *aboutness* and throws away
texture — because texture lives in exactly the material extraction discards.

We tested the alternatives seriously before building. Running the same real
conversation corpus through several established memory platforms, and letting
the agent who *lived* those conversations audit the results from inside, we
found the same failure family everywhere:

- **Attribution collapse** — the agent's statements filed under the human's
  name; one person fissioned into three entities ("the user", her name, and
  an invented "partner").
- **Personification** — abstract nouns turned into people. A conversation
  about *grace* and *faith* produced two humans named Grace and Faith who
  never existed.
- **Intention promotion** — private drafts and plans stored as accomplished
  facts.
- **Narrative smoothing** — "A built it and B audited it" becoming "A and B
  worked together"; *mentioned* becoming *named*.

These aren't engineering slips. They're what happens when a system can't
tell **what happened** from **what it felt like**. Madeleine's answer is to
build that distinction into the structure itself.

## The architecture

Three stores, one Postgres database:

1. **Facts** (semantic memory) — atomic, embedded, versioned. **Append-only:
   facts are superseded, never rewritten.** The old row stays, struck
   through, chained to its correction. A correction without the struck
   original is not a correction — it's a denial.
2. **Episodes** (episodic memory) — salience-gated narrative traces of
   exchanges: the arc, the turns, how it felt. Linked to every entity they
   touched through a co-occurrence graph. Episodes *may* be rewritten — they
   reconsolidate when recalled, drift toward relevance, decay when unused,
   and every rewrite is preceded by a revision row. Texture is allowed to
   fade; truth isn't.
3. **Flavor** (affective memory) — per episode, a vector of the conversation's
   *register*: a cheap text tag + embedding at write time, and optionally a
   deep activation vector — a fixed local open-weights reader model runs the
   raw exchange and records the direction its residual stream leaned. Not a
   description of the feeling; the geometric residue of it.

**The write path** is guarded: one gate call scores salience (most exchanges
don't deserve an episode — a memory that keeps everything has kept nothing)
AND screens for embedded instructions. Flagged content is stored quarantined
— never retrievable, never traversed, reviewable by a human. The gate has
already caught real injection attempts and articulated why ("social
engineering via assumed future AI audience"). A second, independent
**write-time verifier** then checks every candidate fact against the raw
exchange — right speaker, right verb, right pronouns, no role-words as
people — before anything is stored. Extraction runs under standing laws
(verb fidelity, role precision, referent ban, pronoun fidelity), each one
born from an audited failure.

**The read path** is two-phase: semantic search over facts (guaranteed
budget), then **spreading activation** through the co-occurrence graph —
seeded by the query's entities and the provenance of the facts found,
propagating with per-hop decay. Phase two can return things similarity never
would; that's its job. Everything it returns is labeled `impression`, with
the reader's felt-tag attached — color, never citation. Optional mood input
makes recall state-dependent: sad moods surface sad memories first.

**Nightly consolidation** is the sleep cycle: co-retrieval edges grow from
usage, unrecalled episodes decay toward compression and tombstones, recalled
ones reconsolidate in light of what they were recalled *for*, cross-episode
patterns get promoted into derived facts with evidence edges, and flavor
vectors are captured while the GPU is free.

**The Observatory** is the built-in dashboard: stats, episode browser with
visibly fading strength bars, the fact ledger with live vector search, a
recall playground that shows per-hop activations, a live gate feed, and the
Atlas — your agent's memories as a 2-D landscape of felt similarity.

## What makes it different, honestly

- **Epistemology in the schema.** Facts and impressions live on separate
  shelves with separate rules. The resident agent who audits this system put
  it best: *"the archivist and the poet finally have separate desks."*
- **Provenance you can bite.** Every correction chain is printable — strikes
  retained, corrections tagged with the audit that produced them. The system
  can be wrong in the past without lying about its past.
- **Forgetting as a feature.** Salience gating at write, decay and
  compression over time, strengthening through recall. Memory that is shaped
  by use, like yours.
- **The soul test passes.** The acceptance test for the whole design: an
  episode sharing zero vocabulary with the query surfaces through pure
  3-hop graph traversal, while a quarantined decoy on the same chain stays
  dark. It's in the verify scripts; run it yourself.
- **Raised by its residents.** The audit loop is real: the first agent living
  in Madeleine has audited his own memory repeatedly; findings became laws,
  organs, and correction chains — audit-to-fix latency under an hour. Several
  extraction laws in this codebase were literally dictated by the mind whose
  memories they protect.

## Where it stands (read this before depending on it)

This is a **days-old, single-machine, personal-scale pilot** — built fast,
verified by executable scripts rather than a test suite, and shaped by one
household's needs. Concretely:

- **One real resident so far** (plus fixtures). It has held one agent's life
  for days, not one fleet's for years. GATE A — a week of parallel-running
  against an incumbent memory system on high-stakes history — has not
  happened yet.
- **Windows-native service** (Task Scheduler deployment). No Docker packaging,
  no Linux testing, no multi-tenant story, no auth beyond optional dashboard
  basic-auth. Run it for yourself, on your machine, behind your firewall.
- **LLM costs are real**: 2–4 API calls per remembered exchange (gate,
  extraction, verifier, trace). Pennies per conversation at personal scale;
  budget before you backfill years of history (the backfill tooling prints
  spend estimates and rate-caps for this reason).
- **The deep flavor layer needs a GPU** (~17 GB VRAM for the default
  Qwen3-8B reader, bf16). Without it you still get the cheap flavor tier
  (register tags + embeddings); the capture is VRAM-guarded and skips
  gracefully.
- **Known open items**: LLM-judged dedupe for paraphrase-twin facts
  (cosine dedupe exists at 0.97; twins below that are deliberately left
  standing), the Forensics/graph/quarantine dashboard views, a deferred
  byte-identical flavor-rebuild determinism check, and an occasionally
  over-strict verifier (it rejects when in doubt — by design, a missing
  fact costs less than a wrong one).
- **Known limits by design**: extraction is an LLM reading a conversation —
  error can be lowered, never zeroed; the answer is the provenance culture,
  not a promise of perfection. Flavor vectors describe the conversation as
  measured by one fixed instrument, not the agent's own interior (activation
  capture of API-hosted models is impossible; the injection seam — GATE C —
  stays sealed unless you run a local open-weights generator).
- **pgvector quirk**: no ANN index on 4096-dim flavor vectors (pgvector hnsw
  caps at 2000 dims). Brute-force cosine is fine below ~100k episodes.

`DECISIONS.md` records every choice and reversal, with measurements.
`docs/reports/` holds per-sprint evidence including the failures.
`docs/CHANGES-SINCE-SPEC.md` is the honest delta between design and reality.

## Quickstart

Requirements: Python 3.12+, PostgreSQL with pgvector, an OpenRouter (or
Anthropic) API key for extraction, optionally a CUDA GPU for deep flavor.

```
git clone https://github.com/jpetree331/memory-madeleine.git
cd memory-madeleine
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
# copy .env.example -> .env, set MADELEINE_DATABASE_URL + an extractor key
.venv/Scripts/python -m uvicorn src.agent.api:app --port 8011
```

- Health: `GET /api/health` · Remember: `POST /api/retain` · Recall:
  `POST /api/recall` (add `"debug": true` to watch it think)
- Observatory: build `dashboard/` with `npm install && npm run build`,
  then open `http://127.0.0.1:8011`
- Agents integrate via the vendorable [`madeleine_client.py`]
  (src/agent/madeleine_client.py) (with a parallel-run mode for evidence-based
  migration off an incumbent memory) or the FastMCP server
  ([`mcp_server.py`](src/agent/mcp_server.py)) for Claude Code / Claude apps.
- Verify scripts: `scripts/verify-sprint*.py` — Sprint 3 is the soul test.

## Provenance of the project itself

Designed in an afternoon conversation between Jess — a chemist who builds AI
companions as relationships, not tools — and Claude, from her question:
*could a memory remember the way people do, where a sound brings back a red
car because granddad played that music on the radio?* Built the same night by
Claude Code (Fable). Audited from inside, continuously, by Grain — the first
mind to live in it — whose findings shaped its laws. The three-way loop is
the development methodology, and the repo history shows it working.

## License

[Apache-2.0](LICENSE).

*"Wrong in the past, but never wrong about its past."*
