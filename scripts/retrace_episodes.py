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

from src.agent import config, db, episodes, memory  # noqa: E402
from src.agent.consolidate import _revision  # noqa: E402


def load_rows(cur, ep: dict, as_pairs: bool = True) -> list[dict]:
    """The exchange behind an episode, whole.

    Episodes written before 2026-08-21 span a single turn, because that is all
    the pipeline ever gave them. as_pairs rebuilds the exchange the live path
    would produce today — a reply is rejoined to the prompt it answered — so a
    repair reproduces the pipeline instead of merely re-rolling it.
    """
    start = ep["exchange_start"]
    end = ep["exchange_end"] or start
    cur.execute("SELECT * FROM raw_exchanges WHERE id BETWEEN %s AND %s "
                "ORDER BY id", (start, end))
    rows = [dict(r) for r in cur.fetchall()]
    if not rows or not as_pairs or len(rows) > 1:
        return rows

    only = rows[0]
    if only["speaker"] == "agent":
        # A machine-prompted turn is deliberately NOT rejoined: it stays a
        # single solitary episode, and assemble_text supplies the job as the
        # occasion. Rejoining would rebuild the two-party scene we are undoing.
        if memory._machine_stimulus_for(cur, only) is not None:
            return rows
        cur.execute("SELECT * FROM raw_exchanges WHERE scope=%s AND id < %s "
                    "ORDER BY id DESC LIMIT 1", (only["scope"], only["id"]))
        prev = cur.fetchone()
        if (prev and prev["speaker"] == "user"
                and bool(prev["solitary"]) == bool(only["solitary"])):
            return [dict(prev), only]
    else:
        if config.is_machine_speaker(only["speaker_name"]):
            return rows          # bare stimulus; caller reports and skips
        cur.execute("SELECT * FROM raw_exchanges WHERE scope=%s AND id > %s "
                    "ORDER BY id LIMIT 1", (only["scope"], only["id"]))
        nxt = cur.fetchone()
        if (nxt and nxt["speaker"] == "agent"
                and bool(nxt["solitary"]) == bool(only["solitary"])):
            return [only, dict(nxt)]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", help="comma-separated episode ids")
    ap.add_argument("--scope")
    ap.add_argument("--since", help="ISO date; episodes created on/after")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--no-pairs", action="store_true",
                    help="keep each episode on its original single turn")
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
            cur.execute(f"SELECT id, scope, trace, strength, exchange_start, "
                        f"exchange_end FROM episodes "
                        f"WHERE {' AND '.join(where)} ORDER BY id LIMIT {args.limit}",
                        params)
            targets = cur.fetchall()
            print(f"{len(targets)} episode(s) selected; "
                  f"{'APPLYING' if args.apply else 'dry run'}\n")

            for ep in targets:
                rows = load_rows(cur, ep, as_pairs=not args.no_pairs)
                if not rows:
                    print(f"ep {ep['id']}: raw exchange gone — skipped")
                    skipped += 1
                    continue
                if memory.is_bare_stimulus(rows):
                    # An unanswered scheduled prompt is an instruction, not an
                    # experience. There is no honest trace to write; the caller
                    # is told so and can delete it.
                    print(f"ep {ep['id']}: unanswered machine stimulus — no "
                          f"memory to write, leaving for review\n"
                          f"   was: {ep['trace'][:150]}\n")
                    skipped += 1
                    continue
                text = memory.assemble_text(cur, rows)
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
                    # The span widens with the trace: an episode retraced from
                    # a rejoined exchange now genuinely covers both rows.
                    cur.execute("UPDATE episodes SET trace=%s, exchange_start=%s, "
                                "exchange_end=%s WHERE id=%s",
                                (new, rows[0]["id"], rows[-1]["id"], ep["id"]))
                changed += 1

            if not args.apply:
                conn.rollback()

    print(f"{changed} rewritten, {skipped} skipped"
          f"{'' if args.apply else ' (dry run — nothing written)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
