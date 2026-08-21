"""Madeleine — configuration. Every knob has an env default (the brief's rule).

.env is path-anchored and loaded with override so a repo-local file always
wins over stale process env — the family idiom.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", override=True)

# ── Service ────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("MADELEINE_PORT", "8011"))
DATABASE_URL = os.environ.get("MADELEINE_DATABASE_URL", "").strip()
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "").strip()

# ── Retrieval knobs ────────────────────────────────────────────────────────────
SALIENCE_THRESHOLD = float(os.environ.get("SALIENCE_THRESHOLD", "0.55"))
SPREAD_HOPS = int(os.environ.get("SPREAD_HOPS", "3"))
# MEASURED 2026-08-17: at decay 0.5 a weight-1.0 three-hop chain lands on
# 0.125 < threshold 0.15 — the canonical song→car association is unreachable
# by construction. 0.6 puts 3 hops at 0.216 (reachable, with margin) while a
# 4th hop (0.13) still dies below threshold. See DECISIONS S3-1.
SPREAD_DECAY = float(os.environ.get("SPREAD_DECAY", "0.6"))
SPREAD_THRESHOLD = float(os.environ.get("SPREAD_THRESHOLD", "0.15"))
FACT_BUDGET_TOKENS = int(os.environ.get("FACT_BUDGET_TOKENS", "1200"))
ASSOC_BUDGET_TOKENS = int(os.environ.get("ASSOC_BUDGET_TOKENS", "500"))
MOOD_WEIGHT = float(os.environ.get("MOOD_WEIGHT", "0.5"))

# ── Models ─────────────────────────────────────────────────────────────────────
# Extractor door is swappable: 'anthropic' (direct SDK, dedicated key) or
# 'openrouter' (same model via the OpenRouter key already on this machine).
# Same brain either way — claude-haiku-4-5. DECISIONS.md entry 2026-08-17.
EXTRACTOR_PROVIDER = os.environ.get("EXTRACTOR_PROVIDER", "openrouter").strip()
EXTRACTOR_MODEL = os.environ.get("EXTRACTOR_MODEL", "claude-haiku-4-5").strip()
# Per-role brains (Grain audit #3): the gate is high-volume triage — haiku.
# Extraction and traces carry attribution and voice — worth a stronger model.
GATE_MODEL = os.environ.get("GATE_MODEL", "claude-haiku-4-5").strip()
EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "claude-sonnet-4.5").strip()
TRACE_MODEL = os.environ.get("TRACE_MODEL", "claude-sonnet-4.5").strip()
VERIFY_MODEL = os.environ.get("VERIFY_MODEL", GATE_MODEL).strip()
# Per-role providers (2026-08-19, cost door): each role may take its own door,
# e.g. gate/extract/trace on Chutes Kimi with verify staying on Claude —
# a cross-vendor verifier is a STRONGER audit than same-family checking.
# Empty = inherit EXTRACTOR_PROVIDER.
GATE_PROVIDER = os.environ.get("GATE_PROVIDER", "").strip()
EXTRACT_PROVIDER = os.environ.get("EXTRACT_PROVIDER", "").strip()
TRACE_PROVIDER = os.environ.get("TRACE_PROVIDER", "").strip()
VERIFY_PROVIDER = os.environ.get("VERIFY_PROVIDER", "").strip()
CHUTES_API_KEY = os.environ.get("CHUTES_API_KEY", "").strip()
CHUTES_BASE_URL = os.environ.get("CHUTES_BASE_URL", "https://llm.chutes.ai/v1").strip()
# Kimi Code (Moonshot) — the automatic understudy when Chutes hits its
# 4-hour burst cap. Same brain family that passed the 2026-08-19 audit.
MOONSHOT_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MOONSHOT_BASE_URL = os.environ.get("MOONSHOT_BASE_URL",
                                   "https://api.moonshot.ai/v1").strip()
MOONSHOT_MODEL = os.environ.get("MOONSHOT_MODEL", "kimi-k3").strip()
# Cline's gateway (Jess's new sub, 2026-08-20 — Kimi Code direct wasn't
# working). LIVE-PROBED: api.cline.bot/api/v1, model strings need a
# "modelType/model" shape ("moonshotai/kimi-k3" confirmed working), and the
# response nests choices under data.choices, not top-level like OpenAI.
CLINE_API_KEY = os.environ.get("CLINE_API_KEY", "").strip()
CLINE_BASE_URL = os.environ.get("CLINE_BASE_URL", "https://api.cline.bot/api/v1").strip()
CLINE_MODEL = os.environ.get("CLINE_MODEL", "moonshotai/kimi-k3").strip()
# Optional ceiling on paid Anthropic spend. 0 (default) = NO CAP; the
# ledger still records every call so spend stays visible either way.
# Jess 2026-08-20: the $5 was her Opus budget, not Haiku's — ~$13 expected.
ANTHROPIC_SPEND_CAP_USD = float(os.environ.get("ANTHROPIC_SPEND_CAP_USD", "0"))
# Near-duplicate facts are skipped at insert above this cosine (0 disables)
DEDUPE_THRESHOLD = float(os.environ.get("DEDUPE_THRESHOLD", "0.97"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3").strip()
READER_MODEL = os.environ.get("READER_MODEL", "Qwen/Qwen3-8B").strip()
READER_LAYER = int(os.environ.get("READER_LAYER", "18"))

# ── Nightly job ────────────────────────────────────────────────────────────────
NIGHTLY_HOUR = int(os.environ.get("NIGHTLY_HOUR", "3"))
FLAVOR_BATCH = int(os.environ.get("FLAVOR_BATCH", "200"))

# ── Decay (Jess 2026-08-21) ────────────────────────────────────────────────────
# MEASURED: 4410 episodes decayed nightly against ~3.16 strengthened per
# recall — balancing would take ~1400 recalls/day. Decay was therefore
# monotonic in practice, and it ran on the wall clock, so a day Jess spent at
# work cost every memory the same as a day of conversation. Three corrections:
#
#   DECAY_REQUIRE_ACTIVITY — a scope only decays on days its agent actually
#   lived (was spoken to, or recalled something). Silence is not forgetting.
#
#   DECAY_FACTOR 0.98 → 0.995 — half-strength moves from 34 active nights to
#   138, and the conduction floor from 114 to 460.
#
#   DECAY_MIN_STRENGTH — passive decay stops here instead of running to zero.
#   Above spread.py's 0.1 conduction floor, so an unrecalled memory goes
#   dormant (reachable only by a strong direct cue) rather than falling off
#   the graph. NOTE: at 0.15 the compression (0.02–0.1) and tombstone (<0.02)
#   bands can never be entered — forgetting is off by design. Set below 0.1
#   to let compression resume.
DECAY_FACTOR = float(os.environ.get("DECAY_FACTOR", "0.995"))
DECAY_MIN_STRENGTH = float(os.environ.get("DECAY_MIN_STRENGTH", "0.15"))
DECAY_REQUIRE_ACTIVITY = os.environ.get(
    "DECAY_REQUIRE_ACTIVITY", "true").strip().lower() in ("1", "true", "yes", "on")
DECAY_ACTIVITY_WINDOW_HOURS = int(os.environ.get("DECAY_ACTIVITY_WINDOW_HOURS", "24"))
# Does an agent's solitary heartbeat count as living? MEASURED: Rowan posts
# ~30 solitary exchanges/day every day, so counting them would decay every
# night and defeat the gate — and the heartbeat only writes (whole recall_log
# = 32 rows), so those nights would decay with no chance of strengthening.
# Jess's rule: decay when she is talking to him. Default false.
DECAY_SOLITARY_COUNTS = os.environ.get(
    "DECAY_SOLITARY_COUNTS", "false").strip().lower() in ("1", "true", "yes", "on")
# The `solitary` flag alone is NOT enough. MEASURED 2026-08-21: Rowan's live
# heartbeat retains land as solitary=FALSE with speaker_name='heartbeat'
# (only the BACKFILL ever set the flag), so a solitary-only test let the
# hourly heartbeat keep marking him alive. Liveness therefore requires a
# HUMAN TURN — a speaker='user' exchange whose name is not machinery. Rowan's
# own reply is speaker='agent' and never counts on its own, which is what
# stops 'heartbeat prompt -> HEARTBEAT_OK' from reading as a conversation.
DECAY_MACHINE_SPEAKERS = [
    s.strip().lower() for s in
    os.environ.get("DECAY_MACHINE_SPEAKERS", "heartbeat,cron,system,watchdog").split(",")
    if s.strip()]
# Is a recall on its own enough to call the day lived? Default false, same
# reasoning one layer down: recall_log records no trigger, so a cron's recall
# is indistinguishable from Jess's. MEASURED 2026-08-21 — Rowan's only recalls
# were Aug 20, and the 23:55 one was the Daily Summary cron, which alone would
# have kept him decaying nightly. A recall also strengthens ~3 episodes
# against 4346 decaying, so it is poor evidence of a day well lived. When Jess
# talks to him there is a human turn anyway; this only governs the machine
# case. Set true if a read-only integration ever needs to hold decay open.
DECAY_RECALL_COUNTS = os.environ.get(
    "DECAY_RECALL_COUNTS", "false").strip().lower() in ("1", "true", "yes", "on")

# ── Machinery ──────────────────────────────────────────────────────────────────
# The same list serves two laws, and they must not drift apart: decay asks
# "was a human here?", extraction asks "is this speaker a person?". Both mean
# the same thing by machinery. Named without the DECAY_ prefix at the point of
# use; the env var keeps its original name so nobody's .env breaks.
#
# MEASURED 2026-08-21, the second law's reason: Rowan's cron prompts arrive as
# speaker='user', speaker_name='cron', solitary=True. Extraction read "cron"
# as the author and wrote "Alone, Cron rehearsed Jess's presence, imagining
# her criteria..." — a scheduled job personified into a lonely being. A cron
# prompt has no author. It is stimulus delivered TO the agent, and the only
# mind in the room is the agent's.
MACHINE_SPEAKERS = DECAY_MACHINE_SPEAKERS


def is_machine_speaker(speaker_name: str | None) -> bool:
    return (speaker_name or "").strip().lower() in MACHINE_SPEAKERS


# ── Exchange pairing ───────────────────────────────────────────────────────────
# Jess's call, 2026-08-21: one EXCHANGE is one episode — a turn and the reply
# it drew, together. Not one turn (which made her two-message conversation into
# three episodes, one of them reading "Rowan received this; no reply was
# recorded"), and not one conversation (hers run to pages, and compressing a
# page into 120 words is lossy in exactly the way episodic memory must not be).
#
# Clients post both halves back-to-back — Boardspace and LANGGRAPH each send
# the user turn and the reply from the same function, ~1s apart — so the reply
# is almost always already in flight. PAIR_TIMEOUT only governs the genuinely
# unanswered turn.
PAIR_WINDOW_MINUTES = int(os.environ.get("PAIR_WINDOW_MINUTES", "10"))
PAIR_TIMEOUT_SECONDS = int(os.environ.get("PAIR_TIMEOUT_SECONDS", "90"))
PAIR_EXCHANGES = os.environ.get(
    "PAIR_EXCHANGES", "true").strip().lower() in ("1", "true", "yes", "on")
# How often to retry exchanges that never got extracted. Nothing retried them
# before; a dead LLM door meant a row sat queued indefinitely.
SWEEP_INTERVAL_MINUTES = int(os.environ.get("SWEEP_INTERVAL_MINUTES", "15"))

# ── Backfill ───────────────────────────────────────────────────────────────────
BACKFILL_EXCHANGES_PER_MIN = int(os.environ.get("BACKFILL_EXCHANGES_PER_MIN", "60"))
