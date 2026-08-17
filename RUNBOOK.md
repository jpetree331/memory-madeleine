# RUNBOOK — Madeleine

## Ports
| Port | What | Confirmed free |
|------|------|----------------|
| 8011 | Madeleine API (FastAPI, loopback) | 2026-08-17 |
| 5179 | Dashboard Vite dev server | 2026-08-17 |

Machine port claims at time of writing: 8000 LANGGRAPH, 8001 gaming-ai,
8002 CG-Discord-Bot, 8005 supabase-kong, 8007 Agent-Boardspace, 8010 voice
bot, 8888/9999 Hindsight, 5433/6543 supabase Postgres, 5173/5174/5178
frontends, 3000 mission-control (Docker), 9119 hermes dashboard (Docker).

## Start / stop / restart
- Start (foreground, dev): `.venv\Scripts\python.exe -m uvicorn src.agent.api:app --port 8011` from repo root
- Start (ops): `madeleine.cmd` (PYTHONUTF8=1, logs append to `data\logs\service.log`)
- Scheduled Task registration: Sprint 7 (deployment sprint); until then run manually
- Stop: kill the listening process — `Get-NetTCPConnection -LocalPort 8011 -State Listen` → `Stop-Process`

## Env knobs
See `.env.example` — every knob commented there. The live `.env` is never committed.

## Known failure modes → fixes
- **Postgres down at boot** → service stays up, `/api/health` reports `db_ready: false`, DDL retries on next restart. Fix: start Postgres, restart Madeleine.
- **Extractor provider down** → retains still write `raw_exchanges`; extraction queues. No agent-facing errors by design.

## Do-not-disturb inventory
- Database `madeleine` on the shared local Postgres instance — other DBs on the same instance (agent-boardspace, fable, Rowan's) are load-bearing for other services. Never DROP anything outside `madeleine`.
- `E:\git\Hindsight` — never touch on disk, ever (house rule).
