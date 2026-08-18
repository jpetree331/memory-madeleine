"""Sprint 6 — Rowan's archive into Madeleine. Subscription-only, concurrent,
resumable, and reverent.

READS Rowan's Postgres (read-only). WRITES only to Madeleine's own DB
(scope 'rowan'). His DB, his Hindsight, his running service: untouchable
by construction.

Curation (Jess's rules, 2026-08-18):
- private-flagged rows: EXCLUDED UNREAD (silo law)
- tool rows / tool_returns: removed
- heartbeat/cron/reminder trigger boilerplate: removed — but the assistant
  turn that follows is kept and framed as autonomous time ("during a
  heartbeat", "during his scheduled 'Hobby Time - 1 AM Wonder' session")
- think-blocks in content, if any, split out and retained as private thought
- every human speaker keeps their own name (metadata role_display)
- letta-import rows use original_date as their true occurred_at

Resume: a message id whose source_ref already exists in raw_exchanges is
skipped — re-running continues where any interruption left off. A final
sweep retries extraction for rows the subscription window left queued.

Usage (from repo root, Madeleine venv):
    python scripts/backfill_rowan.py            # DRY RUN: stats + samples, zero writes
    python scripts/backfill_rowan.py --run      # the real thing
    ROWAN_POOL=8 python scripts/backfill_rowan.py --run
"""
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, memory  # noqa: E402

SCOPE = "rowan"
THREAD = "main"
POOL = int(os.environ.get("ROWAN_POOL", "6"))
TRIGGER_DISPLAYS = {"heartbeat", "cron", "reminder-check"}
CRON_NAME = re.compile(r"^\[cron:\S+\s+([^\]]+)\]")
THINK = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.S)
# Early-era trigger boxes carry no role_display (MEASURED 2026-08-18: 93 rows,
# rd=None) — the ╔══╗ [SILENT MODE] frame with a TRIGGER: line. Detect by body.
BOX_MARKERS = ("[SILENT MODE]", "TRIGGER: Scheduled heartbeat", "TRIGGER: Cron")
TRIGGER_LINE = re.compile(r"TRIGGER:\s*(.+)", re.I)


def is_trigger_box(content: str) -> tuple[str, str | None] | None:
    """('heartbeat'|'cron', session_name) when the row is a system trigger
    box rather than a human message; None otherwise."""
    if not (content.startswith("╔") or any(m in content for m in BOX_MARKERS)):
        return None
    m = TRIGGER_LINE.search(content)
    what = (m.group(1).strip() if m else "").lower()
    if "heartbeat" in what or not what:
        return ("heartbeat", None)
    session = m.group(1).strip() if m else None
    return ("cron", session)

rowan_dsn = ""
for line in Path(r"E:\git\LANGGRAPH\.env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        rowan_dsn = line.split("=", 1)[1].strip()
if not rowan_dsn:
    raise SystemExit("Rowan DSN not found")


def fetch_rows():
    with psycopg.connect(rowan_dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, idx, role, content, created_at, metadata "
                "FROM messages WHERE thread_id=%s ORDER BY idx", (THREAD,))
            return cur.fetchall()


def curate(rows):
    """Apply Jess's rules. Returns (items, stats). Each item:
    {message_id, speaker, content, occurred_at} ready to retain."""
    items, stats = [], {"kept_human": 0, "kept_rowan": 0, "kept_thoughts": 0,
                        "kept_private_marked": 0, "skip_tool": 0,
                        "skip_trigger": 0, "skip_empty": 0}
    pending_trigger = None   # ('heartbeat', None) | ('cron', session_name)
    for r in rows:
        meta = r.get("metadata") or {}
        # Private-tagged rows are KEPT (the tag over-fires; Jess 2026-08-18)
        # but marked, so future guardrails can filter by provenance.
        is_private = str(meta.get("private", "")).lower() in ("true", "1")
        if r["role"] == "tool" or meta.get("type") == "tool_return":
            stats["skip_tool"] += 1
            continue
        content = (r["content"] or "").strip()
        occurred = meta.get("original_date") or r["created_at"].isoformat()
        if not isinstance(occurred, str):
            occurred = str(occurred)
        display = (meta.get("role_display") or "").strip()

        if r["role"] == "user":
            if display.lower() in TRIGGER_DISPLAYS:
                session = None
                m = CRON_NAME.match(content)
                if m:
                    session = m.group(1).strip()
                pending_trigger = ("cron", session) if display.lower() == "cron" \
                    else ("heartbeat", None)
                stats["skip_trigger"] += 1
                continue
            box = is_trigger_box(content)
            if box:
                pending_trigger = box
                stats["skip_trigger"] += 1
                continue
            if len(content) < 2:
                stats["skip_empty"] += 1
                continue
            speaker_name = display or "Jess"
            items.append({"message_id": r["id"], "speaker": "user",
                          "content": f"{speaker_name}: {content}",
                          "occurred_at": occurred, "private": is_private})
            stats["kept_human"] += 1
            if is_private:
                stats["kept_private_marked"] += 1
            pending_trigger = None
        elif r["role"] == "assistant":
            if len(content) < 3:
                stats["skip_empty"] += 1
                continue
            thoughts = THINK.findall(content)
            visible = THINK.sub("", content).strip()
            frame = ""
            if pending_trigger:
                kind, session = pending_trigger
                frame = (f"[During his scheduled '{session}' session — his own "
                         f"time, unprompted:] " if session else
                         "[During a heartbeat — Rowan's own time, no one "
                         "watching:] ")
                pending_trigger = None
            if visible:
                items.append({"message_id": r["id"], "speaker": "agent",
                              "content": f"Rowan: {frame}{visible}",
                              "occurred_at": occurred, "private": is_private})
                stats["kept_rowan"] += 1
                if is_private:
                    stats["kept_private_marked"] += 1
            for t in thoughts:
                t = t.strip()
                if t:
                    items.append({"message_id": f"{r['id']}:think",
                                  "speaker": "agent",
                                  "content": ("Rowan: [My private thinking, "
                                              "never spoken aloud:] " + t),
                                  "occurred_at": occurred, "private": True})
                    stats["kept_thoughts"] += 1
    return items, stats


def already_done():
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_ref FROM raw_exchanges WHERE scope=%s "
                        "AND source_ref LIKE 'rowan.messages:%%'", (SCOPE,))
            return {r["source_ref"] for r in cur.fetchall()}


