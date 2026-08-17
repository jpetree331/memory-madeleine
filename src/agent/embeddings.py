"""Madeleine — local embeddings (BAAI/bge-m3, 1024-dim).

Lazy singleton, thread-safe: the model loads on first use, never at import —
service boot stays fast and the GPU is only touched when memory actually
flows. Nothing leaves the machine.
"""
from __future__ import annotations

import logging
import threading

from . import config

logger = logging.getLogger("madeleine.embeddings")

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                logger.info("loading embed model %s (first use)", config.EMBED_MODEL)
                _model = SentenceTransformer(config.EMBED_MODEL)
                logger.info("embed model ready on %s", _model.device)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Batch-embed. Normalized vectors (cosine-ready)."""
    if not texts:
        return []
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]
