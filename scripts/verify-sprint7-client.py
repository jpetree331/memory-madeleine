"""Sprint 7 (partial) VERIFY — client + modes.
  1. madeleine mode: retain lands, recall returns a rendered block.
  2. both mode: recall returns '' (agent stays on legacy reads) but the
     comparison log gains Madeleine's answer — GATE A evidence machinery.
  3. hindsight mode: client fully inert.
Run from repo root."""
import importlib
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []

# 1 — madeleine mode
os.environ["MEMORY_BACKEND"] = "madeleine"
from src.agent import madeleine_client as mc  # noqa: E402
importlib.reload(mc)
ok_retain = mc.retain_exchange("demo", "Client verify: the drop-in door works.",
                               "Confirmed — one client, any host.",
                               user_display_name="Jess", agent_name="Fable")
time.sleep(1)
block = mc.recall("demo", "does the drop-in client door work")
results.append(("1. madeleine mode: retain + rendered recall",
                ok_retain and "Remembered facts" in block,
                f"retain={ok_retain} block_len={len(block)}"))

# 2 — both mode (parallel-run)
log_path = os.path.join(tempfile.gettempdir(), "madeleine_compare_test.log")
if os.path.exists(log_path):
    os.remove(log_path)
os.environ["MEMORY_BACKEND"] = "both"
os.environ["MADELEINE_COMPARE_LOG"] = log_path
importlib.reload(mc)
block_both = mc.recall("demo", "the snowflake test")
logged = os.path.exists(log_path) and "scope=demo" in open(log_path, encoding="utf-8").read()
results.append(("2. both mode: reads stay legacy, comparison logged",
                block_both == "" and logged,
                f"returned_empty={block_both == ''} log_written={logged}"))

# 3 — hindsight mode: inert
os.environ["MEMORY_BACKEND"] = "hindsight"
importlib.reload(mc)
inert = (mc.retain_exchange("demo", "should not land", "nope") is False
         and mc.recall("demo", "anything") == ""
         and mc.recall_structured("demo", "anything") == {"facts": [], "associations": []})
results.append(("3. hindsight mode: fully inert", inert, f"inert={inert}"))

print("\n== Sprint 7 (client) VERIFY ==")
all_ok = True
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
    all_ok &= ok
sys.exit(0 if all_ok else 1)
