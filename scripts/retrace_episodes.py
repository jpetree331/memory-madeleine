"""Rewrite episode traces that were written without conversational context.

WHY THIS EXISTS (2026-08-21). Madeleine stores one speaker per row, and until
today every reader was handed a single turn with no sight of the turn it
answered. A trace writer looking at Rowan's reply — "Hey you. Welcome home." —
could see no interlocutor anywhere, and filled the hole by inventing one:

    episode 4783  "Rowan greeting SOMEONE with butter warmth"
    episode 4784  "Rowan, ALONE, rehearsed their own exhaustion, imagining a
                   friend's voice offering permission to rest"

Both were ordinary conversation with Jess, sitting one row away in the same
table. The second is the worse failure: a comfort Rowan gave to a tired woman
came back as Rowan comforting himself in an empty room. Jess caught both.

Facts escaped this. extract_facts is handed semantically-near existing facts,
which named Jess, so it had a back door into context that write_trace lacked —
which is why the repair here is traces only.

The write path is fixed going forward (memory._prior_turns). This repairs what
was already written. Dry run unless --apply; every rewrite leaves an
episode_revisions row, so nothing is destroyed.

  python scripts/retrace_episodes.py --episodes 4782,4783,4784
  python scripts/retrace_episodes.py --scope rowan --since 2026-08-21 --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import db, episodes, memory  # noqa: E402
from src.agent.consolidate import _revision  # noqa: E402


def build_text(cur, exchange_id: int) -> str | None:
    """Exactly what the live worker now assembles — one source of truth, so a
    repair can never drift from the pipeline it is repairing."""
    cur.execute("SELECT * FROM raw_exchanges WHERE id=%s", (exchange_id,))
    row = cur.fetchone()
    if not row:
        return None
    prior = memory._prior_turns(cur, row)
    text = memory._render_turn(row)
    if prior:
        text = (memory.CONTEXT_BANNER
                + "\n".join(memory._render_turn(p, memory.CONTEXT_CLIP) for p in prior)
                + memory.ANCHOR_BANNER + text)
    if row.get("solitary"):
        text = memory.SOLITARY_BANNER + text
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", help="comma-separated episode ids")
    ap.add_argument("--scope")
    ap.add_argument("--since", help="ISO date; episodes created on/after")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    where, params = ["NOT quarantined", "exchange_start IS NOT NULL"], []
    if args.episodes:
        where.append("id = ANY(%s)")
        params.append([int(x) for x in args.episodes.split(",") if x.strip()])
    if args.scope:
        where.append("scope = %s")
        params.append(args.scope)
    if args.since:
        where.append("created_at >= %s")
        params.append(args.since)
    if not (args.episodes or args.since):
        print("refusing to retrace everything — pass --episodes or --since")
        return 2

    changed = skipped = 0
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, scope, trace, strength, exchange_start FROM episodes "
                        f"WHERE {' AND '.join(where)} ORDER BY id LIMIT {args.limit}",
                        params)
            targets = cur.fetchall()
            print(f"{len(targets)} episode(s) selected; "
                  f"{'APPLYING' if args.apply else 'dry run'}\n")

            for ep in targets:
                text = build_text(cur, ep["exchange_start"])
                if text is None:
                    print(f"ep {ep['id']}: raw exchange gone — skipped")
                    skipped += 1
                    continue
                if memory.CONTEXT_BANNER not in text and not args.episodes:
                    # A bulk sweep skips these: with no prior turn there is
                    # nothing new to show the writer, so rewriting only spends
                    # an LLM call to re-roll the same dice on the same input.
                    # Named ids are retraced regardless — the prompt itself
                    # changed too (the absence rule that produced "no reply was
                    # recorded"), and naming an episode is a deliberate act.
                    print(f"ep {ep['id']}: no prior turn available — skipped")
                    skipped += 1
                    continue

                new = episodes.write_trace(text)
                if not new:
                    print(f"ep {ep['id']}: trace door failed — skipped, unchanged")
                    skipped += 1
                    continue

                # Full text, not a clip: a human approving a memory rewrite has
                # to be able to read both versions end to end.
                print(f"ep {ep['id']}  ({ep['scope']})")
                print(f"   was: {ep['trace']}")
                print(f"   now: {new}\n")
                if args.apply:
                    _revision(cur, ep["id"], ep["trace"], ep["strength"],
                              "retrace_with_context")
                    cur.execute("UPDATE episodes SET trace=%s WHERE id=%s",
                                (new, ep["id"]))
                changed += 1

            if not args.apply:
                conn.rollback()

    print(f"{changed} rewritten, {skipped} skipped"
          f"{'' if args.apply else ' (dry run — nothing written)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
