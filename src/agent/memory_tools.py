"""Madeleine — memory capability exposed as agent-facing tools (family
signature pairing: memory.py implements, memory_tools.py exposes).

Sprint 1: thin degradation-safe wrappers; the FastMCP wrapper (Sprint 7)
and Rowan client build on these shapes. Wrappers return ''/[] on failure,
never raise into an agent loop.
"""
from __future__ import annotations

import logging

from . import memory

logger = logging.getLogger("madeleine.memory_tools")


def retain_tool(scope: str, speaker: str, content: str,
                occurred_at: str | None = None) -> bool:
    try:
        memory.retain(scope, speaker, content, occurred_at=occurred_at)
        return True
    except Exception as e:
        logger.error("retain_tool degraded: %s", e)
        return False


def recall_tool(scope: str, query: str) -> list[dict]:
    try:
        return memory.recall(scope, query)
    except Exception as e:
        logger.error("recall_tool degraded: %s", e)
        return []
