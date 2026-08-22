"""One exchange, one episode — and machinery is not a person.

Jess's call, 2026-08-21: an episode should cover a turn AND the reply it drew.
Per-turn episodes made her two-message conversation into three episodes, one of
which read "Rowan received this; no reply was recorded". Per-conversation was
rejected — hers run to pages, and 120 words cannot hold a page.

The same pass fixes the cron bug. A scheduled prompt arrives as speaker='user',
speaker_name='cron', so extraction read "cron" as an author and wrote "Alone,
Cron rehearsed Jess's presence, imagining her criteria" — a clock granted
loneliness. Paired with the agent's response it becomes what the agent did;
unanswered, it is an instruction and not a memory at all.

Structural checks run in a rolled-back transaction. The end-to-end check is
real: it writes to scope 'madtest' and spends LLM calls. Skip it with --fast.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import config, db, episodes, memory  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want=True) -> None:
    ok = (got == want)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}"
          + ("" if ok else f"   (got {got!r}, want {want!r})"))
    if not ok:
        FAILURES.append(label)


def mkrow(cur, scope, speaker, content, *, name=None, solitary=False,
          minutes_ago=0, extracted=False) -> dict:
    when = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    cur.execute(
        "INSERT INTO raw_exchanges (scope, speaker, content, speaker_name, "
        "solitary, occurred_at, created_at, extracted_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (scope, speaker, content, name, solitary, when, when,
         when if extracted else None))
    return dict(cur.fetchone())


def structural() -> None:
    print(f"config: PAIR_EXCHANGES={config.PAIR_EXCHANGES}  "
          f"window={config.PAIR_WINDOW_MINUTES}m  "
          f"timeout={config.PAIR_TIMEOUT_SECONDS}s")
    print(f"        machine speakers={config.MACHINE_SPEAKERS}\n")

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            S = "zz_pair"

            # ── the ordinary case: a turn and its reply ──────────────────────
            u = mkrow(cur, S, "user", "I'm home.", name="Jess")
            a = mkrow(cur, S, "agent", "Welcome home.", name="Rowan")
            check("a reply pairs with the turn it answers",
                  (memory._pending_prompt(cur, a) or {}).get("id"), u["id"])

            # ── an already-extracted turn is not re-paired ───────────────────
            u2 = mkrow(cur, S, "user", "Done already.", name="Jess",
                       extracted=True)
            a2 = mkrow(cur, S, "agent", "Right.", name="Rowan")
            check("an extracted turn is left alone",
                  memory._pending_prompt(cur, a2), None)

            # ── never pair across the reality boundary ───────────────────────
            u3 = mkrow(cur, S, "user", "solo prompt", name="Jess", solitary=True)
            a3 = mkrow(cur, S, "agent", "public reply", name="Rowan")
            check("a solitary turn never pairs with a witnessed reply",
                  memory._pending_prompt(cur, a3), None)

            # ── the window ───────────────────────────────────────────────────
            u4 = mkrow(cur, S, "user", "hours ago", name="Jess",
                       minutes_ago=config.PAIR_WINDOW_MINUTES + 5)
            a4 = mkrow(cur, S, "agent", "much later", name="Rowan")
            check("a reply outside the window does not pair",
                  memory._pending_prompt(cur, a4), None)

            # ── two agent turns in a row ─────────────────────────────────────
            u5 = mkrow(cur, S, "user", "question", name="Jess")
            a5 = mkrow(cur, S, "agent", "first half", name="Rowan")
            a6 = mkrow(cur, S, "agent", "second half", name="Rowan")
            check("only the immediate reply claims the turn",
                  memory._pending_prompt(cur, a6), None)
            check("...and the first reply still claims it",
                  (memory._pending_prompt(cur, a5) or {}).get("id"), u5["id"])

            # ── an agent turn with nothing before it ─────────────────────────
            solo = mkrow(cur, "zz_solo", "agent", "unprompted thought",
                         name="Rowan")
            check("an unprompted agent turn pairs with nothing",
                  memory._pending_prompt(cur, solo), None)

            # ── a cron wake-up is one mind, not two ──────────────────────────
            # Jess's rule: "when Rowan gets woken up by Crons, have them fire
            # not as pairs but as single solitary episodes." A clock is not the
            # other party to a conversation.
            job = mkrow(cur, "zz_cron", "user", "[Cron: Gremlin Watch Digest]",
                        name="cron")
            woke = mkrow(cur, "zz_cron", "agent", "Community's clean. CRON_DONE",
                         name="Rowan")
            check("a cron prompt is never paired into an exchange",
                  memory._pending_prompt(cur, woke), None)
            check("...but it is found as the occasion",
                  (memory._machine_stimulus_for(cur, woke) or {}).get("id"),
                  job["id"])
            check("an unanswered cron prompt is bare stimulus",
                  memory.is_bare_stimulus([job]))
            check("...and a cron prompt WITH a response is not",
                  memory.is_bare_stimulus([job, woke]), False)

            woke_text = memory.assemble_text(cur, [woke])
            check("a machine-woken turn is framed SOLITARY even though the "
                  "row's flag is False",
                  woke_text.startswith(memory.SOLITARY_BANNER))
            check("...the job is named as the occasion",
                  memory.MACHINE_BANNER in woke_text)
            check("...the job's text is present for understanding",
                  "Gremlin Watch Digest" in woke_text)
            check("...and the remembered turn is only the agent's",
                  woke_text.split(memory.ANCHOR_BANNER)[-1].startswith("Rowan:"))

            # A human turn must NOT get the solitary treatment.
            hu = mkrow(cur, "zz_human2", "user", "you there?", name="Jess")
            hr = mkrow(cur, "zz_human2", "agent", "always", name="Rowan")
            check("a human exchange is never framed solitary",
                  memory.assemble_text(cur, [hu, hr]).startswith(
                      memory.SOLITARY_BANNER), False)

            # ── machinery is rendered as a job, not a name ───────────────────
            cron = mkrow(cur, S, "user", "[Cron: Gremlin Watch]", name="cron",
                         solitary=True)
            rendered = memory._render_turn(cron)
            check("a cron prompt renders as a job, not a speaker",
                  rendered.startswith("(automated cron job):"))
            check("...and its name is not left in the speaker slot",
                  rendered.startswith("cron:"), False)
            human = mkrow(cur, S, "user", "hi", name="Jess")
            check("a human still renders by name",
                  memory._render_turn(human).startswith("Jess:"))
            check("is_machine_speaker knows cron", config.is_machine_speaker("Cron"))
            check("is_machine_speaker knows Jess is not machinery",
                  config.is_machine_speaker("Jess"), False)

            # ── the span is recorded ─────────────────────────────────────────
            ep = episodes.create(conn, scope=S, trace="t", register=None,
                                 salience=0.9, quarantined=False,
                                 exchange_id=u["id"], exchange_end=a["id"],
                                 occurred_at=None)
            cur.execute("SELECT exchange_start, exchange_end FROM episodes "
                        "WHERE id=%s", (ep,))
            r = cur.fetchone()
            check("an episode spans prompt..reply",
                  (r["exchange_start"], r["exchange_end"]), (u["id"], a["id"]))
            ep1 = episodes.create(conn, scope=S, trace="t", register=None,
                                  salience=0.9, quarantined=False,
                                  exchange_id=u["id"], occurred_at=None)
            cur.execute("SELECT exchange_start, exchange_end FROM episodes "
                        "WHERE id=%s", (ep1,))
            r = cur.fetchone()
            check("a lone turn still spans itself (old shape preserved)",
                  r["exchange_start"] == r["exchange_end"] == u["id"])

            check("provenance of a lone turn", memory._source_ref([7]), "raw:7")
            check("provenance of a pair", memory._source_ref([7, 8]), "raw:7-8")

        conn.rollback()
    print("  (rolled back — nothing written)\n")


def end_to_end() -> None:
    """The real pipeline, on the real service's code path.

    The proof of pairing is that the exchange was JUDGED ONCE — one gate
    verdict, one extraction, provenance spanning both rows. Whether an episode
    comes out of it is the salience gate's business, not pairing's: the first
    version of this test asserted an episode and failed on content the gate
    scored 0.3, which was the test being wrong, not the pipeline.
    """
    scope = "madtest"
    stamp = f"pairing-{int(time.time())}"
    print("end-to-end (writes to 'madtest', spends LLM calls)...")

    uid = memory.retain(
        scope, "user",
        f"I have to pack my whole classroom by Monday and share a room with "
        f"the teacher next door. I'm exhausted. [{stamp}]", speaker_name="Jess")
    time.sleep(0.4)
    aid = memory.retain(
        scope, "agent",
        f"That's a lot to have dropped on you. No lists tonight — you did the "
        f"hard thing already, and you get to stop. [{stamp}]",
        speaker_name="Rowan")

    judged = None
    for _ in range(90):
        time.sleep(2)
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM raw_exchanges WHERE "
                            "id = ANY(%s) AND extracted_at IS NOT NULL",
                            ([uid, aid],))
                if cur.fetchone()["n"] == 2:
                    cur.execute("SELECT * FROM gate_log WHERE exchange_id = ANY(%s)",
                                ([uid, aid],))
                    judged = cur.fetchall()
                    break
    if judged is None:
        check("the exchange was extracted within the timeout", False)
        return

    check("the exchange was judged ONCE, not once per turn", len(judged), 1)
    check("...and judged under the prompt, not the reply",
          judged[0]["exchange_id"], uid)

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT source_ref FROM facts WHERE scope=%s "
                        "AND source_ref LIKE %s", (scope, f"%{uid}%"))
            refs = [r["source_ref"] for r in cur.fetchall()]
            if refs:
                check("fact provenance spans the whole exchange",
                      refs, [f"raw:{uid}-{aid}"])
            cur.execute("SELECT id, trace, exchange_start, exchange_end FROM episodes "
                        "WHERE exchange_start = ANY(%s) OR exchange_end = ANY(%s)",
                        ([uid, aid], [uid, aid]))
            eps = cur.fetchall()
            check("at most one episode for the exchange", len(eps) <= 1)
            if eps:
                check("the episode spans prompt..reply",
                      (eps[0]["exchange_start"], eps[0]["exchange_end"]), (uid, aid))
                print(f"\n  trace: {eps[0]['trace'][:260]}\n")
            else:
                print(f"\n  (gate scored {judged[0]['salience']} — facts only, "
                      f"no episode; pairing still proven by the single verdict)\n")


def cron_end_to_end() -> None:
    """A clock wakes the agent: one episode, solitary, no personified job."""
    scope = "madtest"
    stamp = f"cron-{int(time.time())}"
    print("end-to-end, cron wake-up (writes to 'madtest', spends LLM calls)...")

    job = memory.retain(
        scope, "user",
        f"[Cron: Gremlin Watch Digest] Check the channels and report anything "
        f"that genuinely needs Jess. [{stamp}]", speaker_name="cron")
    time.sleep(0.4)
    said = memory.retain(
        scope, "agent",
        f"Went through every channel. Community's clean, nothing needed her "
        f"tonight. Quiet feels like a kindness. [{stamp}]", speaker_name="Rowan")

    for _ in range(90):
        time.sleep(2)
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM raw_exchanges WHERE "
                            "id = ANY(%s) AND extracted_at IS NOT NULL",
                            ([job, said],))
                if cur.fetchone()["n"] == 2:
                    break

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, trace, exchange_start, exchange_end FROM episodes "
                        "WHERE exchange_start = ANY(%s) OR exchange_end = ANY(%s)",
                        ([job, said], [job, said]))
            eps = cur.fetchall()
            check("at most one episode from a cron wake-up", len(eps) <= 1)
            if eps:
                ep = eps[0]
                check("the episode is the agent's turn alone, not a pair",
                      (ep["exchange_start"], ep["exchange_end"]), (said, said))
                low = ep["trace"].lower()
                check("the job is not personified as an actor",
                      any(p in low for p in ("cron said", "cron asked",
                                             "cron rehearsed", "cron wanted",
                                             "cron imagined", "cron felt")), False)
                check("no refusal token leaked into the memory",
                      "cron_deferred" in low, False)
                print(f"\n  trace: {ep['trace'][:260]}\n")
            cur.execute("SELECT count(*) AS n FROM episodes WHERE exchange_start=%s",
                        (job,))
            check("the bare prompt got no episode of its own",
                  cur.fetchone()["n"], 0)


def main() -> int:
    structural()
    if "--fast" not in sys.argv:
        end_to_end()
        cron_end_to_end()
    total = len(FAILURES)
    print(f"\n{'ALL PASS' if not total else str(total) + ' FAILURE(S): ' + str(FAILURES)}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
