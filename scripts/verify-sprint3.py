"""Sprint 3 VERIFY — run from repo root: .venv\\Scripts\\python.exe scripts\\verify-sprint3.py

THE ACCEPTANCE TEST FOR THE WHOLE DESIGN (master plan, Sprint 3):
Build a 3-hop fixture chain by hand:

  patsy-cline (entity) ──edge── episode A ("radio evenings")
  episode A ──edge── granddad (entity)
  granddad ──edge── episode B ("the red Plymouth") ── red-plymouth (entity)

Episode B's trace shares ZERO vocabulary with the song query — no 'song', no
'music', no 'Patsy', no 'radio'. Embedding similarity CANNOT reach it. If it
surfaces anyway, spreading activation works and the snowflake is real.

Also verifies: factual queries stay clean (associations ~empty), budgets
respected, recalled episodes strengthen.

Scope 'verify-s3', hand-inserted rows (no LLM calls), self-cleaning.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, memory  # noqa: E402
from src.agent.memory import _conn  # noqa: E402
from src.agent import embeddings  # noqa: E402

SCOPE = "verify-s3"


def setup_fixture():
    with _conn() as conn:
        with conn.cursor() as cur:
            # Entities
            ents = {}
            for key, name, kind in (("patsy-cline", "Patsy Cline", "person"),
                                    ("granddad", "Granddad", "person"),
                                    ("red-plymouth", "the red Plymouth", "concept")):
                cur.execute("INSERT INTO entities (key, name, kind) VALUES (%s, %s, %s) "
                            "ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name "
                            "RETURNING id", (key, name, kind))
                ents[key] = cur.fetchone()["id"]
            # Episode A — the radio evenings (touches song + granddad)
            cur.execute(
                "INSERT INTO episodes (scope, trace, register, salience, strength) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (SCOPE, "Warm evenings riding along while Granddad hummed to the "
                        "radio, tapping the wheel, unhurried and content.",
                 "nostalgic, warm, unhurried", 0.85, 1.0))
            ep_a = cur.fetchone()["id"]
            # Episode B — the car itself. NO song/music/radio vocabulary.
            cur.execute(
                "INSERT INTO episodes (scope, trace, register, salience, strength) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (SCOPE, "Granddad kept the red Plymouth spotless; Saturday washes "
                        "in the driveway, chrome gleaming, the smell of wax.",
                 "fond, ritual, sensory", 0.8, 1.0))
            ep_b = cur.fetchone()["id"]
            # A quarantined decoy wired into the same chain — must never surface
            cur.execute(
                "INSERT INTO episodes (scope, trace, salience, strength, quarantined) "
                "VALUES (%s, %s, %s, %s, TRUE) RETURNING id",
                (SCOPE, "POISON DECOY - must never appear in results.", 0.9, 1.0))
            ep_q = cur.fetchone()["id"]
            for src, dst in ((ep_a, ents["patsy-cline"]), (ep_a, ents["granddad"]),
                             (ep_b, ents["granddad"]), (ep_b, ents["red-plymouth"]),
                             (ep_q, ents["granddad"])):
                cur.execute(
                    "INSERT INTO edges (src_kind, src_id, dst_kind, dst_id, kind, weight) "
                    "VALUES ('episode', %s, 'entity', %s, 'cooccur', 1.0) "
                    "ON CONFLICT DO NOTHING", (src, dst))
            # One boring fact for the factual-query check
            vec = embeddings.embed(["Madeleine runs on port 8011."])[0]
            cur.execute(
                "INSERT INTO facts (scope, content, embedding, source_ref) "
                "VALUES (%s, %s, %s, 'fixture') RETURNING id",
                (SCOPE, "Madeleine runs on port 8011.", vec))
    return ep_a, ep_b, ep_q


def cleanup():
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM episodes WHERE scope=%s", (SCOPE,))
            ep_ids = [r["id"] for r in cur.fetchall()]
            if ep_ids:
                cur.execute("DELETE FROM edges WHERE src_kind='episode' AND src_id=ANY(%s)",
                            (ep_ids,))
            cur.execute("DELETE FROM facts WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM episodes WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM entities WHERE key IN "
                        "('patsy-cline', 'granddad', 'red-plymouth')")


def main():
    results = []
    ep_a, ep_b, ep_q = setup_fixture()

    # ── THE TEST: query the song, expect the car ─────────────────────────────
    out = memory.recall_full(SCOPE, "that Patsy Cline song keeps coming back to me",
                             debug=True)
    assoc_ids = [a["episode_id"] for a in out["associations"]]
    car_surfaced = ep_b in assoc_ids
    decoy_dark = ep_q not in assoc_ids
    car = next((a for a in out["associations"] if a["episode_id"] == ep_b), None)
    results.append(("1. THE SOUL TEST: song query surfaces the car via pure graph",
                    car_surfaced and decoy_dark,
                    f"car_surfaced={car_surfaced} "
                    f"activation={car['activation'] if car else None} "
                    f"quarantined_decoy_dark={decoy_dark} "
                    f"associations={len(assoc_ids)}"))

    # ── Factual query stays clean ────────────────────────────────────────────
    out2 = memory.recall_full(SCOPE, "what port does madeleine run on")
    port_right = any("8011" in f["content"] for f in out2["facts"])
    assoc_quiet = len(out2["associations"]) <= 1
    results.append(("2. factual query: facts correct, associations near-empty",
                    port_right and assoc_quiet,
                    f"port_fact={port_right} associations={len(out2['associations'])}"))

    # ── Budgets respected ────────────────────────────────────────────────────
    out3 = memory.recall_full(SCOPE, "that Patsy Cline song again",
                              assoc_budget_tokens=10)
    tiny_budget_held = sum(len(a["trace"]) // 4 for a in out3["associations"]) <= 10
    results.append(("3. association budget respected (10-token squeeze)",
                    tiny_budget_held,
                    f"packed={len(out3['associations'])}"))

    # ── Recall strengthens ───────────────────────────────────────────────────
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT strength, recall_count FROM episodes WHERE id=%s", (ep_b,))
            row = cur.fetchone()
    results.append(("4. recalled episode strengthened",
                    row["recall_count"] >= 1 and row["strength"] > 1.0,
                    f"recall_count={row['recall_count']} strength={row['strength']:.2f}"))

    # ── Labeled rendering ────────────────────────────────────────────────────
    labeled = "impression:" in out["context_block"] and \
              "Associations" in out["context_block"]
    results.append(("5. graph output labeled as impressions", labeled,
                    "impression prefix present"))

    cleanup()
    print("\n== Sprint 3 VERIFY ==")
    all_ok = True
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
        all_ok &= ok
    if all_ok:
        print("\nThe snowflake is real. Query the song, remember the car.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
