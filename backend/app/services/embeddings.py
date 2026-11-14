"""Text embeddings (384 dims) for twin memory.

Providers:
- local:  sentence-transformers all-MiniLM-L6-v2 on CPU, free. Model cached in backend/.model_cache
- openai: text-embedding-3-small with dimensions=384 (same column, no migration)
- fake:   deterministic hashed bag-of-words (tests); similar wording -> similar vectors
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
import zlib
from collections.abc import Callable

from app.core.config import BACKEND_DIR, settings

log = logging.getLogger("twin.embeddings")

# Keep downloaded model files inside the project, not in the user's profile.
os.environ.setdefault("HF_HOME", str(BACKEND_DIR / ".model_cache"))

_lock = threading.Lock()
_local_model = None


class EmbeddingError(Exception):
    pass


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _fake(texts: list[str]) -> list[list[float]]:
    out = []
    for t in texts:
        vec = [0.0] * settings.embedding_dim
        for tok in re.findall(r"[a-z0-9]+", t.lower()):
            stem = tok[:5]
            vec[zlib.crc32(stem.encode()) % settings.embedding_dim] += 1.0
        if not any(vec):
            vec[0] = 1.0
        out.append(_normalise(vec))
    return out


def _load_local():
    global _local_model
    with _lock:
        if _local_model is None:
            t0 = time.perf_counter()
            from sentence_transformers import SentenceTransformer

            log.info("loading local embedding model %s ...", settings.local_embedding_model)
            _local_model = SentenceTransformer(settings.local_embedding_model, device="cpu")
            log.info("local embedding model ready in %.0fs", time.perf_counter() - t0)
    return _local_model


def ready() -> bool:
    """False only while the local model is still loading (it can take minutes on a cold
    Windows machine). Callers then skip embedding and let the backfill catch up."""
    return settings.embedding_provider != "local" or _local_model is not None


def warm_up_in_background(on_ready: Callable[[], None] | None = None) -> None:
    """Load the local model off the request path at startup, then run `on_ready`."""
    if settings.embedding_provider != "local" or _local_model is not None:
        return

    def run() -> None:
        try:
            _load_local()
            if on_ready:
                on_ready()
        except Exception:  # noqa: BLE001
            log.exception("local embedding warm-up failed")

    threading.Thread(target=run, name="embedding-warmup", daemon=True).start()


def backfill_missing(session_factory, batch: int = 256) -> int:
    """Embed learnable user messages that were saved without a vector. Returns count."""
    from sqlalchemy import select

    from app.models import Message

    done = 0
    with session_factory() as db:
        while True:
            rows = db.scalars(
                select(Message)
                .where(
                    Message.role == "user", Message.learnable.is_(True), Message.embedding.is_(None)
                )
                .limit(batch)
            ).all()
            if not rows:
                break
            try:
                vecs = embed([m.text for m in rows])
            except EmbeddingError:
                log.warning("backfill stopped: embedding failed")
                break
            for m, v in zip(rows, vecs, strict=True):
                m.embedding = v
            db.commit()
            done += len(rows)
    if done:
        log.info("backfilled embeddings for %d messages", done)
    return done


def _local(texts: list[str]) -> list[list[float]]:
    vecs = _load_local().encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
    )
    return [v.tolist() for v in vecs]


def _openai(texts: list[str]) -> list[list[float]]:
    from app.services.llm import llm_configured

    if not llm_configured() or not settings.openai_api_key:
        raise EmbeddingError("OPENAI_API_KEY is not set")
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key.strip(), timeout=30, max_retries=2)
    out: list[list[float]] = []
    for i in range(0, len(texts), 512):
        resp = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts[i : i + 512],
            dimensions=settings.embedding_dim,
        )
        out.extend(_normalise(d.embedding) for d in resp.data)
    return out


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts. Raises EmbeddingError on failure (callers degrade gracefully)."""
    if not texts:
        return []
    try:
        if settings.embedding_provider == "fake":
            return _fake(texts)
        if settings.embedding_provider == "openai":
            return _openai(texts)
        return _local(texts)
    except EmbeddingError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("embedding failed")
        raise EmbeddingError(str(exc)) from exc


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
