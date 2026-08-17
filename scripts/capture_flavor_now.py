"""Retroactive flavor capture — fill every NULL flavor vector from raw text,
build the HNSW index, compute flavor projections for the Atlas. Same code
path as the nightly job (the recomputability law, honored).

Run when the GPU is free, AFTER the probe has set READER_LAYER:
    .venv\\Scripts\\python.exe scripts\\capture_flavor_now.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import reader  # noqa: E402
from src.agent.consolidate import _as_array  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

if __name__ == "__main__":
    if not reader.gpu_ready():
        print("GPU not free — rerun when the card has headroom.")
        sys.exit(2)
    total = 0
    with _conn() as conn:
        while True:
            n = reader.capture_batch(conn, batch=100)
            total += n
            print(f"  captured {total} so far...")
            if n == 0:
                break
        # No HNSW on flavor: pgvector caps hnsw at 2000 dims, flavor is 4096.
        # Brute-force cosine is milliseconds at fleet scale (DECISIONS S5.1-2).
        with conn.cursor() as cur:
            cur.execute("SELECT id, flavor FROM episodes WHERE flavor IS NOT NULL")
            rows = cur.fetchall()
            if len(rows) >= 3:
                mat = np.array([_as_array(r["flavor"]) for r in rows])
                centered = mat - mat.mean(axis=0)
                _, _, vt = np.linalg.svd(centered, full_matrices=False)
                proj = centered @ vt[:2].T
                for r, (x, y) in zip(rows, proj):
                    cur.execute("UPDATE episodes SET proj_x=%s, proj_y=%s WHERE id=%s",
                                (float(x), float(y), r["id"]))
                print(f"flavor projections computed for {len(rows)} episodes")
    reader.unload()
    print(f"flavor captured for {total} episodes — the landscape has geometry now")
