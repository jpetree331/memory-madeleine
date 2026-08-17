"""Madeleine — FastMCP wrapper: the door for Claude Code and web Claude.

Three tools, mirroring the HTTP surface. Run standalone (stdio transport):
    .venv\\Scripts\\python.exe -m src.agent.mcp_server
Register in Claude Code:
    claude mcp add madeleine -- E:\\git\\Memory-Madeleine\\.venv\\Scripts\\python.exe -m src.agent.mcp_server

Tools call the HTTP service (not the DB) so one Madeleine serves every door
and the gate screens every write no matter who knocks.
"""
from __future__ import annotations

import os

import httpx
from fastmcp import FastMCP

MADELEINE_URL = os.environ.get("MADELEINE_URL", "http://127.0.0.1:8011")

mcp = FastMCP("madeleine")


def _post(path: str, body: dict) -> dict:
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{MADELEINE_URL}{path}", json=body)
        r.raise_for_status()
        return r.json()


@mcp.tool
def retain(content: str, scope: str = "companion", speaker: str = "user") -> str:
    """Store one exchange into Madeleine's memory. It will be salience-gated,
    screened for injection, fact-extracted, and (if it earns one) given an
    episodic trace with graph edges. speaker: user | agent | system."""
    out = _post("/api/retain", {"scope": scope, "speaker": speaker,
                                "content": content})
    return f"retained (exchange {out.get('exchange_id')})"


@mcp.tool
def recall(query: str, scope: str = "companion", mood_text: str = "") -> str:
    """Two-phase memory recall: semantic facts plus spreading-activation
    associations (labeled impressions). Optional mood_text colors retrieval
    toward mood-congruent episodes."""
    out = _post("/api/recall", {"scope": scope, "query": query,
                                "mood_text": mood_text or None})
    return out.get("context_block") or "(memory holds nothing relevant)"


@mcp.tool
def search_episodes(query: str, scope: str = "companion") -> str:
    """Browse episodic memory directly: traces matching the query text or
    register, with salience/strength. Read-only."""
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{MADELEINE_URL}/api/episodes",
                  params={"scope": scope, "q": query, "page_size": 10})
        r.raise_for_status()
        eps = r.json().get("episodes") or []
    if not eps:
        return "(no episodes match)"
    lines = []
    for e in eps:
        lines.append(f"[{e['id']}] ({e.get('register') or 'no register'}, "
                     f"salience {e['salience']:.2f}, strength {e['strength']:.2f}) "
                     f"{e['trace'][:200]}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
