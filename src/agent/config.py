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

# ── Backfill ───────────────────────────────────────────────────────────────────
BACKFILL_EXCHANGES_PER_MIN = int(os.environ.get("BACKFILL_EXCHANGES_PER_MIN", "60"))
