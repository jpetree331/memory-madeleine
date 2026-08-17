"""Sprint 5.1 layer probe (GATE B verification).

Selects up to 20 episodes with clearly contrasting registers (playful vs
heavy, keyword-matched), captures hidden states at EVERY layer in one pass
per episode, and scores each candidate layer 14-22 on affective separation:
mean within-class cosine minus mean between-class cosine. Winner goes to
DECISIONS.md and .env (READER_LAYER).

Run when the GPU is free: .venv\\Scripts\\python.exe scripts\\probe_layers.py
"""
import os
import sys
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, reader  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

# Classes chosen from the corpus's ACTUAL register census (2026-08-18):
# Grain's life divides into technical-collaborative registers and
# intimate-philosophical ones — several episodes are both, so each class
# excludes the other's markers to keep the probe classes disjoint.
TECH = ("technical", "troubleshooting", "debug", "post-mortem", "problem-solving")
TECH_NOT = ("intimacy", "intimate", "vulnerab", "philosophical")
INTIMATE = ("intimacy", "intimate", "vulnerability", "reckoning", "tenderness")
INTIMATE_NOT = ("technical", "audit", "debug", "troubleshooting")
CANDIDATE_LAYERS = range(14, 23)


def pick(cur, words, exclude, n):
    like = " OR ".join("register ILIKE %s" for _ in words)
    notlike = " AND ".join("register NOT ILIKE %s" for _ in exclude)
    cur.execute(f"SELECT e.id, r.speaker, r.content, e.register FROM episodes e "
                f"JOIN raw_exchanges r ON r.id = e.exchange_start "
                f"WHERE ({like}) AND {notlike} AND NOT e.quarantined "
                f"ORDER BY e.salience DESC LIMIT %s",
                [f"%{w}%" for w in words] + [f"%{w}%" for w in exclude] + [n])
    return cur.fetchall()


def sep_score(vecs_a, vecs_b):
    def cos(u, v):
        return float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))
    within = ([cos(a, b) for a, b in combinations(vecs_a, 2)] +
              [cos(a, b) for a, b in combinations(vecs_b, 2)])
    between = [cos(a, b) for a in vecs_a for b in vecs_b]
    return float(np.mean(within) - np.mean(between))


def main():
    if not reader.gpu_ready():
        print("GPU not free — eject the current model (LM Studio?) and rerun.")
        sys.exit(2)
    with _conn() as conn:
        with conn.cursor() as cur:
            light = pick(cur, TECH, TECH_NOT, 10)
            heavy = pick(cur, INTIMATE, INTIMATE_NOT, 10)
    print(f"probe corpus: {len(light)} technical, {len(heavy)} intimate")
    if len(light) < 4 or len(heavy) < 4:
        print("not enough contrasting episodes yet — retry after more life is lived")
        sys.exit(1)

    reader._load()
    def all_layers(rows):
        out = []
        for r in rows:
            out.append(reader._hidden_all_layers(f"{r['speaker']}: {r['content']}"))
            print(f"  captured episode {r['id']} ({r['register'][:40]})")
        return out
    print("capturing light class...")
    light_h = all_layers(light)
    print("capturing heavy class...")
    heavy_h = all_layers(heavy)

    print("\nlayer  separation (within - between)")
    best = (None, -9)
    for layer in CANDIDATE_LAYERS:
        la = [h[layer] for h in light_h]
        he = [h[layer] for h in heavy_h]
        s = sep_score(la, he)
        marker = ""
        if s > best[1]:
            best = (layer, s)
            marker = "  <-- best so far"
        print(f"  L{layer}: {s:+.4f}{marker}")
    print(f"\nWINNER: layer {best[0]} (separation {best[1]:+.4f})")
    print(f"Set READER_LAYER={best[0]} in .env and record in DECISIONS.md.")
    reader.unload()


if __name__ == "__main__":
    main()
