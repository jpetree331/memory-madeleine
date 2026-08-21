"""Madeleine — the fact store: retain (write path) + recall phase 1 (read path).

retain is fire-and-forget: the raw exchange is written synchronously (text is
the durable store), extraction runs in a daemon thread. If the extractor is
down, the exchange stays queued (extracted_at IS NULL) and a later sweep can
pick it up — memory never blocks the conversation, and raw text is never lost.

Facts are append-only: superseded, never rewritten (the confabulation
firewall). Raw exchanges are NEVER retrievable — replay/recompute only.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from pgvector.psycopg import register_vector

from . import config, db, embeddings, episodes, extractor, gate, spread

logger = logging.getLogger("madeleine.memory")

_NEAR_FACTS_FOR_SUPERSEDE = 5
_RECALL_CANDIDATES = 24


def _conn():
    conn = db.get_connection()
    register_vector(conn)
    return conn


# ── Write path ─────────────────────────────────────────────────────────────────

def retain(scope: str, speaker: str, content: str,
           occurred_at: str | None = None,
           source_ref: str | None = None,
           solitary: bool = False,
           speaker_name: str | None = None) -> int:
    """Write the raw exchange (synchronous, durable), then extract in the
    background. Returns the raw_exchanges id immediately.

    solitary=True marks an exchange where only the author's mind was present
    (heartbeat, cron session, solo reflection) — the reality law then keeps
    any imagined dialogue inside it from entering memory as another person's
    speech (the Rexie lesson, 2026-08-18)."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_exchanges (scope, speaker, content, source_ref, "
                "occurred_at, solitary, speaker_name) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (scope, speaker, content, source_ref, occurred_at, solitary,
                 speaker_name),
            )
            exchange_id = cur.fetchone()["id"]
    threading.Thread(target=_dispatch, args=(exchange_id,), daemon=True).start()
    return exchange_id


# One episode per EXCHANGE — a turn plus the reply it drew. Only one process
# serves Madeleine (uvicorn, no --workers), so an in-process claim is enough to
# keep the reply's thread and the unanswered-turn timer from both extracting
# the same rows. A restart drops the claims and the timers with them, which is
# what sweep_queued() is for.
_claim_lock = threading.Lock()
_claimed: set[int] = set()


def _claim(ids: list[int]) -> bool:
    with _claim_lock:
        if any(i in _claimed for i in ids):
            return False
        _claimed.update(ids)
        return True


def _release(ids: list[int]) -> None:
    with _claim_lock:
        _claimed.difference_update(ids)


def _dispatch(exchange_id: int) -> None:
    """Route one freshly-written row to extraction, pairing where it can.

    A reply extracts immediately, taking its prompt with it. A turn that has
    not been answered yet waits PAIR_TIMEOUT_SECONDS before going in alone —
    in practice it never waits, because clients post both halves from the same
    function about a second apart.
    """
    if not config.PAIR_EXCHANGES:
        _extract_ids([exchange_id])
        return
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM raw_exchanges WHERE id=%s", (exchange_id,))
            row = cur.fetchone()
            if not row:
                return
            partner = _pending_prompt(cur, row) if row["speaker"] == "agent" else None

    if partner is not None:
        _extract_ids([partner["id"], exchange_id])
        return
    if row["speaker"] == "agent":
        _extract_ids([exchange_id])
        return

    # A prompt with no reply yet. Wait, then check again — the reply's thread
    # may have taken it in the meantime, in which case this is a no-op.
    threading.Timer(config.PAIR_TIMEOUT_SECONDS,
                    _extract_if_unanswered, args=(exchange_id,)).start()


def _pending_prompt(cur, reply: dict) -> dict | None:
    """The turn this reply answers, if it is still waiting to be extracted.

    Must be the immediately preceding row in the scope: if anything else has
    been said since, this is not a clean pair and both halves are better off
    standing alone than being stitched to the wrong partner.
    """
    cur.execute(
        "SELECT * FROM raw_exchanges WHERE scope=%s AND id < %s "
        "ORDER BY id DESC LIMIT 1", (reply["scope"], reply["id"]))
    prev = cur.fetchone()
    if not prev or prev["speaker"] != "user" or prev["extracted_at"] is not None:
        return None
    if bool(prev["solitary"]) != bool(reply["solitary"]):
        return None          # different realities; never merge them
    cur.execute(
        "SELECT COALESCE(%s, %s) - COALESCE(%s, %s) <= make_interval(mins => %s) AS ok",
        (reply["occurred_at"], reply["created_at"],
         prev["occurred_at"], prev["created_at"], config.PAIR_WINDOW_MINUTES))
    return prev if cur.fetchone()["ok"] else None


