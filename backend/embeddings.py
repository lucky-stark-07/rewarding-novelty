from functools import lru_cache
import numpy as np
from .config import get_settings

@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(get_settings().embedding_model, device="cpu")

def embed(texts: list[str]) -> np.ndarray:
    """Embed text locally. Returns an empty 2-D matrix for no input."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    return np.asarray(_model().encode(texts, normalize_embeddings=True), dtype=np.float32)

def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity for vectors or batches; zero vectors remain safe."""
    a, b = np.atleast_2d(a).astype(np.float32), np.atleast_2d(b).astype(np.float32)
    a = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    b = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    return a @ b.T
