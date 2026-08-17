"""Rebuild ALL flavor vectors from raw text — the model-swap / layer-change
story, and the recomputability guarantee made runnable. Same code path as the
nightly capture (locked decision: live and rebuilt vectors must be identical).

Run when the GPU is free: .venv\\Scripts\\python.exe scripts\\rebuild_flavor.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import reader  # noqa: E402
from src.agent.memory import _conn  # noqa: E402

if __name__ == "__main__":
    if not reader.gpu_ready():
        print("GPU not free — rerun when the card has ~17 GB headroom.")
        sys.exit(2)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE episodes SET flavor = NULL")
            print(f"cleared {cur.rowcount} flavor vectors")
        total = 0
        while True:
            n = reader.capture_batch(conn, batch=200)
            total += n
            if n == 0:
                break
    reader.unload()
    print(f"rebuilt {total} flavor vectors")