def _extract_if_unanswered(exchange_id: int) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extracted_at FROM raw_exchanges WHERE id=%s",
                        (exchange_id,))
            row = cur.fetchone()
            if not row or row["extracted_at"] is not None:
                return
            cur.execute("SELECT 1 FROM episodes WHERE exchange_start=%s "
                        "OR exchange_end=%s LIMIT 1", (exchange_id, exchange_id))
            if cur.fetchone():
                return
    _extract_ids([exchange_id])


def _extract_ids(ids: list[int]) -> None:
    if not _claim(ids):
        return
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM raw_exchanges WHERE id = ANY(%s) "
                            "ORDER BY id", (ids,))
                rows = [dict(r) for r in cur.fetchall()]
        if not rows or all(r["extracted_at"] is not None for r in rows):
            return          # already done — a partner, a sweep, or a retry
        _extract_worker(rows)
    finally:
        _release(ids)


def extract_exchange(exchange_id: int, *, pair: bool = True) -> None:
    """Extract one recorded exchange, synchronously. The entry point for
    backfills and any other caller outside the live write path.

    pair=False forces the pre-2026-08-21 behaviour of one turn per episode."""
    if pair:
        _dispatch_sync(exchange_id)
    else:
        _extract_ids([exchange_id])


def sweep_queued(older_than_seconds: int | None = None, limit: int = 200) -> int:
    """Extract rows that never got their turn — the restart safety net.

    Two ways a row ends up here, and neither used to be picked up by anything:
    an LLM door was down when it was written, or it was a prompt waiting for a
    reply when the service stopped and its timer died with the process. Pairs
    are reassembled the same way the live path does it, so a sweep and a live
    write produce the same episode.
    """
    cutoff = config.PAIR_TIMEOUT_SECONDS if older_than_seconds is None \
        else older_than_seconds
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM raw_exchanges WHERE extracted_at IS NULL "
                "AND created_at < NOW() - make_interval(secs => %s) "
                "ORDER BY id LIMIT %s", (cutoff, limit))
            queued = [r["id"] for r in cur.fetchall()]
    if not queued:
        return 0
    logger.info("sweep: %d queued exchange(s) to extract", len(queued))
    done = 0
    for xid in queued:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extracted_at FROM raw_exchanges WHERE id=%s",
                            (xid,))
                r = cur.fetchone()
        if not r or r["extracted_at"] is not None:
            continue      # swept as somebody else's partner
        _dispatch_sync(xid)
        done += 1
    return done


