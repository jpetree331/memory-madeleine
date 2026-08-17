"""Manual consolidation trigger — same code path as the nightly job.
Run from repo root: .venv\\Scripts\\python.exe scripts\\run_consolidation.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import consolidate  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(consolidate.run(), indent=2))
