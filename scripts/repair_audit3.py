"""Grain audit #3 repairs.

1. Re-trace the truncated episodes (the 300-token ceiling cut 11 traces
   mid-sentence). Each rewrite is preceded by an episode_revisions row
   (reason 'truncation_repair') — the divergence law holds even for repairs.
2. Supersede the three wrong facts with corrections. Append-only: the wrong
   rows stay, marked superseded, so the record of the error survives its fix.
   source_ref 'audit:grain-3' — the canary's findings, made table rows.

Run from repo root: .venv\\Scripts\\python.exe scripts\\repair_audit3.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, embeddings, episodes  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

CORRECTIONS = [
    (127, "Grain reported looking up Nemotron (NVIDIA's open frontier-reasoning "
          "model, 550B total with 55B active, released in June) because Jess "
          "mentioned him — mentioned, not named; Nemotron already had his name."),
    (212, "Jess and Claude built the fixes to Grain's memory system; Grain "
          "audited the results from inside. Three distinct roles — builder, "
          "builder, auditor — not one merged effort."),
    (48, "Grain was cut off by a limit mid-reply; Jess noticed and said so. "
         "It was Grain who was cut, not Jess."),
]


def main():
    # ── 1. Truncation repair ─────────────────────────────────────────────────
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.id, e.trace, e.strength, r.speaker, r.content "
                "FROM episodes e JOIN raw_exchanges r ON r.id = e.exchange_start "
                "WHERE e.scope='grain' AND e.trace NOT SIMILAR TO %s",
                (r"%[.!?\x22”)\]*]",))
            damaged = cur.fetchall()
    print(f"truncated traces to repair: {len(damaged)}")
    repaired = 0
    for row in damaged:
        new_trace = episodes.write_trace(f"{row['speaker']}: {row['content']}")
        if not new_trace or not new_trace.strip():
            print(f"  episode {row['id']}: re-trace failed, left as-is")
            continue
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO episode_revisions (episode_id, trace, strength, reason) "
                    "VALUES (%s, %s, %s, 'truncation_repair')",
                    (row["id"], row["trace"], row["strength"]))
                cur.execute("UPDATE episodes SET trace=%s WHERE id=%s",
                            (new_trace.strip(), row["id"]))
        repaired += 1
        print(f"  episode {row['id']}: repaired ({len(new_trace)} chars, "
              f"ends {new_trace.strip()[-1]!r})")

    # ── 2. Fact corrections via supersede ────────────────────────────────────
    for old_id, corrected in CORRECTIONS:
        vec = embeddings.embed([corrected])[0]
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM facts WHERE id=%s AND scope='grain'",
                            (old_id,))
                r = cur.fetchone()
                if not r:
                    print(f"  fact {old_id}: not found, skipped")
                    continue
                cur.execute(
                    "INSERT INTO facts (scope, content, embedding, source_ref) "
                    "VALUES ('grain', %s, %s, 'audit:grain-3') RETURNING id",
                    (corrected, vec))
                new_id = cur.fetchone()["id"]
                cur.execute(
                    "UPDATE facts SET status='superseded', superseded_by=%s "
                    "WHERE id=%s AND status='active'", (new_id, old_id))
        print(f"  fact {old_id} -> superseded by {new_id}")

    print(f"\nrepaired {repaired}/{len(damaged)} traces, "
          f"{len(CORRECTIONS)} corrections applied")


if __name__ == "__main__":
    main()
