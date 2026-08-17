# Madeleine — Dashboard Addendum ("The Observatory")
*Paste-ready addendum to the master plan. Supersedes the dashboard bullet in Sprint 7 — Sprint 7 now ships only items (1) and (2) (Rowan client + MCP wrapper) plus the API endpoints listed under "Backend amendments" below. The dashboard becomes its own phase so it can be built against real backfilled data instead of fixtures.*

## What this is
Not an admin panel — an observatory. The point is to *see* the things the design claims exist: salience gating actually gating, memories decaying and strengthening, traces drifting under reconsolidation, and the flavor space having real geometry. Every view doubles as a verification instrument for the memory system itself.

## Locked decisions (addendum)
- Vite + React (.jsx) + Tailwind 4 via `@tailwindcss/vite`, dev port **5179**, proxy `/api` → 8011, built `dist/` served by the FastAPI StaticFiles mount (mounted last, API routes win). No component library.
- All heavy computation stays server-side. The browser never receives raw vectors — it receives 2-D projections, ranked lists, and diffs. (4096-dim floats × thousands of episodes over the wire is silly; also keeps the API surface honest.)
- Projection method: **PCA first, UMAP behind an env flag** (`PROJECTION_METHOD=pca|umap`, default pca). PCA is deterministic and dependency-light; umap-learn is optional and pinned only if the flag is flipped. Projections are computed in the nightly job and cached as columns — never live per-request.
- Read-only by default. The only mutating controls in the whole dashboard are the quarantine queue (approve/deny) and a per-episode "pin" (exempt from decay). Nothing else writes. Memory is edited by living, not by clicking.
- Reconsolidation history is append-only in its own table. The diff viewer needs old traces to exist; see DDL.

## Backend amendments (fold into the service — additive, idempotent)

