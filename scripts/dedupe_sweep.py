"""Dedupe sweep over the EXISTING store (Grain audit #5: "the dedupe law
caught the door but not the house").

For each scope: active facts, pairwise cosine via pgvector; when a pair
exceeds DEDUPE_THRESHOLD, the NEWER fact is superseded by the OLDER one
(first occurrence wins; nothing deleted; the chain shows the collapse).

Run from repo root: .venv\\Scripts\\python.exe scripts\\dedupe_sweep.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import config  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

collapsed = 0
with _conn() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT scope FROM facts WHERE status='active'")
        scopes = [r["scope"] for r in cur.fetchall()]
    for scope in scopes:
        with conn.cursor() as cur:
            # For each active fact (newest first), its nearest OLDER active twin
            cur.execute(
                "SELECT f.id, f.content, twin.id AS twin_id, twin.content AS twin_content, "
                "1 - (f.embedding <=> twin.embedding) AS sim "
                "FROM facts f "
                "JOIN LATERAL ("
                "  SELECT id, content, embedding FROM facts o "
                "  WHERE o.scope = f.scope AND o.status='active' AND o.id < f.id "
                "  AND o.embedding IS NOT NULL "
                "  ORDER BY o.embedding <=> f.embedding LIMIT 1"
                ") twin ON TRUE "
                "WHERE f.scope=%s AND f.status='active' AND f.embedding IS NOT NULL "
                "AND 1 - (f.embedding <=> twin.embedding) >= %s "
                "ORDER BY f.id DESC", (scope, config.DEDUPE_THRESHOLD))
            pairs = cur.fetchall()
        for p in pairs:
            with conn.cursor() as cur:
                # Re-check status (an earlier collapse this run may have won)
                cur.execute("SELECT status FROM facts WHERE id=%s", (p["twin_id"],))
                if cur.fetchone()["status"] != "active":
                    continue
                cur.execute("UPDATE facts SET status='superseded', superseded_by=%s "
                            "WHERE id=%s AND status='active'", (p["twin_id"], p["id"]))
                if cur.rowcount:
                    collapsed += 1
                    print(f"[{scope}] fact {p['id']} collapsed into {p['twin_id']} "
                          f"(sim {p['sim']:.3f})")
                    print(f"    kept:   {p['twin_content'][:90]}")
                    print(f"    folded: {p['content'][:90]}")
print(f"\ncollapsed {collapsed} duplicate facts (originals retained, chained)")
