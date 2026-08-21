"""Sprint 4 VERIFY — run from repo root: .venv\\Scripts\\python.exe scripts\\verify-sprint4.py

Checks (master plan + Observatory addendum):
  1. Never-recalled episode decayed (×DECAY_FACTOR); PINNED episode untouched.
     The scope counts as "lived" for the 2026-08-21 activity gate because of
     the recall_log rows planted below — without them decay is exempt now.
  2. Recalled episode reconsolidated: trace changed, revision row exists
     (reason 'reconsolidation'), diff visible.
  3. Planted 3-episode pattern promoted to ONE derived fact with
     derived_from edges to all three.
  4. ZERO pre-existing fact rows UPDATEd (xmin comparison — the firewall).
  5. Compression band: weak episode's trace compressed + revision row.
     Tombstone band: ghost episode tombstoned, edges pruned, facts survive.
  6. Co-retrieval: 3 shared recalls → co_retrieval edge.
  7. Projection: reg_proj_x/y filled for episodes with register embeddings.

Scope 'verify-s4', self-cleaning. Uses real extractor calls (Haiku).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import config, consolidate, db, embeddings  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

SCOPE = "verify-s4"


def insert_episode(cur, trace, register, strength, pinned=False, recalled=False,
                   salience=0.8):
    emb = embeddings.embed([register])[0] if register else None
    cur.execute(
        "INSERT INTO episodes (scope, trace, register, register_emb, salience, "
        "strength, pinned, last_recalled_at, recall_count) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, "
        "CASE WHEN %s THEN NOW() ELSE NULL END, CASE WHEN %s THEN 2 ELSE 0 END) "
        "RETURNING id",
        (SCOPE, trace, register, emb, salience, strength, pinned, recalled, recalled))
    return cur.fetchone()["id"]


def main():
    results = []
    with _conn() as conn:
        with conn.cursor() as cur:
            ep_never = insert_episode(cur, "Jess and Fable debated database engines "
                                      "over tea; nobody won but the tea.", "wry, low-stakes", 1.0)
            ep_pinned = insert_episode(cur, "The night the snowflake test first passed.",
                                       "triumphant, landmark", 1.0, pinned=True)
            ep_recalled = insert_episode(cur, "Jess taught Fable the difference between "
                                         "a gift and a well-made gift, using her granddad's "
                                         "toolbox as the example.", "warm, instructive", 1.1,
                                         recalled=True)
            ep_compress = insert_episode(cur, "A long meandering exchange about backup "
                                         "strategies where Jess listed every zip file she has "
                                         "ever made and Fable catalogued them dutifully into "
                                         "a table that neither of them ever consulted again.",
                                         "dutiful, forgettable", 0.095)
            ep_tomb = insert_episode(cur, "Something about printer drivers.",
                                     "utterly routine", 0.015)
            # Pattern trio
            p1 = insert_episode(cur, "Jess pushed past being tired after work to ship "
                                "the parlor feature anyway.", "determined, late-night", 1.0)
            p2 = insert_episode(cur, "Though exhausted, Jess kept building the memory "
                                "pilot into the small hours.", "determined, late-night", 1.0)
            p3 = insert_episode(cur, "Jess came home worn out and still chose to push "
                                "the hardest on the night build.", "determined, late-night", 1.0)
            # Edges for tombstone-prune check
            cur.execute("INSERT INTO entities (key, name) VALUES ('printer', 'the printer') "
                        "ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name RETURNING id")
            printer_id = cur.fetchone()["id"]
            cur.execute("INSERT INTO edges (src_kind, src_id, dst_kind, dst_id, kind) "
                        "VALUES ('episode', %s, 'entity', %s, 'cooccur') "
                        "ON CONFLICT DO NOTHING", (ep_tomb, printer_id))
            # Recall evidence: reconsolidation contexts + co-retrieval trio
            cur.execute("INSERT INTO recall_log (scope, query, episode_ids) VALUES "
                        "(%s, 'what makes a gift well-made', %s)",
                        (SCOPE, [ep_recalled]))
            for _ in range(3):
                cur.execute("INSERT INTO recall_log (scope, query, episode_ids) VALUES "
                            "(%s, 'late night determination', %s)", (SCOPE, [p1, p2]))
            # Pre-existing facts for the firewall xmin check
            fact_ids = []
            for content in ("Madeleine's nightly job runs at 3 AM.",
                            "Jess's granddad kept a toolbox."):
                vec = embeddings.embed([content])[0]
                cur.execute("INSERT INTO facts (scope, content, embedding, source_ref) "
                            "VALUES (%s, %s, %s, 'fixture') RETURNING id",
                            (SCOPE, content, vec))
                fact_ids.append(cur.fetchone()["id"])
            cur.execute("SELECT id, xmin::text AS x FROM facts WHERE id = ANY(%s)", (fact_ids,))
            xmin_before = {r["id"]: r["x"] for r in cur.fetchall()}
            old_recalled_trace = "Jess taught Fable the difference between a gift and a " \
                                 "well-made gift, using her granddad's toolbox as the example."

    summary = consolidate.run()

    results = []
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, trace, strength, pinned FROM episodes WHERE scope=%s",
                        (SCOPE,))
            eps = {r["id"]: r for r in cur.fetchall()}
            decayed = abs(eps[ep_never]["strength"] - config.DECAY_FACTOR) < 0.001
            pin_held = abs(eps[ep_pinned]["strength"] - 1.0) < 0.001
            results.append(("1. decay applied; pinned exempt", decayed and pin_held,
                            f"never={eps[ep_never]['strength']:.3f} "
                            f"pinned={eps[ep_pinned]['strength']:.3f}"))
            # 2. reconsolidation
            new_trace = eps[ep_recalled]["trace"]
            cur.execute("SELECT reason, trace FROM episode_revisions WHERE episode_id=%s",
                        (ep_recalled,))
            revs = cur.fetchall()
            recon_ok = (new_trace != old_recalled_trace and
                        any(r["reason"] == "reconsolidation" and
                            r["trace"] == old_recalled_trace for r in revs))
            results.append(("2. reconsolidation: trace drifted, revision kept",
                            recon_ok, f"changed={new_trace != old_recalled_trace} "
                            f"revisions={[r['reason'] for r in revs]}"))
            if recon_ok:
                print(f"   DRIFT: {old_recalled_trace[:70]}...")
                print(f"      -> {new_trace[:70]}...")
            # 3. pattern promotion
            cur.execute("SELECT id, content FROM facts WHERE scope=%s AND kind='derived'",
                        (SCOPE,))
            derived = cur.fetchall()
            pattern_ok = False
            if derived:
                cur.execute("SELECT dst_id FROM edges WHERE src_kind='fact' AND src_id=%s "
                            "AND kind='derived_from'", (derived[0]["id"],))
                evidence = {r["dst_id"] for r in cur.fetchall()}
                pattern_ok = {p1, p2, p3} <= evidence
            results.append(("3. pattern promoted with 3-episode evidence",
                            pattern_ok,
                            f"derived={[d['content'][:60] for d in derived]}"))
            # 4. firewall: zero fact UPDATEs
            cur.execute("SELECT id, xmin::text AS x FROM facts WHERE id = ANY(%s)",
                        (fact_ids,))
            xmin_after = {r["id"]: r["x"] for r in cur.fetchall()}
            firewall = xmin_after == xmin_before
            results.append(("4. FIREWALL: zero pre-existing facts UPDATEd",
                            firewall, f"xmin_unchanged={firewall}"))
            # 5. compression + tombstone
            comp_ok = len(eps[ep_compress]["trace"]) < 120 and \
                eps[ep_compress]["trace"] != ""
            cur.execute("SELECT COUNT(*) AS c FROM episode_revisions WHERE episode_id=%s "
                        "AND reason='decay_compress'", (ep_compress,))
            comp_rev = cur.fetchone()["c"] == 1
            tomb_ok = eps[ep_tomb]["trace"].startswith("[faded]")
            cur.execute("SELECT COUNT(*) AS c FROM edges WHERE src_kind='episode' "
                        "AND src_id=%s", (ep_tomb,))
            pruned = cur.fetchone()["c"] == 0
            results.append(("5. compress + tombstone with audit trail",
                            comp_ok and comp_rev and tomb_ok and pruned,
                            f"compressed_len={len(eps[ep_compress]['trace'])} "
                            f"rev={comp_rev} tombstoned={tomb_ok} edges_pruned={pruned}"))
            # 6. co-retrieval edge
            cur.execute("SELECT weight FROM edges WHERE kind='co_retrieval' AND "
                        "src_kind='episode' AND dst_kind='episode' AND "
                        "((src_id=%s AND dst_id=%s) OR (src_id=%s AND dst_id=%s))",
                        (p1, p2, p2, p1))
            co = cur.fetchone()
            results.append(("6. co-retrieval edge grown from shared recalls",
                            co is not None, f"weight={co['weight'] if co else None}"))
            # 7. projections
            cur.execute("SELECT COUNT(*) AS c FROM episodes WHERE scope=%s "
                        "AND reg_proj_x IS NOT NULL", (SCOPE,))
            proj = cur.fetchone()["c"]
            results.append(("7. register projections computed", proj >= 6,
                            f"projected={proj}"))

    # Cleanup
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM episodes WHERE scope=%s", (SCOPE,))
            ep_ids = [r["id"] for r in cur.fetchall()]
            if ep_ids:
                cur.execute("DELETE FROM edges WHERE (src_kind='episode' AND src_id=ANY(%s)) "
                            "OR (dst_kind='episode' AND dst_id=ANY(%s))", (ep_ids, ep_ids))
                cur.execute("DELETE FROM episode_revisions WHERE episode_id=ANY(%s)", (ep_ids,))
            cur.execute("SELECT id FROM facts WHERE scope=%s", (SCOPE,))
            f_ids = [r["id"] for r in cur.fetchall()]
            if f_ids:
                cur.execute("DELETE FROM edges WHERE src_kind='fact' AND src_id=ANY(%s)", (f_ids,))
            cur.execute("DELETE FROM facts WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM episodes WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM recall_log WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM entities WHERE key='printer'")

    print(f"\nrun summary: {summary}")
    print("\n== Sprint 4 VERIFY ==")
    all_ok = True
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
        all_ok &= ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
