import asyncio
import hashlib
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import numpy as np
from .config import get_settings

# One worker: SentenceTransformer inference is CPU-bound and already multi-threaded internally.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed")
_lock = threading.Lock()
_cache: OrderedDict[str, np.ndarray] = OrderedDict()
cache_stats = {"hits": 0, "misses": 0, "encode_calls": 0}


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(get_settings().embedding_model, device="cpu")


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def warm_up() -> None:
    _model().encode(["warm up"], normalize_embeddings=True)


def embed(texts: list[str]) -> np.ndarray:
    """Embed texts as L2-normalised rows in one encode call for all cache misses.

    Blocking and CPU-bound: from async code use `embed_async`."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    settings = get_settings()
    use_cache = settings.cache_enabled and settings.embedding_cache_size > 0
    keys = [text_key(text) for text in texts]
    found: dict[str, np.ndarray] = {}
    with _lock:
        if use_cache:
            for key in keys:
                if (vector := _cache.get(key)) is not None:
                    _cache.move_to_end(key)
                    found[key] = vector
        missing = list(dict.fromkeys((key, text) for key, text in zip(keys, texts) if key not in found))
        cache_stats["hits"] += sum(1 for key in keys if key in found)
        cache_stats["misses"] += len(missing)
        if missing:
            cache_stats["encode_calls"] += 1
            vectors = np.asarray(_model().encode([text for _, text in missing], normalize_embeddings=True), dtype=np.float32)
            for (key, _), vector in zip(missing, vectors):
                found[key] = vector
                if use_cache:
                    _cache[key] = vector
                    _cache.move_to_end(key)
            while len(_cache) > settings.embedding_cache_size:
                _cache.popitem(last=False)
    return np.stack([found[key] for key in keys])


async def run_embedder(embedder, texts: list[str]) -> np.ndarray:
    return await asyncio.get_running_loop().run_in_executor(_executor, embedder, texts)


async def embed_async(texts: list[str]) -> np.ndarray:
    return await run_embedder(embed, texts)


def cache_snapshot() -> dict[str, int | bool]:
    settings = get_settings()
    return {**cache_stats, "size": len(_cache), "capacity": settings.embedding_cache_size, "enabled": settings.cache_enabled}


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    matrix = np.atleast_2d(matrix).astype(np.float32)
    return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity for vectors or batches; zero vectors remain safe."""
    return normalize_rows(a) @ normalize_rows(b).T
