"""Madeleine — the deep flavor reader (Sprint 5.1, GATE B: Qwen/Qwen3-8B).

The affective instrument. A conversation is run through a fixed open-weight
model; hidden states at one mid-depth layer are mean-pooled over tokens,
contrasted against a cached neutral baseline, and L2-normalized. The result
is not a description of the conversation's register — it is the geometric
residue of it: the direction the model leaned while reading.

Laws:
- ONE reader, forever, for all flavor vectors (mixed-model vectors are
  meaningless). Changing READER_MODEL means rebuild_flavor.py over everything.
- The reader reads RAW exchanges, never traces — flavor is captured from the
  conversation itself, not from memory's retelling of it.
- bf16, deterministic forward, no sampling. Same text → same vector.
- VRAM guard: capture SKIPS with a WARN when the card lacks headroom
  (~17 GB). The nightly window retries; nothing ever OOMs the fleet.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from . import config

logger = logging.getLogger("madeleine.reader")

_VRAM_NEEDED_MB = 17000
_MAX_TOKENS = 2048
_HIDDEN = 4096   # Qwen3-8B hidden size — must match episodes.flavor VECTOR(4096)

# Fifty fixed neutral passages — the baseline "room temperature" of the
# reader. Deliberately boring, varied in surface form, constant forever
# (changing them invalidates every stored vector).
_BASELINE_PASSAGES = tuple(
    f"This is a plain statement about an ordinary topic, number {i}. "
    "It describes routine information in a neutral tone without any "
    "particular emotional content or unusual subject matter."
    for i in range(1, 51)
)

_model = None
_tokenizer = None


def vram_free_mb() -> int:
    try:
        import torch
        free, _total = torch.cuda.mem_get_info()
        return int(free / 1024 / 1024)
    except Exception:
        return 0


def gpu_ready() -> bool:
    # Already resident? Then the card is ours and no new allocation is
    # needed. Checking free VRAM here counted our OWN 17 GB footprint as
    # someone else's, so the runner napped forever after batch 1
    # (2026-08-20: flavor stuck at 600/4402 in a 10-min retry loop).
    if _model is not None:
        return True
    free = vram_free_mb()
    if free < _VRAM_NEEDED_MB:
        logger.warning("reader skipped: %d MB free, %d needed — retry next window",
                       free, _VRAM_NEEDED_MB)
        return False
    return True


def _load():
    global _model, _tokenizer
    if _model is not None:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    logger.info("loading reader %s (bf16)...", config.READER_MODEL)
    _tokenizer = AutoTokenizer.from_pretrained(config.READER_MODEL)
    _model = AutoModelForCausalLM.from_pretrained(
        config.READER_MODEL, dtype=torch.bfloat16, device_map="cuda",
        output_hidden_states=True)
    _model.eval()
    logger.info("reader ready")


def unload():
    """Release the card when the batch is done — the reader is a night
    visitor, not a resident."""
    global _model, _tokenizer
    if _model is None:
        return
    import torch
    del _model
    _model = None
    _tokenizer = None
    torch.cuda.empty_cache()
    logger.info("reader unloaded")


def _hidden_at(text: str, layer: int) -> np.ndarray:
    """Mean-pooled hidden state at one layer for one text. bf16→fp32."""
    import torch
    toks = _tokenizer(text, return_tensors="pt", truncation=True,
                      max_length=_MAX_TOKENS).to("cuda")
    with torch.no_grad():
        out = _model(**toks)
    h = out.hidden_states[layer][0]          # (seq, hidden)
    return h.mean(dim=0).float().cpu().numpy()


def _hidden_all_layers(text: str) -> list[np.ndarray]:
    """Mean-pooled hidden states at EVERY layer (for the probe)."""
    import torch
    toks = _tokenizer(text, return_tensors="pt", truncation=True,
                      max_length=_MAX_TOKENS).to("cuda")
    with torch.no_grad():
        out = _model(**toks)
    return [h[0].mean(dim=0).float().cpu().numpy() for h in out.hidden_states]


def _baseline_path(layer: int) -> Path:
    slug = config.READER_MODEL.replace("/", "_")
    return config.REPO_ROOT / "data" / f"baseline_{slug}_L{layer}.npy"


def get_baseline(layer: int) -> np.ndarray:
    """Neutral-direction cache: mean hidden state over the 50 fixed passages.
    Computed once per model+layer, stored in data/."""
    p = _baseline_path(layer)
    if p.exists():
        return np.load(p)
    logger.info("computing neutral baseline for layer %d (one-time)...", layer)
    acc = np.zeros(_HIDDEN, dtype=np.float64)
    for passage in _BASELINE_PASSAGES:
        acc += _hidden_at(passage, layer)
    baseline = (acc / len(_BASELINE_PASSAGES)).astype(np.float32)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.save(p, baseline)
    return baseline


def flavor_of(text: str, layer: int | None = None) -> np.ndarray:
    """The flavor vector: (mean hidden − neutral baseline), L2-normalized."""
    layer = layer or config.READER_LAYER
    _load()
    v = _hidden_at(text, layer) - get_baseline(layer)
    n = np.linalg.norm(v)
    return (v / n if n > 0 else v).astype(np.float32)


def capture_batch(conn, batch: int | None = None) -> int:
    """Fill episodes.flavor where NULL, newest first, capped. The nightly
    pass. Caller checks gpu_ready() first. Reads RAW exchange spans."""
    batch = batch or config.FLAVOR_BATCH
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, r.speaker, r.content FROM episodes e "
            "JOIN raw_exchanges r ON r.id = e.exchange_start "
            "WHERE e.flavor IS NULL AND NOT e.quarantined "
            "ORDER BY e.created_at DESC LIMIT %s", (batch,))
        rows = cur.fetchall()
    if not rows:
        return 0
    _load()
    done = 0
    for row in rows:
        try:
            vec = flavor_of(f"{row['speaker']}: {row['content']}")
            with conn.cursor() as cur:
                cur.execute("UPDATE episodes SET flavor=%s WHERE id=%s",
                            (vec.tolist(), row["id"]))
            done += 1
        except Exception as e:
            logger.error("flavor capture failed for episode %d: %s", row["id"], e)
    logger.info("flavor captured for %d episodes", done)
    return done
