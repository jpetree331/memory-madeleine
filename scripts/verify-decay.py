"""VERIFY — decay is a cost of living, not of elapsed time (2026-08-21).

Jess's finding: 4410 episodes decayed every night against ~3.16 strengthened
per recall, on the wall clock, so a day she spent at work cost every memory
exactly what a day of conversation cost it. Three corrections landed:
activity-gated decay, a gentler factor, and a dormancy floor.

Everything here runs inside ONE transaction that is ALWAYS rolled back —
the real corpus is never touched. Run it any time:

    .venv\\Scripts\\python.exe scripts\\verify-decay.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import config, db  # noqa: E402
from src.agent.consolidate import decay_pass  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results = []


def check(label, got, want, tol=1e-6):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    results.append((PASS if ok else FAIL, label, got, want))


def mkepisode(cur, scope, strength, *, pinned=False, recalled_at=None):
    cur.execute(
        "INSERT INTO episodes (scope, trace, register, salience, strength, "
        "pinned, last_recalled_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (scope, "a trace long enough to be realistic for the compression band "
                "check, well past eighty characters of narrative texture",
         "test", 0.8, strength, pinned, recalled_at))
    return cur.fetchone()["id"]


def mkexchange(cur, scope, occurred_at, solitary=False,
               speaker="user", speaker_name=None):
    cur.execute(
        "INSERT INTO raw_exchanges (scope, speaker, speaker_name, content, "
        "occurred_at, solitary) VALUES (%s, %s, %s, 'test', %s, %s) RETURNING id",
        (scope, speaker, speaker_name, occurred_at, solitary))
    return cur.fetchone()["id"]


def strength_of(cur, ep_id):
    cur.execute("SELECT strength FROM episodes WHERE id=%s", (ep_id,))
    return float(cur.fetchone()["strength"])


def main():
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    long_ago = now - timedelta(days=365)
    f = config.DECAY_FACTOR
    floor = config.DECAY_MIN_STRENGTH

    print(f"config: DECAY_FACTOR={f}  DECAY_MIN_STRENGTH={floor}  "
          f"DECAY_REQUIRE_ACTIVITY={config.DECAY_REQUIRE_ACTIVITY}  "
          f"window={config.DECAY_ACTIVITY_WINDOW_HOURS}h\n"
          f"        DECAY_SOLITARY_COUNTS={config.DECAY_SOLITARY_COUNTS}  "
          f"DECAY_RECALL_COUNTS={config.DECAY_RECALL_COUNTS}\n"
          f"        machine speakers={config.DECAY_MACHINE_SPEAKERS}\n")

    conn = db.get_connection()
    try:
        cur = conn.cursor()

        # ── A scope that lived today: someone spoke to it ────────────────────
        mkexchange(cur, "zz_lived", now - timedelta(hours=1))
        ep_plain = mkepisode(cur, "zz_lived", 0.9)
        ep_pinned = mkepisode(cur, "zz_lived", 0.9, pinned=True)
        ep_recent = mkepisode(cur, "zz_lived", 0.9, recalled_at=now - timedelta(days=2))
        ep_stale = mkepisode(cur, "zz_lived", 0.9, recalled_at=now - timedelta(days=30))
        ep_nearfloor = mkepisode(cur, "zz_lived", floor + 0.0002)
        ep_atfloor = mkepisode(cur, "zz_lived", floor)

        # ── A scope nobody touched at all ────────────────────────────────────
        ep_idle = mkepisode(cur, "zz_idle", 0.9)

        # ── A scope with a big BACKFILL today, but no living ─────────────────
        # created_at is now (the import), occurred_at is a year ago (the life).
        mkexchange(cur, "zz_backfill", long_ago)
        ep_backfill = mkepisode(cur, "zz_backfill", 0.9)

        # ── A scope that recalled something but was never spoken to ──────────
        cur.execute("INSERT INTO recall_log (scope, query) VALUES ('zz_recall', 'q')")
        ep_recall = mkepisode(cur, "zz_recall", 0.9)

        # ── A scope with a HEARTBEAT today but no conversation ───────────────
        # Rowan's REAL live shape, MEASURED 2026-08-21: solitary is FALSE (only
        # the backfill ever set it), the prompt arrives as speaker='user' named
        # 'heartbeat', and his reply is speaker='agent'. Neither is a human
        # turn. A solitary-only test passed this and was wrong.
        mkexchange(cur, "zz_heartbeat", None, speaker="user", speaker_name="heartbeat")
        mkexchange(cur, "zz_heartbeat", None, speaker="agent", speaker_name="Rowan")
        ep_heartbeat = mkepisode(cur, "zz_heartbeat", 0.9)

        # ── A scope running CRON jobs today but no conversation ──────────────
        mkexchange(cur, "zz_cron", None, speaker="user", speaker_name="cron")
        mkexchange(cur, "zz_cron", None, speaker="agent", speaker_name="Rowan")
        ep_cron = mkepisode(cur, "zz_cron", 0.9)

        # ── A scope where a HUMAN actually spoke, amid the machinery ─────────
        mkexchange(cur, "zz_human", None, speaker="user", speaker_name="heartbeat")
        mkexchange(cur, "zz_human", None, speaker="user", speaker_name="Jess")
        ep_human = mkepisode(cur, "zz_human", 0.9)

        # ── Agent Boardspace's shape: speaker_name is never set, the display
        # name is baked into the content instead. A real parlor turn must still
        # read as living even with no name to inspect.
        mkexchange(cur, "zz_parlor", None, speaker="user", speaker_name=None)
        mkexchange(cur, "zz_parlor", None, speaker="agent", speaker_name=None)
        ep_parlor = mkepisode(cur, "zz_parlor", 0.9)

        # ── Boardspace retain_reasoning: agent-side private thinking only.
        # The agent talking to itself is not Jess being present.
        mkexchange(cur, "zz_reasoning", None, speaker="agent", speaker_name=None)
        ep_reasoning = mkepisode(cur, "zz_reasoning", 0.9)

        out = decay_pass(cur, now, week_ago)

        check("lived scope decays at DECAY_FACTOR",
              strength_of(cur, ep_plain), 0.9 * f)
        check("pinned episode is exempt",
              strength_of(cur, ep_pinned), 0.9)
        check("recalled within 7d is exempt",
              strength_of(cur, ep_recent), 0.9)
        check("recalled 30d ago still decays",
              strength_of(cur, ep_stale), 0.9 * f)
        check("decay floors at DECAY_MIN_STRENGTH",
              strength_of(cur, ep_nearfloor), floor)
        check("already at floor stays put (no churn)",
              strength_of(cur, ep_atfloor), floor)
        check("IDLE scope does not decay",
              strength_of(cur, ep_idle), 0.9)
        check("backfill is not living - scope does not decay",
              strength_of(cur, ep_backfill), 0.9)
        check("a recall alone follows DECAY_RECALL_COUNTS",
              strength_of(cur, ep_recall),
              0.9 * f if config.DECAY_RECALL_COUNTS else 0.9)
        check("live heartbeat (solitary=FALSE) is not living",
              strength_of(cur, ep_heartbeat), 0.9)
        check("cron traffic is not living",
              strength_of(cur, ep_cron), 0.9)
        check("a human turn amid the machinery IS living",
              strength_of(cur, ep_human), 0.9 * f)
        check("Boardspace parlor turn (no speaker_name) IS living",
              strength_of(cur, ep_parlor), 0.9 * f)
        check("agent-only reasoning is not living",
              strength_of(cur, ep_reasoning), 0.9)
        check("floor keeps everything above spread.py conduction (0.1)",
              strength_of(cur, ep_nearfloor) >= 0.1, True)
        check("idle scopes are reported",
              "zz_idle" in out["scopes_idle"] and "zz_backfill" in out["scopes_idle"],
              True)
        check("lived scopes are reported",
              "zz_lived" in out["scopes_decayed"] and "zz_human" in out["scopes_decayed"],
              True)
        check("machine-only scopes are reported idle",
              "zz_heartbeat" in out["scopes_idle"] and "zz_cron" in out["scopes_idle"],
              True)
        check("nothing compressed while floor >= 0.1", out["compressed"], 0)
        check("nothing tombstoned while floor >= 0.1", out["tombstoned"], 0)

        # ── What tonight would actually do to the real corpus ────────────────
        print("real scopes, as they stand right now:")
        cur.execute("SELECT DISTINCT scope FROM episodes WHERE scope NOT LIKE 'zz_%'")
        real = sorted(r["scope"] for r in cur.fetchall())
        for s in real:
            state = "WOULD DECAY" if s in out["scopes_decayed"] else "idle - exempt"
            cur.execute("SELECT count(*) AS n FROM episodes WHERE scope=%s "
                        "AND NOT pinned AND NOT quarantined AND strength > %s "
                        "AND (last_recalled_at IS NULL OR last_recalled_at < %s)",
                        (s, floor, week_ago))
            eligible = cur.fetchone()["n"]
            cur.execute("SELECT max(COALESCE(occurred_at, created_at)) AS t "
                        "FROM raw_exchanges WHERE scope=%s AND NOT solitary "
                        "AND speaker='user' AND (speaker_name IS NULL OR "
                        "lower(speaker_name) <> ALL(%s))",
                        (s, config.DECAY_MACHINE_SPEAKERS))
            spoke = cur.fetchone()["t"]
            cur.execute("SELECT max(created_at) AS t FROM recall_log WHERE scope=%s", (s,))
            recalled = cur.fetchone()["t"]
            fmt = lambda t: f"{t:%Y-%m-%d %H:%M}" if t else "never"  # noqa: E731
            print(f"   {s:<10} {state:<14} {eligible:>5} eligible | "
                  f"spoken to {fmt(spoke)} | recall {fmt(recalled)}")
    finally:
        conn.rollback()
        conn.close()

    print()
    failed = 0
    for status, label, got, want in results:
        if status == FAIL:
            failed += 1
            print(f"  {status}  {label}\n        got {got!r}, wanted {want!r}")
        else:
            print(f"  {status}  {label}")
    print(f"\n{len(results) - failed}/{len(results)} checks passed "
          f"(transaction rolled back — nothing written)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
