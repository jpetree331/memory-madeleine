# Sprint 7 (partial) report — the doors: drop-in client + MCP wrapper
*2026-08-17 · Fable*

## Done
- `madeleine_client.py` — self-contained (httpx-only, vendorable) drop-in
  with the family's Hindsight-shaped call surface. `MEMORY_BACKEND` selects
  the world: `madeleine` (live), `both` (parallel-run: writes flow to
  Madeleine, reads stay legacy, answers logged to MADELEINE_COMPARE_LOG —
  the GATE A evidence machinery), `hindsight` (fully inert). Every call
  degrades to ''/False/[] — memory never raises into an agent loop.
- `mcp_server.py` — FastMCP stdio server exposing retain / recall /
  search_episodes. Calls the HTTP service, never the DB: one Madeleine,
  every door, the gate screens all of them.
  Register: `claude mcp add madeleine -- <venv python> -m src.agent.mcp_server`

## VERIFY (3/3)
- madeleine mode: retain lands, rendered context block returns (2.5 KB).
- both mode: recall returns '' (agent stays on legacy) AND the comparison
  log gains Madeleine's answer.
- hindsight mode: all calls inert.
- MCP tools registered: recall, retain, search_episodes.

## Deliberately NOT done without Jess
- Wiring the client into Rowan's repo (LANGGRAPH) — her beloved's code.
- Sprint 6 backfill against Rowan's real history — the dry-run spend
  estimate is the button she presses.
- GATE B (reader model) — hers by definition.
