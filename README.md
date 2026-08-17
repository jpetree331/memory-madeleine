# Madeleine

A memory system for LLM agents that remembers three things per exchange, not one:

- **Facts** — atomic, embedded, versioned. Truth. Never rewritten, only superseded.
- **Episodes** — salience-gated traces of conversations: the arc, the turns, what it
  felt like. Linked to every entity they touched through a co-occurrence graph.
- **Flavor** — the register of the moment: a cheap text tag at write time, and a deep
  activation vector from a local reader model, captured nightly.

Retrieval is two-phase: semantic RAG over facts, then **spreading activation** through
the episode graph — so asking about the song can surface the red car, the way it does
for people. Named for Proust's madeleine: the cookie that proved memory is triggered
by texture, not lookup.

Designed by Jess with web-Fable; built by Fable (Claude Code). See `BUILD_BRIEF.md`
for the architecture contract, `madeleine_master_plan.md` for the sprint plan,
`DECISIONS.md` for the choices and reversals, and `docs/reports/` for what actually
happened each sprint.

## Run
```
.venv\Scripts\python.exe -m uvicorn src.agent.api:app --port 8011
```
Health: `GET http://127.0.0.1:8011/api/health`
