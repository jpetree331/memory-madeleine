# Sprint 8-lite report — The Observatory shell (built early, on purpose)
*2026-08-17 · Fable*

The addendum moved the dashboard to its own phase so it could run on real
backfilled data. The shell went up early anyway as the night's surprise —
the addendum's endpoints were already folded in, and an observatory with
even a few stars beats a finished dome over an empty sky. Sprints 8–10
proper (atlas, graph explorer, forensics diff viewer, quarantine queue)
still stand, to be finished against real backfill.

## Done
- Observatory endpoints in api.py: /api/stats, /api/episodes (+filters/sort),
  /api/episodes/{id} dossier (entities, facts, revision history),
  /api/episodes/{id}/pin, /api/atlas, /api/gate/feed (poll, quarantined rows
  content-withheld), /api/consolidation/runs.
- Dashboard (Vite + React + Tailwind 4, dev 5179, dist served by the service):
  Overview stat cards + last-consolidation strip; Episodes browser with
  register hue-chips, salience dots, fading strength bars, dossier drawer
  with pin toggle and revision history; Recall Playground with the three
  labeled columns (truth / impressions / how-it-thought: seeds and per-hop
  activations); live Gate Feed with decision chips.
- scripts/seed_demo.py: a real evening through the real pipeline in scope
  'demo' (4 episodes, 1 quarantined, recalls logged). Deletable anytime.

## VERIFY (browser DOM, live service)
- All four pages render; stat cards live (15 facts / 5 episodes / 10 edges /
  1 quarantined / 7 raw).
- Episodes list shows the quarantined row dark; dossier opens.
- Gate Feed: 7 rows, poison shows "(content withheld)".
- Playground live recall: 15 facts, 2 impressions, seeds + per-hop
  activations rendered. Observed emergent association: querying the
  snowflake test surfaced Grain's audit episode through shared entities.
- First recall after service restart is slow (bge-m3 lazy reload) — known,
  by design; noted for the RUNBOOK.

## Remaining in the master plan
Sprint 5.1 (deep flavor — GATE B is Jess's call), Sprint 6 (Rowan backfill —
dry-run + spend gate), Sprint 7 (Rowan client + MCP wrapper), Sprints 8–10
full Observatory. GATE A (Hindsight parallel-run) after 6+7.