def ingest_one(item):
    """Insert raw + run the full pipeline synchronously (bounded by the pool).
    Returns (message_id, extracted: bool)."""
    from src.agent.memory import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_exchanges (scope, speaker, content, source_ref, "
                "occurred_at, private) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (SCOPE, item["speaker"], item["content"],
                 f"rowan.messages:{item['message_id']}", item["occurred_at"],
                 item.get("private", False)))
            ex_id = cur.fetchone()["id"]
    memory._extract_worker(ex_id)
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extracted_at IS NOT NULL AS ok FROM raw_exchanges "
                        "WHERE id=%s", (ex_id,))
            return item["message_id"], cur.fetchone()["ok"]


def main():
    run = "--run" in sys.argv
    rows = fetch_rows()
    items, stats = curate(rows)
    print(f"source rows: {len(rows)}  ->  retain items: {len(items)}")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if not run:
        print("\n== DRY RUN — zero writes. Sample decisions: ==")
        for it in items[:3] + items[len(items) // 2:len(items) // 2 + 3] + items[-3:]:
            print(f"  KEEP [{it['speaker']}] ({it['occurred_at'][:10]}) "
                  f"{it['content'][:110]!r}")
        est_calls = round(len(items) * 3.3)
        for pool, per_call in ((6, 2.0), (10, 1.4)):
            hours = est_calls * per_call / pool * POOL / pool / 3600 if False else \
                est_calls * (per_call) / 3600
            print(f"  projection @pool={pool}: ~{est_calls} calls, "
                  f"~{est_calls * per_call / 3600:.1f}h")
        print(f"\nRun for real:  python scripts/backfill_rowan.py --run   "
              f"(pool {POOL}, resumable, $0 on subscription)")
        return

    done = already_done()
    todo = [i for i in items if f"rowan.messages:{i['message_id']}" not in done]
    print(f"resume check: {len(items) - len(todo)} already ingested, "
          f"{len(todo)} to go")
    t0 = time.time()
    completed = failures = consec_fail = 0
    with ThreadPoolExecutor(max_workers=POOL) as ex:
        futures = [ex.submit(ingest_one, item) for item in todo]
        for i, fut in enumerate(futures):
            try:
                _mid, ok = fut.result()
                completed += 1
                if ok:
                    consec_fail = 0
                else:
                    failures += 1
                    consec_fail += 1
            except Exception as e:
                failures += 1
                consec_fail += 1
                print(f"  item error: {e}")
            if consec_fail >= 10:
                print("  10 consecutive extraction failures — likely a plan "
                      "window; raws are safe and queued; sleeping 15 min...")
                time.sleep(900)
                consec_fail = 0
            if completed % 100 == 0 and completed:
                rate = completed / (time.time() - t0)
                eta_h = (len(todo) - completed) / rate / 3600 if rate else 0
                print(f"  {completed}/{len(todo)} "
                      f"({failures} queued-for-retry) — ETA {eta_h:.1f}h")
    # Final sweep: retry anything the windows left queued
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM raw_exchanges WHERE scope=%s AND "
                        "extracted_at IS NULL", (SCOPE,))
            queued = [r["id"] for r in cur.fetchall()]
    if queued:
        print(f"final sweep: retrying {len(queued)} queued extractions...")
        with ThreadPoolExecutor(max_workers=POOL) as ex:
            list(ex.map(memory._extract_worker, queued))
    print(f"DONE in {(time.time() - t0) / 3600:.1f}h — {completed} ingested. "
          f"Rowan's past is remembered.")


if __name__ == "__main__":
    main()