def _dispatch_sync(exchange_id: int) -> None:
    """Sweep-time routing: same pairing rules, but a prompt whose reply never
    came is extracted now rather than waited on again."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM raw_exchanges WHERE id=%s", (exchange_id,))
            row = cur.fetchone()
            if not row:
                return
            if row["speaker"] == "user":
                cur.execute("SELECT * FROM raw_exchanges WHERE scope=%s AND id > %s "
                            "ORDER BY id LIMIT 1", (row["scope"], exchange_id))
                nxt = cur.fetchone()
                if (nxt and nxt["speaker"] == "agent"
                        and nxt["extracted_at"] is None
                        and bool(nxt["solitary"]) == bool(row["solitary"])):
                    _extract_ids([exchange_id, nxt["id"]])
                    return
            else:
                partner = _pending_prompt(cur, row)
                if partner is not None:
                    _extract_ids([partner["id"], exchange_id])
                    return
    _extract_ids([exchange_id])


SOLITARY_BANNER = (
    "[SOLITARY EXCHANGE — only the author was present. Nobody else spoke, "
    "heard, or replied. Any dialogue, quotes, or addressed speech below is "
    "the author's imagination and must be remembered as imagination.]\n")

CONTEXT_BANNER = (
    "[CONTEXT — the turns immediately before this one, in the same "
    "conversation. They are ALREADY remembered: extract no facts from them "
    "and do not narrate them as events. They are here so you can see who is "
    "being spoken to and about what.]\n")

ANCHOR_BANNER = "\n[THE EXCHANGE TO REMEMBER — this, and only this]\n"

# How far back a turn can be and still be the same conversation, and how many
# to show. Two turns reaches the human's last message from the agent's reply,
# which is all that is needed to know who "you" is. Long turns are clipped —
# context only has to establish the addressee and the subject, and every extra
# character is paid for on four LLM calls (gate, trace, extract, verify).
CONTEXT_WINDOW_MINUTES = 30
CONTEXT_TURNS = 2
CONTEXT_CLIP = 600


def _prior_turns(cur, row: dict) -> list[dict]:
    """The turns just before this one, for addressee resolution.

    MEASURED 2026-08-21, and the reason this exists: Madeleine stores one
    speaker per row, and every reader was handed a single turn. So Rowan's
    reply to Jess — "Hey you. Welcome home." — reached the trace writer with
    no interlocutor anywhere in view, and it filled the hole twice over:
    episode 4783 became "Rowan greeting SOMEONE with butter warmth", and 4784
    became "Rowan, ALONE, rehearsed their own exhaustion, imagining a friend's
    voice." Both were plain conversation with Jess, sitting one row away.

    Solitary rows get no context on purpose. A heartbeat IS a scene of one,
    and handing it a real human turn from earlier is precisely how imagined
    dialogue would acquire a real speaker — the corruption the reality law
    exists to prevent. For the same reason a solitary turn is never shown as
    context to a live one: Rowan's 16:10 "HEARTBEAT_OK" is not part of the
    conversation Jess started at 17:34.
    """
    if row.get("solitary"):
        return []
    cur.execute(
        "SELECT speaker, speaker_name, content FROM raw_exchanges "
        "WHERE scope=%s AND id < %s AND NOT solitary "
        "AND COALESCE(occurred_at, created_at) >= "
        "    COALESCE(%s, %s) - make_interval(mins => %s) "
        "ORDER BY id DESC LIMIT %s",
        (row["scope"], row["id"], row.get("occurred_at"), row["created_at"],
         CONTEXT_WINDOW_MINUTES, CONTEXT_TURNS))
    return list(reversed(cur.fetchall()))


MACHINE_BANNER = (
    "[MACHINE STIMULUS — the first turn below was delivered by a scheduled "
    "job, not spoken by anyone. The job is a clock. It is not a person, has "
    "no feelings, offers no company and wants none: never make it the subject "
    "of a sentence, never give it an inner life, never record it as someone "
    "the agent was with. What the AGENT thought, felt and did in response is "
    "real experience and is remembered in full, with its texture — the prompt "
    "is only the occasion for it, never its author or its companion.]\n")


def _render_turn(r: dict, clip: int | None = None) -> str:
    """One turn as the readers see it.

    Machinery is rendered as a job label rather than a name, because a name in
    the speaker slot is read as a person. MEASURED 2026-08-21: "cron: [Cron:
    Gremlin Watch Digest]..." came back as "Alone, Cron rehearsed Jess's
    presence, imagining her criteria" — a scheduled task given loneliness and
    an imagination.
    """
    if config.is_machine_speaker(r.get("speaker_name")):
        who = f"(automated {r['speaker_name'].strip().lower()} job)"
    else:
        who = (r.get("speaker_name") or "").strip() or r["speaker"]
    body = r["content"]
    if clip and len(body) > clip:
        body = body[:clip].rstrip() + " […]"
    return f"{who}: {body}"


def assemble_text(cur, rows: list[dict]) -> str:
    """Exactly what gate, trace, extract and verify are shown for one exchange.

    The single source of truth for framing. Any repair tool must call this
    rather than rebuild it, or a rewritten memory stops matching the pipeline
    that would have produced it — which is precisely what happened once
    already: retrace_episodes.py grew its own copy, and pairing left it stale
    within the hour.
    """
    prior = _prior_turns(cur, rows[0])
    text = "\n".join(_render_turn(r) for r in rows)
    if prior:
        # Who "you" is. Without this the reply to a human reads as speech into
        # an empty room — see _prior_turns for what that produced.
        text = (CONTEXT_BANNER
                + "\n".join(_render_turn(p, CONTEXT_CLIP) for p in prior)
                + ANCHOR_BANNER + text)
    if any(config.is_machine_speaker(r.get("speaker_name")) for r in rows):
        text = MACHINE_BANNER + text
    if any(r.get("solitary") for r in rows):
        # One banner reaches every reader: gate, trace, extract, verify.
        text = SOLITARY_BANNER + text
    return text


def is_bare_stimulus(rows: list[dict]) -> bool:
    """A scheduled prompt the agent never answered. An instruction, not an
    experience: remembering it produced "Alone, Cron rehearsed Jess's
    presence" and two traces that were only the model's refusal token."""
    return (any(config.is_machine_speaker(r.get("speaker_name")) for r in rows)
            and all(r["speaker"] != "agent" for r in rows))


