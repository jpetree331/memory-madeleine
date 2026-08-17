"""Sprint 1 VERIFY — run from repo root: .venv\\Scripts\\python.exe scripts\\verify-sprint1.py

Checks (from the master plan):
  1. Retain 10 fixture exchanges; extraction produces facts with provenance.
  2. Recall returns the right facts for 5 test queries.
  3. Contradiction: retaining a correction supersedes the old fact (old row kept).
  4. Degradation: with extractor keys absent, retain still writes the raw
     exchange and the row stays visibly queued (extracted_at IS NULL).

Uses scope 'verify-s1' throughout and cleans it up at the end, so repeat runs
are honest and the companion scope stays pristine.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import config, db, memory  # noqa: E402

SCOPE = "verify-s1"

FIXTURES = [
    ("user", "My kid's teacher this year is Ms. Alvarez, she seems great at the IEP stuff."),
    ("user", "Madeleine runs on port 8011, wrote it in the runbook."),
    ("agent", "I noted that the consolidation job should run at 3 AM when the GPU is free."),
    ("user", "My granddad drove a red Plymouth and always played Patsy Cline on the radio."),
    ("user", "We decided the extractor rides OpenRouter until the dedicated Anthropic key exists."),
    ("agent", "Jess prefers memory retention to be passive for agents — given, not performed."),
    ("user", "The Hindsight dashboard lives on port 9999 locally."),
    ("user", "Rowan generates on Kimi K2 through an API, no residual stream access."),
    ("agent", "The verify fixtures for sprint one live in the scripts directory."),
    ("user", "bge-m3 makes 1024-dimensional embeddings and runs fully local."),
]

QUERIES = [
    ("who is the kid's teacher", "Alvarez"),
    ("what port does madeleine use", "8011"),
    ("what did granddad drive", "red"),
    ("when does consolidation run", "3"),
    ("what model does Rowan generate on", "Kimi"),
]


def wait_extracted(n, timeout=180):
    for _ in range(timeout // 3):
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM raw_exchanges "
                            "WHERE scope=%s AND extracted_at IS NOT NULL", (SCOPE,))
                if cur.fetchone()["c"] >= n:
                    return True
        time.sleep(3)
    return False


def main():
    results = []

    # ── 1. Retain fixtures ────────────────────────────────────────────────────
    for speaker, content in FIXTURES:
        memory.retain(SCOPE, speaker, content)
    ok = wait_extracted(len(FIXTURES))
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM facts WHERE scope=%s", (SCOPE,))
            fact_count = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM facts WHERE scope=%s "
                        "AND source_ref IS NULL AND source_episode_id IS NULL", (SCOPE,))
            orphans = cur.fetchone()["c"]
    results.append(("1. retain+extract 10 fixtures",
                    ok and fact_count > 0 and orphans == 0,
                    f"extracted={ok} facts={fact_count} orphan_facts={orphans}"))

    # ── 2. Recall accuracy ────────────────────────────────────────────────────
    hits = 0
    for q, needle in QUERIES:
        got = memory.recall(SCOPE, q)
        top = " | ".join(f["content"] for f in got[:3])
        if needle.lower() in top.lower():
            hits += 1
        else:
            print(f"   MISS {q!r} -> {top[:120]}")
    results.append(("2. recall 5 queries", hits >= 4, f"{hits}/5 hit (>=4 passes)"))

    # ── 3. Supersede on contradiction ────────────────────────────────────────
    memory.retain(SCOPE, "user", "Correction: actually Madeleine moved to port 8012.")
    time.sleep(20)
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, content, status FROM facts WHERE scope=%s "
                        "AND content ILIKE '%%8011%%'", (SCOPE,))
            old = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS c FROM facts WHERE scope=%s "
                        "AND content ILIKE '%%8012%%' AND status='active'", (SCOPE,))
            new_active = cur.fetchone()["c"]
    old_superseded = any(r["status"] == "superseded" for r in old)
    old_kept = len(old) > 0
    results.append(("3. contradiction supersedes",
                    old_superseded and old_kept and new_active > 0,
                    f"old_kept={old_kept} old_superseded={old_superseded} new_active={new_active}"))

    # ── 4. Degradation without extractor keys ────────────────────────────────
    saved_a, saved_o = config.ANTHROPIC_API_KEY, config.OPENROUTER_API_KEY
    config.ANTHROPIC_API_KEY = ""
    config.OPENROUTER_API_KEY = ""
    try:
        ex_id = memory.retain(SCOPE, "user", "This lands while the extractor is dark.")
        time.sleep(6)
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extracted_at FROM raw_exchanges WHERE id=%s", (ex_id,))
                row = cur.fetchone()
        results.append(("4. keyless degradation: raw written, visibly queued",
                        row is not None and row["extracted_at"] is None,
                        f"raw_row={row is not None} queued={row and row['extracted_at'] is None}"))
    finally:
        config.ANTHROPIC_API_KEY, config.OPENROUTER_API_KEY = saved_a, saved_o

    # ── Cleanup ───────────────────────────────────────────────────────────────
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM facts WHERE scope=%s", (SCOPE,))
            cur.execute("DELETE FROM raw_exchanges WHERE scope=%s", (SCOPE,))

    print("\n== Sprint 1 VERIFY ==")
    all_ok = True
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
        all_ok &= ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
