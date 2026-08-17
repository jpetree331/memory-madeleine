"""Madeleine — spreading activation: the retrieval nobody ships.

The current turn activates a few nodes; activation propagates along
co-occurrence edges with per-hop decay; whatever crosses threshold enters
context — INCLUDING episodes with zero embedding similarity to the query.
This is the machine equivalent of "this reminds me of..." — the snowflake
doing its job. The design's acceptance test: query the song, surface the car.

Traversal law: quarantined episodes and episodes below strength 0.1 never
conduct and never surface. Final results are scope-filtered (entities are
global connectors, but only the scope's own episodes may surface — the
privacy-silo stance). Anything returned from here is an ASSOCIATION, labeled
as such, never mixed into facts.

Neighborhood loading: two batched IN-queries per hop (src side + dst side),
not a recursive CTE — sanctioned by the plan; chosen for debuggability (the
Observatory's recall debugger wants per-hop activations, which a CTE hides).
"""
from __future__ import annotations

import logging

from . import config

logger = logging.getLogger("madeleine.spread")


def _seed_from_query(conn, query: str) -> dict:
    """Entities whose key or name appears in the query text (simple match —
    the plan sanctions this over an extractor-lite call; revisit if it
    underseeds). Seed activation 1.0."""
    seeds = {}
    q = query.lower()
    with conn.cursor() as cur:
        cur.execute("SELECT id, key, name FROM entities")
        for row in cur.fetchall():
            key_words = row["key"].replace("-", " ")
            if key_words in q or (row["name"] and row["name"].lower() in q):
                seeds[("entity", row["id"])] = 1.0
    return seeds


def _seed_from_fact_hits(conn, fact_hits: list[dict]) -> dict:
    """Episodes that produced the phase-1 facts join the seed set — the
    provenance pointers are the crucial join between the two layers."""
    seeds = {}
    ids = [f["id"] for f in fact_hits]
    if not ids:
        return seeds
    with conn.cursor() as cur:
        cur.execute("SELECT id, source_episode_id FROM facts "
                    "WHERE id = ANY(%s) AND source_episode_id IS NOT NULL", (ids,))
        for row in cur.fetchall():
            seeds[("episode", row["source_episode_id"])] = 1.0
    return seeds


def _load_neighbors(conn, frontier: list[tuple[str, int]]) -> list[dict]:
    """All edges touching the frontier, both directions, two batched queries."""
    by_kind: dict[str, list[int]] = {}
    for kind, node_id in frontier:
        by_kind.setdefault(kind, []).append(node_id)
    edges = []
    with conn.cursor() as cur:
        for kind, ids in by_kind.items():
            cur.execute(
                "SELECT src_kind, src_id, dst_kind, dst_id, weight FROM edges "
                "WHERE (src_kind = %s AND src_id = ANY(%s)) "
                "   OR (dst_kind = %s AND dst_id = ANY(%s))",
                (kind, ids, kind, ids),
            )
            edges.extend(cur.fetchall())
    return edges


def _conducting_episodes(conn, episode_ids: set[int], scope: str) -> dict[int, dict]:
    """Episode metadata for traversal/surfacing rules. Quarantined or
    sub-strength episodes are simply absent — they neither conduct nor surface."""
    if not episode_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, scope, trace, register, salience, strength, occurred_at "
            "FROM episodes WHERE id = ANY(%s) AND NOT quarantined AND strength >= 0.1",
            (list(episode_ids),),
        )
        return {r["id"]: dict(r) for r in cur.fetchall()}


def spread(conn, scope: str, query: str, fact_hits: list[dict],
           assoc_budget_tokens: int | None = None,
           debug: bool = False) -> list[dict] | tuple[list[dict], dict]:
    """Run activation spread; return budget-packed associations
    (and the per-hop trace when debug=True — the Observatory's debugger)."""
    budget = assoc_budget_tokens or config.ASSOC_BUDGET_TOKENS
    activation: dict = {}
    activation.update(_seed_from_query(conn, query))
    activation.update(_seed_from_fact_hits(conn, fact_hits))
    debug_info: dict = {"seeds": [f"{k}:{i}" for (k, i) in activation], "hops": []}
    if not activation:
        return ([], debug_info) if debug else []

    frontier = dict(activation)
    episode_meta: dict[int, dict] = {}
    for hop in range(config.SPREAD_HOPS):
        if not frontier:
            break
        edges = _load_neighbors(conn, list(frontier.keys()))
        # Episode metadata for every episode endpoint this hop (conduction rules)
        ep_ids = {e["src_id"] for e in edges if e["src_kind"] == "episode"} | \
                 {e["dst_id"] for e in edges if e["dst_kind"] == "episode"}
        episode_meta.update(_conducting_episodes(conn, ep_ids - set(episode_meta), scope))
        next_frontier: dict = {}
        hop_log = []
        for e in edges:
            for (fk, fi), (tk, ti) in (
                ((e["src_kind"], e["src_id"]), (e["dst_kind"], e["dst_id"])),
                ((e["dst_kind"], e["dst_id"]), (e["src_kind"], e["src_id"])),
            ):
                src_act = frontier.get((fk, fi))
                if src_act is None:
                    continue
                new_act = src_act * config.SPREAD_DECAY * min(float(e["weight"]), 2.0)
                if tk == "episode":
                    meta = episode_meta.get(ti)
                    if meta is None:      # quarantined / weak / unknown: no conduction
                        continue
                    new_act *= meta["strength"]
                if new_act <= activation.get((tk, ti), 0.0):
                    continue
                activation[(tk, ti)] = new_act
                next_frontier[(tk, ti)] = new_act
                hop_log.append({"node": f"{tk}:{ti}", "activation": round(new_act, 4)})
        debug_info["hops"].append(hop_log)
        frontier = next_frontier

    # Collect: episodes above threshold, in scope, ranked activation × salience
    candidates = []
    for (kind, node_id), act in activation.items():
        if kind != "episode" or act < config.SPREAD_THRESHOLD:
            continue
        meta = episode_meta.get(node_id)
        if meta is None or meta["scope"] != scope:
            continue
        candidates.append({**meta, "activation": act,
                           "rank": act * meta["salience"]})
    candidates.sort(key=lambda c: c["rank"], reverse=True)

    packed, spent = [], 0
    for c in candidates:
        cost = max(1, len(c["trace"]) // 4)
        if spent + cost > budget:
            continue
        spent += cost
        packed.append({"episode_id": c["id"], "trace": c["trace"],
                       "register": c["register"], "occurred_at": c["occurred_at"],
                       "activation": round(float(c["activation"]), 4)})

    # Recall strengthens: memory learns from being used
    if packed:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE episodes SET recall_count = recall_count + 1, "
                "last_recalled_at = NOW(), strength = LEAST(strength + 0.1, 2.0) "
                "WHERE id = ANY(%s)",
                ([p["episode_id"] for p in packed],),
            )
    debug_info["candidates"] = len(candidates)
    debug_info["packed"] = len(packed)
    return (packed, debug_info) if debug else packed


def render_context(facts: list[dict], associations: list[dict]) -> str:
    """The labeled context block — graph output is color, never citation."""
    lines = []
    if facts:
        lines.append("## Remembered facts")
        lines += [f"- {f['content']}" for f in facts]
    if associations:
        lines.append("\n## Associations (impressions surfaced by memory, not verified facts)")
        lines += [f"- impression: {a['trace']}" for a in associations]
    return "\n".join(lines)