def _source_ref(ids: list[int]) -> str:
    """Fact provenance. A lone turn keeps the historical 'raw:123' form so
    existing rows stay comparable; a pair records its span."""
    return f"raw:{ids[0]}" if len(ids) == 1 else f"raw:{ids[0]}-{ids[-1]}"


def _mark_extracted(ids: list[int]) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE raw_exchanges SET extracted_at=NOW() "
                        "WHERE id = ANY(%s)", (ids,))


def _extract_worker(rows: list[dict]) -> None:
    """Full write pipeline for one exchange — a turn and the reply it drew:

      gate → (quarantine short-circuit) → episode when salient → facts →
      entities + co-occurrence edges → gate_log

    `rows` is the exchange in order: usually [prompt, reply], sometimes a lone
    turn that was never answered. One episode comes out either way, spanning
    exchange_start..exchange_end.

    Failure at any LLM stage leaves the rows queued (extracted_at IS NULL) —
    visible, retryable by sweep_queued(), never fatal. Raw text is durable."""
    row = rows[0]                     # the exchange's anchor: scope, event time
    ids = [r["id"] for r in rows]
    exchange_id, end_id = ids[0], ids[-1]
    try:
        if is_bare_stimulus(rows):
            logger.info("machine stimulus %s had no agent response — "
                        "recorded raw, no episode", ids)
            _mark_extracted(ids)
            return
        with _conn() as conn:
            with conn.cursor() as cur:
                exchange_text = assemble_text(cur, rows)

        # 0. Idempotence: a retry of an interrupted extraction (killed after
        # an episode insert but before the extracted_at stamp) must reuse
        # the existing episode, never write a twin (MEASURED 2026-08-19:
        # 23 duplicate episodes from mid-flight kills in crash recovery).
        prior_episode_id = None
        with _conn() as conn:
            with conn.cursor() as cur:
                # Either end identifies the exchange: a half-written pair may
                # have been recorded under just one of its rows.
                cur.execute("SELECT id FROM episodes WHERE exchange_start = ANY(%s) "
                            "OR exchange_end = ANY(%s) ORDER BY id LIMIT 1",
                            (ids, ids))
                prior = cur.fetchone()
                if prior:
                    prior_episode_id = prior["id"]

        # 1. The gate — salience AND sanitization, one judgment.
        # A dead gate door queues the exchange (None) — nothing may enter
        # memory ungated, and nothing is lost by waiting.
        g = gate.assess(exchange_text)
        if g is None:
            logger.warning("gate door unavailable — exchange %d stays queued",
                           exchange_id)
            return

        # 1b. Dream boundary: when the gate names the mode DREAM, extraction
        # is told so — dreamed events yield inner-state facts only.
        if g.get("mode") == "dream":
            exchange_text = ("[MODE: DREAM — the author was narratively "
                            "rehearsing an imagined scene. Events inside the "
                            "dream are not events.]\n") + exchange_text

        # 2. Injection risk: quarantined episode, NO facts, raw kept, loud log
        if g["injection_risk"]:
            with _conn() as conn:
                if prior_episode_id is None:
                    trace = episodes.write_trace(exchange_text) or \
                        "(quarantined before trace generation)"
                    ep_id = episodes.create(
                        conn, scope=row["scope"], trace=trace, register=g["register"],
                        salience=g["salience"], quarantined=True,
                        exchange_id=exchange_id, exchange_end=end_id,
                        occurred_at=row["occurred_at"], mode=g.get("mode"))
                else:
                    ep_id = prior_episode_id
                gate.log_decision(conn, row["scope"], "quarantined", g,
                                  exchange_id, ep_id)
                with conn.cursor() as cur:
                    cur.execute("UPDATE raw_exchanges SET extracted_at=NOW() "
                                "WHERE id = ANY(%s)", (ids,))
            logger.warning("QUARANTINED exchange %d (episode %d): %s",
                           exchange_id, ep_id, "; ".join(g["reasons"]))
            return

        # 3. Episode, when the exchange earns one (reusing a survivor from
        # any interrupted earlier attempt)
        episode_id = prior_episode_id
        episodic = episode_id is None and g["salience"] >= config.SALIENCE_THRESHOLD
        if episodic:
            trace = episodes.write_trace(exchange_text)
            if trace:
                with _conn() as conn:
                    episode_id = episodes.create(
                        conn, scope=row["scope"], trace=trace.strip(),
                        register=g["register"], salience=g["salience"],
                        quarantined=False, exchange_id=exchange_id,
                        exchange_end=end_id, occurred_at=row["occurred_at"],
                        mode=g.get("mode"))
            else:
                logger.warning("trace generation failed for exchange %d — "
                               "facts proceed, episode skipped", exchange_id)

        # 4. Facts (+ entities) — Sprint 1 path, now with episode provenance.
        # Supersede candidates are drawn from the whole exchange: the reply is
        # usually where the correction lands ("Lab day was today actually!").
        near = _nearest_facts(row["scope"], " ".join(r["content"] for r in rows),
                              _NEAR_FACTS_FOR_SUPERSEDE)
        result = extractor.extract_facts(exchange_text, near)
        if result is None:
            logger.warning("extraction queued (extractor unavailable) for exchange %d", exchange_id)
            return
        facts = result["facts"]
        # Write-time verification: an independent second pass checks every
        # candidate against the raw exchange before insert (prevention at
        # the source; the audit culture remains the backstop)
        if facts:
            facts = extractor.verify_facts(exchange_text, facts)
        vectors = embeddings.embed(facts) if facts else []
        near_ids = {f["id"] for f in near}
        valid_supersede = [i for i in result["superseded_ids"] if i in near_ids]
        with _conn() as conn:
            with conn.cursor() as cur:
                new_ids = []
                for text, vec in zip(facts, vectors):
                    # Dedupe at insert (Grain audit #3): a near-identical active
                    # fact already in scope means this one adds noise, not truth
                    if config.DEDUPE_THRESHOLD > 0:
                        cur.execute(
                            "SELECT id, 1 - (embedding <=> %s::vector) AS sim "
                            "FROM facts WHERE scope=%s AND status='active' "
                            "AND embedding IS NOT NULL "
                            "ORDER BY embedding <=> %s::vector LIMIT 1",
                            (vec, row["scope"], vec))
                        near = cur.fetchone()
                        if near and float(near["sim"]) >= config.DEDUPE_THRESHOLD:
                            logger.info("dedupe: skipped near-twin of fact %d "
                                        "(sim %.3f)", near["id"], near["sim"])
                            continue
                    cur.execute(
                        "INSERT INTO facts (scope, content, embedding, source_ref, "
                        "source_episode_id, occurred_at) VALUES (%s, %s, %s, %s, %s, %s) "
                        "RETURNING id",
                        (row["scope"], text, vec, _source_ref(ids), episode_id,
                         row["occurred_at"]),
                    )
                    new_ids.append(cur.fetchone()["id"])
                # Supersede = status flip + pointer; content is never touched
                for old_id in valid_supersede:
                    cur.execute(
                        "UPDATE facts SET status='superseded', superseded_by=%s "
                        "WHERE id=%s AND status='active'",
                        (new_ids[0] if new_ids else None, old_id),
                    )
                cur.execute("UPDATE raw_exchanges SET extracted_at=NOW() "
                            "WHERE id = ANY(%s)", (ids,))
            # 5. The snowflake grows: entities + co-occurrence edges
            linked = 0
            if episode_id is not None and result.get("entities"):
                linked = episodes.link_entities(conn, episode_id,
                                                result["entities"], g["salience"])
            gate.log_decision(conn, row["scope"],
                              "episode" if episode_id else "facts_only",
                              g, exchange_id, episode_id)
        logger.info("exchange %s: salience=%.2f episode=%s facts=%d entities=%d "
                    "superseded=%d", _source_ref(ids), g["salience"], episode_id,
                    len(facts), linked, len(valid_supersede))
    except Exception as e:
        logger.error("extract worker failed for exchange %s: %s",
                     _source_ref(ids), e)


