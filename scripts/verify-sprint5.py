"""Sprint 5 VERIFY — run from repo root: .venv\\Scripts\\python.exe scripts\\verify-sprint5.py

The plan's check: two fixture episodes touching the same entity, one
grief-adjacent, one playful. The same query with opposite mood_text values
flips their order. State-dependent recall — sad states surface sad memories.

Scope 'verify-s5', hand-inserted, self-cleaning. No LLM calls (embeddings only).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, embeddings, memory  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

SCOPE = "verify-s5"


def main():
    # Ensure current schema (lesson S1/S4: scripts see the DB, not the service)
    db.setup_schema()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO entities (key, name, kind) VALUES "
                        "('the-lake-house', 'the lake house', 'place') "
                        "ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name RETURNING id")
            lake = cur.fetchone()["id"]
            eps = {}
            for tag, trace, register in (
                ("grief", "The last quiet visit to the lake house after the funeral; "
                          "packing boxes nobody wanted to open.",
                 "heavy, grieving, hushed"),
                ("play", "Cannonball contest off the lake house dock; the referee "
                         "was a golden retriever and everyone lost.",
                 "playful, sunlit, laughing"),
            ):
                emb = embeddings.embed([register])[0]
                cur.execute(
                    "INSERT INTO episodes (scope, trace, register, register_emb, "
                    "salience, strength) VALUES (%s, %s, %s, %s, 0.8, 1.0) RETURNING id",
                    (SCOPE, trace, register, emb))
                eps[tag] = cur.fetchone()["id"]
                cur.execute(
                    "INSERT INTO edges (src_kind, src_id, dst_kind, dst_id, kind, weight) "
                    "VALUES ('episode', %s, 'entity', %s, 'cooccur', 1.0) "
                    "ON CONFLICT DO NOTHING", (eps[tag], lake))

    query = "thinking about the lake house"
    sad = memory.recall_full(SCOPE, query,
                             mood_text="quiet and sorrowful tonight, missing people")
    glad = memory.recall_full(SCOPE, query,
                              mood_text="bright silly energy, ready to laugh")

    def order(out):
        return [a["episode_id"] for a in out["associations"]]

    sad_order, glad_order = order(sad), order(glad)
    sad_first = sad_order and sad_order[0] == eps["grief"]
    glad_first = glad_order and glad_order[0] == eps["play"]
    flipped = sad_first and glad_first

    results = [
        ("1. mood flips the order (grief-first sad, play-first glad)", flipped,
         f"sad_order={sad_order} glad_order={glad_order} "
         f"grief_id={eps['grief']} play_id={eps['play']}"),
        ("2. mood_similarity surfaced in results",
         all("mood_similarity" in a for a in sad["associations"]),
         "similarity present on association items"),
        ("3. moodless recall still works",
         len(order(memory.recall_full(SCOPE, query))) == 2,
         "both episodes surface without mood"),
    ]

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM episodes WHERE scope=%s", (SCOPE,))
            ep_ids = [r["id"] for r in cur.fetchall()]
            if ep_ids:
                cur.execute("DELETE FROM edges WHERE src_kind='episode' AND src_id=ANY(%s)",
                            (ep_ids,))
            cur.execute("DELETE FROM recall_log WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM episodes WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM entities WHERE key='the-lake-house'")

    print("\n== Sprint 5 VERIFY ==")
    all_ok = True
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
        all_ok &= ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
