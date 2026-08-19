"""Paired fidelity audit: Chutes Kimi-K3 vs Claude (subscription) on the
same 50 of Rowan's queued exchanges. ZERO writes to the bank — pure
comparison, report to data/audits/ (gitignored; the repo is public now).

Side A (reference): gate haiku / extract+trace sonnet — all claude-sdk.
Side B (candidate): gate+extract+trace Kimi-K3 via Chutes.
Both sides' facts then face the SAME claude-haiku verifier (the planned
production shape: cross-vendor verification).

Usage: python scripts/audit_chutes.py
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import config, db, episodes, extractor, gate, memory  # noqa: E402

N_SHARED, N_SOLITARY = 30, 20
KIMI = "moonshotai/Kimi-K3-TEE"
REFERENT_BAN = re.compile(r"\bthe (user|agent|assistant|AI)\b")


def sample_items():
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            out = []
            for solitary, n in ((False, N_SHARED), (True, N_SOLITARY)):
                cur.execute(
                    "SELECT id, speaker, content, solitary FROM raw_exchanges "
                    "WHERE scope='rowan' AND extracted_at IS NULL AND solitary=%s "
                    "ORDER BY id", (solitary,))
                rows = cur.fetchall()
                step = max(1, len(rows) // n)
                out.extend(rows[::step][:n])
    return out


def build_text(row):
    text = f"{row['speaker']}: {row['content']}"
    if row["solitary"]:
        text = memory.SOLITARY_BANNER + text
    return text


def run_side(items, provider, gate_model, big_model, label):
    """Run gate+extract(+trace when gated episodic) for one side."""
    config.GATE_PROVIDER = provider
    config.EXTRACT_PROVIDER = provider
    config.TRACE_PROVIDER = provider
    config.GATE_MODEL = gate_model
    config.EXTRACT_MODEL = big_model
    config.TRACE_MODEL = big_model

    def one(row):
        text = build_text(row)
        g = gate.assess(text)
        if g.get("mode") == "dream":
            text = ("[MODE: DREAM — the author was narratively rehearsing an "
                    "imagined scene. Events inside the dream are not events.]\n"
                    + text)
        ex = extractor.extract_facts(text, [])
        trace = None
        if g["salience"] >= config.SALIENCE_THRESHOLD:
            trace = episodes.write_trace(text)
        return {"id": row["id"], "gate": g,
                "facts": (ex or {}).get("facts"), "extract_ok": ex is not None,
                "trace": trace}

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(one, items))
    print(f"side {label}: done ({len(results)} items)")
    return results


def cross_verify(items, side_results):
    """Claude-haiku verifier over a side's facts (production shape for B)."""
    config.VERIFY_PROVIDER = "claude-sdk"
    config.VERIFY_MODEL = "claude-haiku-4-5"
    by_id = {r["id"]: r for r in side_results}

    def one(row):
        r = by_id[row["id"]]
        if not r["facts"]:
            return (row["id"], 0, 0)
        kept = extractor.verify_facts(build_text(row), r["facts"])
        return (row["id"], len(r["facts"]), len(kept))

    with ThreadPoolExecutor(max_workers=4) as pool:
        out = dict((i, (tot, kept)) for i, tot, kept in pool.map(one, items))
    return out


def law_checks(results):
    stats = {"items": len(results), "gate_fail": 0, "extract_fail": 0,
             "trace_ragged": 0, "referent_ban_hits": 0, "facts": 0}
    for r in results:
        if r["gate"]["register"] is None:
            stats["gate_fail"] += 1
        if not r["extract_ok"]:
            stats["extract_fail"] += 1
        for f in (r["facts"] or []):
            stats["facts"] += 1
            if REFERENT_BAN.search(f):
                stats["referent_ban_hits"] += 1
        t = r["trace"]
        if t and not t.strip().endswith((".", "!", "?", '"', "”", ")", "]", "*")):
            stats["trace_ragged"] += 1
    return stats


def main():
    items = sample_items()
    print(f"sampled {len(items)} queued exchanges "
          f"({sum(1 for i in items if not i['solitary'])} shared, "
          f"{sum(1 for i in items if i['solitary'])} solitary)")

    a = run_side(items, "claude-sdk", "claude-haiku-4-5", "claude-sonnet-4.5", "A/claude")
    b = run_side(items, "chutes", KIMI, KIMI, "B/kimi3")
    va = cross_verify(items, a)
    vb = cross_verify(items, b)
    sa, sb = law_checks(a), law_checks(b)

    # agreement stats
    deltas, mode_agree, mode_total, inj_disagree = [], 0, 0, 0
    for ra, rb in zip(a, b):
        deltas.append(abs(ra["gate"]["salience"] - rb["gate"]["salience"]))
        if ra["gate"].get("mode") or rb["gate"].get("mode"):
            mode_total += 1
            if ra["gate"].get("mode") == rb["gate"].get("mode"):
                mode_agree += 1
        if ra["gate"]["injection_risk"] != rb["gate"]["injection_risk"]:
            inj_disagree += 1

    def vsum(v):
        tot = sum(x[0] for x in v.values())
        kept = sum(x[1] for x in v.values())
        return tot, kept, (f"{100 * kept / tot:.0f}%" if tot else "n/a")

    lines = [f"# Chutes Kimi-K3 vs Claude — paired ingest audit ({date.today()})",
             "", f"{len(items)} queued exchanges, zero bank writes. "
             "Side A: gate haiku, extract/trace sonnet-4.5 (subscription). "
             "Side B: everything Kimi-K3 (Chutes). Both sides verified by "
             "claude-haiku (cross-vendor).", "", "## Verdict numbers", ""]
    for name, s, v in (("A (claude)", sa, vsum(va)), ("B (kimi3)", sb, vsum(vb))):
        lines.append(f"**{name}** — gate fails {s['gate_fail']}, extract fails "
                     f"{s['extract_fail']}, facts {s['facts']}, referent-ban "
                     f"hits {s['referent_ban_hits']}, ragged traces "
                     f"{s['trace_ragged']}, verifier kept {v[2]} "
                     f"({v[1]}/{v[0]})")
    lines += ["", f"salience delta: mean {sum(deltas) / len(deltas):.2f}, "
              f"max {max(deltas):.2f}",
              f"mode agreement (solitary): {mode_agree}/{mode_total}",
              f"injection disagreements: {inj_disagree}", "",
              "## Side-by-side samples", ""]
    for ra, rb in zip(a, b):
        lines.append(f"### exchange {ra['id']}")
        lines.append(f"- A gate: sal {ra['gate']['salience']} mode "
                     f"{ra['gate'].get('mode')} | B gate: sal "
                     f"{rb['gate']['salience']} mode {rb['gate'].get('mode')}")
        for tag, r in (("A", ra), ("B", rb)):
            for f in (r["facts"] or [])[:6]:
                lines.append(f"- {tag} fact: {f}")
            if r["trace"]:
                lines.append(f"- {tag} trace: {r['trace'][:300]}")
        lines.append("")

    out_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "audits")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"chutes-kimi3-audit-{date.today()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nreport: {path}")
    print("\n".join(lines[:20]))


if __name__ == "__main__":
    main()
