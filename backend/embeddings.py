import threading
from collections import OrderedDict
from functools import lru_cache
import numpy as np
from .config import get_settings

_model_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: OrderedDict[str, np.ndarray] = OrderedDict()
cache_stats = {"hits": 0, "misses": 0}


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(get_settings().embedding_model, device="cpu")


def warm_up() -> None:
    embed(["warm up"])


def embed(texts: list[str]) -> np.ndarray:
    """Embed text locally with a bounded LRU cache. Returns an empty 2-D matrix for no input.

    Blocking and CPU-bound: call through asyncio.to_thread from async code."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    capacity = get_settings().embedding_cache_size
    found: dict[str, np.ndarray] = {}
    with _cache_lock:
        for text in texts:
            vector = _cache.get(text)
            if vector is not None:
                _cache.move_to_end(text)
                found[text] = vector
    missing = list(dict.fromkeys(text for text in texts if text not in found))
    cache_stats["hits"] += len(texts) - sum(1 for text in texts if text not in found)
    cache_stats["misses"] += len(missing)
    if missing:
        with _model_lock:
            vectors = np.asarray(_model().encode(missing, normalize_embeddings=True), dtype=np.float32)
        found.update(zip(missing, vectors))
        if capacity:
            with _cache_lock:
                for text, vector in zip(missing, vectors):
                    _cache[text] = vector
                    _cache.move_to_end(text)
                while len(_cache) > capacity:
                    _cache.popitem(last=False)
    return np.stack([found[text] for text in texts])


def cache_snapshot() -> dict[str, int]:
    return {**cache_stats, "size": len(_cache), "capacity": get_settings().embedding_cache_size}


def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity for vectors or batches; zero vectors remain safe."""
    a, b = np.atleast_2d(a).astype(np.float32), np.atleast_2d(b).astype(np.float32)
    a = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    b = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    return a @ b.T
