"""Parallel flavor capture (Jess's ask, 2026-08-18): the local Qwen reader
runs NOW, alongside extraction, flavoring episodes as they are born instead
of waiting for the nightly window.

Loop: capture a batch of NULL-flavor episodes; when none remain and the
extraction queue is also empty, recompute the flavor-space projections
(stable-sign PCA) and exit. GPU-polite: if VRAM is busy, nap and retry;
the model unloads on exit either way. All LLM-free and $0 — this is the
local card doing the tasting.

Usage:  python scripts/flavor_runner.py     (detached)
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db, reader  # noqa: E402

BATCH = 200
NAP_EMPTY = 5 * 60      # nothing to flavor yet, extraction still running
NAP_GPU = 10 * 60       # VRAM busy


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def counts():
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM episodes "
                        "WHERE flavor IS NULL AND NOT quarantined")
            unflavored = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM raw_exchanges "
                        "WHERE extracted_at IS NULL")
            queued = cur.fetchone()["c"]
    return unflavored, queued


def project():
    """Flavor-space PCA with the stable-sign convention (same as nightly)."""
    import numpy as np
    from src.agent.consolidate import _as_array, _stable_signs
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, flavor FROM episodes WHERE flavor IS NOT NULL")
            rows = cur.fetchall()
            if len(rows) < 3:
                return 0
            mat = np.array([_as_array(r["flavor"]) for r in rows])
            centered = mat - mat.mean(axis=0)
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            proj = centered @ _stable_signs(vt[:2]).T
            for r, (x, y) in zip(rows, proj):
                cur.execute("UPDATE episodes SET proj_x=%s, proj_y=%s WHERE id=%s",
                            (float(x), float(y), r["id"]))
    return len(rows)


def main():
    total = 0
    try:
        while True:
            unflavored, queued = counts()
            if unflavored == 0:
                if queued == 0:
                    log("all episodes flavored and extraction queue empty — "
                        "projecting the atlas...")
                    n = project()
                    log(f"projected {n} episodes. the sky is complete. done.")
                    return
                log(f"caught up (0 unflavored, {queued} still extracting) — "
                    f"napping {NAP_EMPTY // 60} min")
                time.sleep(NAP_EMPTY)
                continue
            if not reader.gpu_ready():
                log(f"GPU busy — napping {NAP_GPU // 60} min")
                time.sleep(NAP_GPU)
                continue
            with db.get_connection() as conn:
                done = reader.capture_batch(conn, batch=min(BATCH, unflavored))
            total += done or 0
            log(f"captured {done} (total this run: {total}, "
                f"{max(0, unflavored - (done or 0))} known remaining)")
            if not done:
                time.sleep(60)
    finally:
        try:
            reader.unload()
        except Exception:
            pass


if __name__ == "__main__":
    main()