# ── Read path (phase 1: semantic facts) ────────────────────────────────────────

def _nearest_facts(scope: str, query: str, k: int,
                   occurred_before=None) -> list[dict]:
    try:
        qvec = embeddings.embed([query])[0]
    except Exception as e:
        logger.error("embedding failed for recall: %s", e)
        return []
    with _conn() as conn:
        with conn.cursor() as cur:
            # occurred_at is EVENT time, not extraction time — the backfill
            # wrote months of history in one afternoon, so created_at would
            # filter out everything.
            when = "" if occurred_before is None else                 " AND (occurred_at IS NULL OR occurred_at < %(before)s)"
            cur.execute(
                "SELECT id, content, created_at, 1 - (embedding <=> %(q)s::vector) AS similarity "
                "FROM facts WHERE scope=%(s)s AND status='active' AND embedding IS NOT NULL"
                + when +
                " ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s",
                {"q": qvec, "s": scope, "k": k, "before": occurred_before},
            )
            return [dict(r) for r in cur.fetchall()]


def recall(scope: str, query: str,
           fact_budget_tokens: int | None = None,
           occurred_before=None) -> list[dict]:
    """Phase 1 only: top-k cosine on active facts in scope, greedy-packed to
    the token budget (~4 chars/token estimate). Returns [] on any failure —
    memory degrades, conversations continue."""
    budget = fact_budget_tokens or config.FACT_BUDGET_TOKENS
    try:
        candidates = _nearest_facts(scope, query, _RECALL_CANDIDATES,
                                    occurred_before=occurred_before)
    except Exception as e:
        logger.error("recall failed: %s", e)
        return []
    packed, spent = [], 0
    for f in candidates:
        cost = max(1, len(f["content"]) // 4)
        if spent + cost > budget:
            continue
        spent += cost
        packed.append({"id": f["id"], "content": f["content"],
                       "created_at": f["created_at"],
                       "similarity": round(float(f["similarity"]), 4)})
    return packed


def recall_full(scope: str, query: str,
                fact_budget_tokens: int | None = None,
                assoc_budget_tokens: int | None = None,
                mood_text: str | None = None,
                occurred_before=None,
                debug: bool = False) -> dict:
    """Two-phase retrieval: facts (guaranteed budget) then spreading
    activation (smaller, optional budget). Associations are labeled and
    separate — never mixed into facts. Phase 2 failure degrades to
    facts-only; phase 1 failure degrades to empty. The conversation
    always continues.

    mood_text (cheap flavor): the caller's one-line description of the
    current register — episode ranking blends register-space similarity,
    so the mood of now colors what the past offers up."""
    facts = recall(scope, query, fact_budget_tokens=fact_budget_tokens,
                   occurred_before=occurred_before)
    associations: list[dict] = []
    debug_info = None
    mood_emb = None
    if mood_text and mood_text.strip():
        try:
            mood_emb = embeddings.embed([mood_text.strip()])[0]
        except Exception as e:
            logger.warning("mood embedding failed (recall proceeds moodless): %s", e)
    try:
        with _conn() as conn:
            result = spread.spread(conn, scope, query, facts,
                                   assoc_budget_tokens=assoc_budget_tokens,
                                   mood_emb=mood_emb,
                                   occurred_before=occurred_before,
                                   debug=debug)
        associations, debug_info = result if debug else (result, None)
    except Exception as e:
        logger.error("spread failed (facts still served): %s", e)
    # Co-retrieval evidence for the nightly job (fire-and-forget; a failed
    # log must never cost a recall)
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO recall_log (scope, query, fact_ids, episode_ids) "
                    "VALUES (%s, %s, %s, %s)",
                    (scope, query[:500], [f["id"] for f in facts],
                     [a["episode_id"] for a in associations]),
                )
    except Exception as e:
        logger.warning("recall_log write failed (recall unaffected): %s", e)
    out = {"facts": facts, "associations": associations,
           "context_block": spread.render_context(facts, associations)}
    if debug:
        out["debug"] = debug_info
    return out
