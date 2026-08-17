# DECISIONS — Madeleine
*Reverse-chronological. Records reversals too.*

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
