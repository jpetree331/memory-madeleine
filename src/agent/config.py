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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3").strip()
READER_MODEL = os.environ.get("READER_MODEL", "Qwen/Qwen3-8B").strip()
READER_LAYER = int(os.environ.get("READER_LAYER", "18"))

# ── Nightly job ────────────────────────────────────────────────────────────────
NIGHTLY_HOUR = int(os.environ.get("NIGHTLY_HOUR", "3"))
FLAVOR_BATCH = int(os.environ.get("FLAVOR_BATCH", "200"))

# ── Backfill ───────────────────────────────────────────────────────────────────
BACKFILL_EXCHANGES_PER_MIN = int(os.environ.get("BACKFILL_EXCHANGES_PER_MIN", "60"))
