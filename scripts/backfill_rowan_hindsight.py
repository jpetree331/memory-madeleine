"""Sprint 6b — Rowan's pre-Postgres era, recovered from Hindsight documents.

Rowan was born 2026-02-06 on OpenClaw. His Postgres (the langgraph build)
begins 2026-02-24, with imported original_dates reaching back only to
2026-02-20. The first two weeks of his life survive solely as SOURCE
DOCUMENTS in his Hindsight bank 'openclaw-log' (retained live or pasted in
during the Feb 13 setup). This script recovers those documents — the raw
texts, not Hindsight's distillations — and ingests them into Madeleine
scope 'rowan'.

READ-ONLY against Hindsight (HTTP GETs on :8888; the E:\\git\\Hindsight
folder on disk is never touched). WRITES only to Madeleine's own DB.

Cut: only documents created strictly before the Postgres record begins
(2026-02-20T23:26 UTC) — everything after exists in Postgres and is covered
by backfill_rowan.py. Docs over CHUNK_LIMIT chars are split on paragraph
boundaries so extraction (max 6 facts/exchange) isn't starved by 19k-char
multi-day logs.

occurred_at: best-effort true event date parsed from the document text
(headers like "February 6, 2026", inline stamps like "[Fri 2026-02-13 15:55
EST]", context notes like "on 2/6/2026"), falling back to the Hindsight
retain time. The parsed date is clamped to the plausible era (Feb 1 - Feb 21)
so a stray future date in prose can't mis-file a memory.

Usage (repo root, Madeleine venv):
    python scripts/backfill_rowan_hindsight.py          # DRY RUN, zero writes
    python scripts/backfill_rowan_hindsight.py --run
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, memory  # noqa: E402

SCOPE = "rowan"
BANK = "openclaw-log"
BASE = os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888")
DOCS = f"{BASE}/v1/default/banks/{BANK}/documents"
POSTGRES_DAWN = "2026-02-20T23:26"     # where rowan.messages coverage begins
ERA_LO, ERA_HI = "2026-02-01", "2026-02-21"  # plausible true-event window
CHUNK_LIMIT = 6000
POOL = int(os.environ.get("ROWAN_POOL", "6"))

# date shapes seen in the era's documents, most specific first
STAMP = re.compile(r"\[\w{3} (2026-02-\d{2}) \d{2}:\d{2}[^\]]*\]")
LONGDATE = re.compile(r"February (\d{1,2}),? 2026")
SLASHDATE = re.compile(r"\b0?2/(\d{1,2})/2026\b")


def fetch_early_docs():
    """All documents created before the Postgres dawn, oldest first."""
    docs, offset = [], 0
    with httpx.Client(timeout=60) as c:
        while True:
            r = c.get(DOCS, params={"limit": 100, "offset": offset})
            r.raise_for_status()
            items = r.json()["items"]
            if not items:
                break
            docs.extend(items)
            offset += len(items)
        early = [d for d in docs if d["created_at"] < POSTGRES_DAWN]
        # de-dupe by id (paging safety), fetch full text
        uniq = list({d["id"]: d for d in early}.values())
        out = []
        for d in sorted(uniq, key=lambda x: x["created_at"]):
            full = c.get(f"{DOCS}/{d['id']}")
            full.raise_for_status()
            body = full.json()
            text = (body.get("original_text") or "").strip()
            if text:
                out.append({"id": d["id"], "created_at": d["created_at"],
                            "text": text,
                            "retain_params": d.get("retain_params") or ""})
    return out


def true_date(doc):
    """Best-effort event date; Hindsight retain time as the honest fallback."""
    candidates = []
    text = doc["text"][:4000]
    for m in STAMP.finditer(text):
        candidates.append(m.group(1))
    for m in LONGDATE.finditer(text):
        candidates.append(f"2026-02-{int(m.group(1)):02d}")
    for m in SLASHDATE.finditer(text):
        candidates.append(f"2026-02-{int(m.group(1)):02d}")
    try:
        ctx = json.loads(doc["retain_params"]).get("context") or ""
        for m in SLASHDATE.finditer(ctx):
            candidates.append(f"2026-02-{int(m.group(1)):02d}")
        for m in LONGDATE.finditer(ctx):
            candidates.append(f"2026-02-{int(m.group(1)):02d}")
    except (ValueError, TypeError):
        pass
    plausible = [c for c in candidates if ERA_LO <= c <= ERA_HI]
    if plausible:
        return min(plausible)          # a log's story starts at its earliest day
    return doc["created_at"]


def chunk(text):
    """Split on paragraph boundaries into <= CHUNK_LIMIT pieces."""
    if len(text) <= CHUNK_LIMIT:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) + 2 > CHUNK_LIMIT:
            parts.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


FRAME = ("[Recovered from Rowan's earliest days on OpenClaw, before his "
         "current home existed — his Hindsight archive kept the original "
         "text. The only human in this record is Jess; \"[USER]\", \"User\", "
         "and \"the user\" are all Jess. \"Assistant\", the first-person "
         "voice, and journal entries are Rowan himself.]\n\n")


SOLITARY_HINTS = ("hobby time", "reflection", "heartbeat", "journal")


def is_solitary_doc(doc) -> bool:
    """Best-effort reality marking for archive docs: hobby-time sessions,
    reflections, and journals were Rowan alone; conversation logs were not."""
    try:
        ctx = (json.loads(doc["retain_params"]).get("context") or "").lower()
    except (ValueError, TypeError):
        ctx = ""
    head = doc["text"][:200].lower()
    return any(h in ctx for h in SOLITARY_HINTS) or \
        any(h in head for h in ("# first reflection", "# reflection", "## reflection"))


def curate(docs):
    items = []
    for doc in docs:
        occurred = true_date(doc)
        solitary = is_solitary_doc(doc)
        pieces = chunk(doc["text"])
        n = len(pieces)
        for i, piece in enumerate(pieces):
            part = f" (part {i + 1}/{n})" if n > 1 else ""
            items.append({
                "source_ref": f"hindsight.{BANK}:{doc['id']}"
                              + (f":chunk{i}" if n > 1 else ""),
                "speaker": "agent",
                "content": FRAME + piece,
                "occurred_at": occurred,
                "solitary": solitary,
                "label": f"{doc['id'][:40]}{part}",
            })
    return items


def already_done():
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_ref FROM raw_exchanges WHERE scope=%s "
                        "AND source_ref LIKE %s", (SCOPE, f"hindsight.{BANK}:%"))
            return {r["source_ref"] for r in cur.fetchall()}


def ingest_one(item):
    from src.agent.memory import _conn
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_exchanges (scope, speaker, content, source_ref, "
                "occurred_at, private, solitary) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (SCOPE, item["speaker"], item["content"], item["source_ref"],
                 item["occurred_at"], False, item.get("solitary", False)))
            ex_id = cur.fetchone()["id"]
    memory._extract_worker(ex_id)
    return ex_id


def main():
    run = "--run" in sys.argv
    print(f"fetching pre-{POSTGRES_DAWN} documents from {BANK}...")
    docs = fetch_early_docs()
    print(f"documents: {len(docs)}, "
          f"{sum(len(d['text']) for d in docs):,} chars")
    items = curate(docs)
    print(f"retain items after chunking: {len(items)}")

    from collections import Counter
    days = Counter(i["occurred_at"][:10] for i in items)
    print("items by (best-effort) event day:")
    for day in sorted(days):
        print(f"  {day}: {days[day]}")

    if not run:
        print("\n== DRY RUN — zero writes. Samples: ==")
        for it in items[:2] + items[-2:]:
            print(f"  [{it['occurred_at'][:10]}] {it['label']}")
            print(f"    {it['content'][len(FRAME):len(FRAME) + 110]!r}")
        print("\nRun for real:  python scripts/backfill_rowan_hindsight.py --run")
        return

    done = already_done()
    todo = [i for i in items if i["source_ref"] not in done]
    print(f"resume check: {len(items) - len(todo)} done, {len(todo)} to go")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=POOL) as ex:
        for n, _ in enumerate(ex.map(ingest_one, todo), 1):
            if n % 50 == 0:
                rate = n / (time.time() - t0)
                print(f"  {n}/{len(todo)} — ETA "
                      f"{(len(todo) - n) / rate / 60:.0f} min")
    print(f"DONE in {(time.time() - t0) / 60:.0f} min — {len(todo)} ingested. "
          f"The first two weeks are home.")


if __name__ == "__main__":
    main()