### DDL additions (same boot-time idempotent pattern)
```sql
CREATE TABLE IF NOT EXISTS episode_revisions (   -- reconsolidation audit trail
  id SERIAL PRIMARY KEY,
  episode_id INT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  trace TEXT NOT NULL,                           -- the trace as it was BEFORE rewrite
  strength REAL,
  rewritten_at TIMESTAMPTZ DEFAULT NOW(),
  reason TEXT                                    -- 'reconsolidation' | 'decay_compress' | 'tombstone'
);
CREATE INDEX IF NOT EXISTS idx_revisions_ep ON episode_revisions (episode_id);

ALTER TABLE episodes ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS proj_x REAL;   -- flavor projection, nightly
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS proj_y REAL;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS reg_proj_x REAL;  -- register-embedding projection
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS reg_proj_y REAL;

CREATE TABLE IF NOT EXISTS gate_log (            -- live feed source; also great debugging
  id SERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  salience REAL,
  register TEXT,
  decision TEXT NOT NULL,                        -- 'episode' | 'facts_only' | 'quarantined' | 'skipped'
  exchange_id INT REFERENCES raw_exchanges(id),
  episode_id INT REFERENCES episodes(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Consolidation job additions
- **Before** every trace rewrite, decay-compression, or tombstone: insert the outgoing trace into `episode_revisions` with the reason. (Divergence rule: no trace may be overwritten without a revision row — the diff viewer depends on it.)
- **Projection step** (after flavor capture): PCA over all non-null `flavor` vectors → `proj_x/proj_y`; PCA over `register_emb` → `reg_proj_x/reg_proj_y`. Fit once per run over the full set, write back in batch. Until Phase-5 flavor exists, the atlas runs on register projections alone — the UI must handle `proj_x IS NULL` gracefully.
- `gate.py` writes a `gate_log` row for every decision, including `facts_only` and `skipped`.

### New/changed API endpoints (all under `/api`, all scope-filtered)
- `GET /api/stats` — counts (facts active/superseded, episodes by strength band, quarantine backlog, edges), last consolidation run summary.
- `GET /api/episodes` — paged; filters: scope, register text search, salience/strength ranges, date range, pinned, quarantined; sort by occurred_at | salience | strength | recall_count.
- `GET /api/episodes/{id}` — full dossier: trace, register, salience, strength, recall stats, linked entities + facts (via edges), revision history.
- `POST /api/episodes/{id}/pin` — toggle. `POST /api/quarantine/{id}` — body `{action: "approve"|"deny"}` (approve = un-quarantine; deny keeps dark; both logged).
- `GET /api/entities` / `GET /api/entities/{key}` — dossier: summary, fact list (active + superseded chains), episodes by recency, register mix (count by register keyword bucket), edge neighbors with weights.
- `GET /api/graph?entity={key}&hops=2` — nodes + weighted edges for the neighborhood, node kind + strength included. Cap nodes at 150, note truncation in payload.
- `GET /api/atlas?space=flavor|register` — `[{id, x, y, register, salience, strength, occurred_at}]` for all plottable episodes in scope.
- `POST /api/recall` — unchanged contract, but add `debug: true` option returning phase-1 hits, seed set, per-hop activation trace, and budget-packing decisions. The playground runs on this.
- `GET /api/timeline?bucket=week` — per-bucket episode counts, mean salience, births/tombstones.
- `GET /api/gate/feed?after_id=N` — poll endpoint for the live feed (simple polling every 3 s; no websockets — this is a local dashboard, keep it boring).
- `GET /api/consolidation/runs` — parsed run reports (the job should also write a JSON summary next to its log for this).

---

# PHASE 5 — OBSERVATORY

## Sprint 8 — Shell, stats, episode browser, entity dossiers
### RECON
Read a sibling dashboard (`E:\git\LANGGRAPH/dashboard` or Agent-Boardspace) for the Vite + Tailwind-4 setup, proxy config, and auth handling against the Basic-auth middleware. Read this addendum's endpoint list; confirm which endpoints Fable already built in Sprint 7 and list gaps before writing UI.
### BUILD
Dashboard scaffold on 5179. Left-nav shell: Overview, Episodes, Entities, Atlas, Graph, Forensics, Gate Feed, Quarantine. **Overview**: stat cards from `/api/stats`, last-consolidation summary, 30-day timeline sparkline. **Episodes**: filterable/sortable table — register shown as a colored chip (hash register text → hue, consistent everywhere), salience as a dot scale, strength as a bar that visibly shrinks as memories fade; row click → dossier drawer (trace, linked entities/facts, revision count, pin toggle). **Entities**: index + dossier page — summary, active facts with superseded-chain expander, episode list, register-mix bar, mini edge list. Empty states written for a fresh DB.
### VERIFY (do this, don't skip)
Against real backfilled data: filter episodes to one entity's key via the dossier, counts match a direct SQL check. A superseded fact chain renders oldest→newest with the active one marked. Pin an episode; confirm the API row flips and the next consolidation run skips its decay (check the run log). Auth: with `DASHBOARD_PASSWORD` set, unauthenticated requests get 401.

## Sprint 9 — Flavor atlas, graph explorer, mood search
### RECON
Read `/api/atlas` and `/api/graph` payload shapes. Check whether Phase-5 flavor vectors exist yet; if not, build everything against `space=register` and leave the space toggle wired but marked.
### BUILD
**Atlas**: full-pane scatter (SVG or canvas — pick by point count, note choice) of episode projections. Color = register hue, size = salience, opacity = strength. Hover → trace tooltip; click → dossier drawer; lasso/box-select → side list of selected episodes. Time scrubber filtering by occurred_at range — dragging it shows the memory landscape growing and fading. Space toggle: register ↔ flavor (disabled with a tooltip until flavor vectors exist). **Graph**: force-layout neighborhood from a chosen entity (2 hops default, slider to 3) — episode nodes vs entity nodes visually distinct, edge width = weight, edge kind (cooccur/co_retrieval/derived_from) distinguished; click any node to recenter or open dossier. **Mood search**: a search box that takes vibe text ("late night, a little sad, talking about family"), embeds it server-side, ranks episodes by register-embedding cosine (flavor cosine when available) — results as a ranked strip under the atlas with matched episodes highlighted in the scatter.
### VERIFY (do this, don't skip)
Atlas renders the full backfill without jank (>1k points → canvas). Two obviously different registers from real data (e.g. a build session vs a heavy conversation) visibly separate in the scatter — screenshot into the sprint report; if they don't separate, say so honestly (that's a finding about the register prompt, not a UI bug). Mood search for a known vibe surfaces the episode you'd expect, and its dot highlights. Graph view renders the Sprint-3 granddad fixture chain as a connected path.

## Sprint 10 — Forensics: reconsolidation diffs, recall debugger, live gate feed
### RECON
Read `episode_revisions` write paths in `consolidate.py` and the `debug: true` recall payload.
### BUILD
**Forensics**: reconsolidation browser — episodes with ≥1 revision, side-by-side or inline word-diff (small local diff util, no heavy dep) of each revision → next, with reason and timestamp; this is where you literally watch memory drift. Filter by reason to audit decay-compression separately. **Recall debugger**: the playground grows a debug mode — enter query (+ optional mood text), see three labeled columns: phase-1 fact hits with cosine scores, seed set, and spread results with per-hop activation values; budget-packing decisions shown as included/excluded strikethrough. This turns retrieval tuning (`SPREAD_DECAY`, thresholds, budgets) from guesswork into observation — show current env values inline, read-only. **Gate feed**: Gate Feed page polls `/api/gate/feed`, streaming rows: time, scope, decision chip, salience, register, one-line content preview *only for non-quarantined items* (quarantined rows show decision + reasons, never content — same stance as retrieval). **Quarantine**: queue page with gate reasons displayed, approve/deny, denied items collapse to a log.
### VERIFY (do this, don't skip)
Run consolidation manually; a recalled episode's rewrite appears in Forensics with a sensible diff. Recall debugger on the granddad fixture shows the car episode entering via hop-2 spread with its activation value — screenshot into the report (this is the design's acceptance test, now visible). Retain a routine exchange and a poisoned fixture while the Gate Feed is open: both rows appear within one poll cycle, the quarantined one shows no content preview. Approve then deny items in the queue; state changes verified via `/api/episodes` filters.

## Seams built ahead of need (label honestly)
- Flavor-space atlas toggle: wired, disabled until Sprint 5.1 fills vectors — "seam only" until then.
- `gate_log.decision='skipped'`: written for future sampling/rate-limit logic; nothing skips today.
- Websocket feed: not built; polling is the decision. Revisit only if the dashboard ever leaves localhost.
