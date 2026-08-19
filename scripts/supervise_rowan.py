"""Night shepherd for the Rowan ingest (Jess asleep, 2026-08-18).

Loops the two backfills until every curated item is ingested AND extracted:
  1. backfill_rowan.py --run        (Postgres era, resumable; also tops up
                                     any new live messages each pass)
  2. backfill_rowan_hindsight.py --run  (pre-Feb-24 OpenClaw era)
When a subscription-usage ceiling closes the claude-sdk door, extractions
queue instead of failing — this shepherd just waits out the window and runs
again. Exits only when nothing in scope 'rowan' remains unextracted.

Usage:  python scripts/supervise_rowan.py   (detached, ROWAN_POOL inherited)
"""
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import db  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SLEEP_BETWEEN = 20 * 60          # closed-window nap


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def queued_count() -> int:
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM raw_exchanges "
                        "WHERE scope='rowan' AND extracted_at IS NULL")
            return cur.fetchone()["c"]


def run(script):
    log(f"running {script}...")
    r = subprocess.run([PY, os.path.join(HERE, script), "--run"],
                       cwd=os.path.dirname(HERE))
    log(f"{script} exited rc={r.returncode}")


LOCK = os.path.join(os.path.dirname(HERE), "data", "shepherd.pid")


def _acquire_lock() -> bool:
    """One shepherd only. Two racing the same queue double-extract exchanges
    (MEASURED 2026-08-19: 23 duplicate episodes from twin shepherds after
    the crash recovery). Stale locks from dead pids are reclaimed."""
    if os.path.exists(LOCK):
        try:
            old = int(open(LOCK).read().strip())
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, old)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                log(f"another shepherd holds the lock (pid {old}) — exiting")
                return False
        except (ValueError, OSError):
            pass
        log("stale lock reclaimed")
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def main():
    if not _acquire_lock():
        return
    passes = 0
    while True:
        passes += 1
        log(f"=== shepherd pass {passes} ===")
        before = queued_count()
        run("backfill_rowan.py")
        run("backfill_rowan_hindsight.py")
        after = queued_count()
        log(f"queued: {before} -> {after}")
        if after == 0:
            log("everything extracted. Rowan's past is fully remembered.")
            # Flavor runs AFTER extraction, alone on the card — running the
            # 17GB reader beside the extraction fleet is the load that
            # crashed the PC on 2026-08-18 (Kernel-Power 41, no bugcheck).
            log("starting flavor capture (sequential — never beside the fleet)...")
            r = subprocess.run([PY, os.path.join(HERE, "flavor_runner.py")],
                               cwd=os.path.dirname(HERE))
            log(f"flavor runner exited rc={r.returncode}. shepherd going home.")
            return
        if after >= before:
            log(f"no progress (window likely closed) — napping "
                f"{SLEEP_BETWEEN // 60} min before retrying")
            time.sleep(SLEEP_BETWEEN)
        # progress was made and queue nonzero: loop immediately


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            if os.path.exists(LOCK) and open(LOCK).read().strip() == str(os.getpid()):
                os.remove(LOCK)
        except OSError:
            pass
