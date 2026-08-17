"""Madeleine — the drop-in client for agent hosts (Rowan, Boardspace, ...).

Call shapes mirror the family's Hindsight client (retain_exchange / recall)
so a host swaps backends by import + env, not by rewrite. Degradation-safe:
every function returns ''/False/[] on failure — memory never raises into an
agent loop.

MEMORY_BACKEND selects the world:
  hindsight — legacy path (host keeps its existing client; this module inert)
  madeleine — this client, alone
  both      — parallel-run: WRITE to Madeleine too, READ still from Hindsight;
              Madeleine's answers logged for comparison. This generates the
              GATE A evidence without changing what the agent experiences.

This file is self-contained on purpose (stdlib + httpx only) so hosts can
vendor it: copy the file, set MADELEINE_URL, done.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("madeleine.client")

MADELEINE_URL = os.environ.get("MADELEINE_URL", "http://127.0.0.1:8011")
MEMORY_BACKEND = os.environ.get("MEMORY_BACKEND", "madeleine").strip().lower()
_TIMEOUT = float(os.environ.get("MADELEINE_CLIENT_TIMEOUT", "10"))
_COMPARE_LOG = os.environ.get("MADELEINE_COMPARE_LOG", "").strip()


def _post(path: str, body: dict, timeout: float | None = None) -> dict | None:
    try:
        with httpx.Client(timeout=timeout or _TIMEOUT) as c:
            r = c.post(f"{MADELEINE_URL}{path}", json=body)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("madeleine %s failed (degrading): %s", path, e)
        return None


def retain_exchange(scope: str, user_content: str, assistant_content: str | None,
                    *, user_display_name: str = "the user",
                    agent_name: str = "the agent",
                    occurred_at: str | None = None) -> bool:
    """Store one exchange (two speaker-tagged retains). Fire-and-forget on the
    server side; cheap and non-blocking here. Active in 'madeleine' AND 'both'
    modes — parallel-run writes to Madeleine while reads stay legacy."""
    if MEMORY_BACKEND == "hindsight":
        return False
    ts = occurred_at or datetime.now(timezone.utc).isoformat()
    ok = True
    if (user_content or "").strip():
        ok &= _post("/api/retain", {"scope": scope, "speaker": "user",
                                    "content": f"{user_display_name}: {user_content.strip()}",
                                    "occurred_at": ts}) is not None
    if (assistant_content or "").strip():
        ok &= _post("/api/retain", {"scope": scope, "speaker": "agent",
                                    "content": f"{agent_name}: {assistant_content.strip()}",
                                    "occurred_at": ts}) is not None
    return ok


def recall(scope: str, query: str, *, mood_text: str | None = None) -> str:
    """Rendered context block (facts + labeled impressions), '' when empty or
    down. In 'both' mode: runs and LOGS but returns '' so the agent still
    reads legacy memory — the comparison log is the deliverable."""
    if MEMORY_BACKEND == "hindsight":
        return ""
    out = _post("/api/recall", {"scope": scope, "query": (query or "").strip()[:500],
                                "mood_text": mood_text})
    if out is None:
        return ""
    block = out.get("context_block") or ""
    if MEMORY_BACKEND == "both":
        if _COMPARE_LOG:
            try:
                with open(_COMPARE_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n=== {datetime.now(timezone.utc).isoformat()} "
                            f"scope={scope} query={query[:120]!r}\n{block}\n")
            except OSError as e:
                logger.warning("compare log write failed: %s", e)
        return ""  # parallel-run: the agent still lives on legacy reads
    return block


def recall_structured(scope: str, query: str, *,
                      mood_text: str | None = None) -> dict:
    """Full structured result for hosts that render their own context.
    {'facts': [], 'associations': []} on failure."""
    if MEMORY_BACKEND == "hindsight":
        return {"facts": [], "associations": []}
    out = _post("/api/recall", {"scope": scope, "query": (query or "").strip()[:500],
                                "mood_text": mood_text})
    return out or {"facts": [], "associations": []}
