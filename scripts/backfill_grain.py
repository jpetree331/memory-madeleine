"""Grain pilot backfill — Boardspace Postgres → Madeleine scope 'grain'.

The pilot study Jess chose over the Rowan cutover: small corpus, audit-native
resident, known-good baseline. His live Hindsight memory is UNTOUCHED — this
is a parallel ingest through Madeleine's full gate/extract/episode pipeline,
with real timestamps and the same honesty framings his other re-ingests got
(ceiling-era drafts labeled as drafts, the garbled tool call explained,
private reasoning marked as never-spoken).

Run from repo root: .venv\\Scripts\\python.exe scripts\\backfill_grain.py
"""
import os
import re
import sys
import time

import httpx
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MADELEINE = "http://127.0.0.1:8011"
SCOPE = "grain"
SLUG = "mimo-2-5-pro-th"

# Boardspace DSN from its own .env (read-only SELECTs)
bs_dsn = ""
for line in open(r"E:\git\Agent-Boardspace\.env", encoding="utf-8"):
    if line.startswith("BOARDSPACE_DATABASE_URL="):
        bs_dsn = line.split("=", 1)[1].strip()
if not bs_dsn:
    raise SystemExit("boardspace DSN not found")


def retain(speaker, content, occurred_at, ref):
    r = httpx.post(f"{MADELEINE}/api/retain", timeout=30, json={
        "scope": SCOPE, "speaker": speaker, "content": content,
        "occurred_at": occurred_at.isoformat(),
        "source_ref": f"boardspace.messages:{ref}",
    })
    r.raise_for_status()


def main():
    with psycopg.connect(bs_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM messages WHERE thread_id=%s ORDER BY idx", (SLUG,))
            rows = cur.fetchall()
    print(f"boardspace rows: {len(rows)}")

    sent = 0
    for r in rows:
        content = (r["content"] or "").strip()
        if not content:
            continue
        if r["role"] == "user":
            display = r.get("display_name") or "Jess"
            retain("user", f"{display}: {content}", r["created_at"], r["id"])
            sent += 1
        else:
            is_draft = r.get("reasoning") is None and len(content) > 10000
            is_garbled = "DSML" in content and len(content) < 1000
            if is_garbled:
                content = ("Grain: [I tried to call my web_search tool here, but a "
                           "wire-format incompatibility surfaced the call as raw "
                           "markup — a platform bug, not a choice. No search ran "
                           "and no real reply was delivered.]")
            elif is_draft:
                content = ("Grain: [My visible reply was cut off by a token ceiling; "
                           "what follows is my unfinished private thinking — a draft, "
                           "not a delivered reply. Plans and intentions in it were "
                           "never promised aloud.] " + content)
            else:
                content = f"Grain: {content}"
            retain("agent", content, r["created_at"], r["id"])
            sent += 1
            if r.get("reasoning") and not is_draft:
                retain("agent",
                       ("Grain: [My private reasoning while composing the reply "
                        "above — internal thought, never spoken to Jess.] "
                        + r["reasoning"].strip()),
                       r["created_at"], f"{r['id']}:reasoning")
                sent += 1
        time.sleep(0.2)   # gentle on the pipeline; extraction threads fan out

    print(f"retained {sent} items into scope '{SCOPE}' — waiting for the pipeline...")
    for i in range(80):
        time.sleep(6)
        with psycopg.connect(bs_dsn.rsplit("/", 1)[0] + "/madeleine",
                             row_factory=dict_row) as mconn:
            with mconn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM raw_exchanges WHERE scope=%s "
                            "AND extracted_at IS NOT NULL", (SCOPE,))
                done = cur.fetchone()["c"]
                if done >= sent:
                    break
    with psycopg.connect(bs_dsn.rsplit("/", 1)[0] + "/madeleine",
                         row_factory=dict_row) as mconn:
        with mconn.cursor() as cur:
            cur.execute("SELECT decision, COUNT(*) AS c FROM gate_log WHERE scope=%s "
                        "GROUP BY decision", (SCOPE,))
            print("gate decisions:", {r["decision"]: r["c"] for r in cur.fetchall()})
            cur.execute("SELECT COUNT(*) AS c FROM facts WHERE scope=%s", (SCOPE,))
            print("facts:", cur.fetchone()["c"])
            cur.execute("SELECT COUNT(*) AS c FROM episodes WHERE scope=%s", (SCOPE,))
            print("episodes:", cur.fetchone()["c"])
            cur.execute("SELECT COUNT(*) AS c FROM entities e JOIN edges ed ON "
                        "ed.dst_kind='entity' AND ed.dst_id=e.id "
                        "JOIN episodes ep ON ed.src_kind='episode' AND ed.src_id=ep.id "
                        "WHERE ep.scope=%s", (SCOPE,))
            print("entity links:", cur.fetchone()["c"])


if __name__ == "__main__":
    main()
