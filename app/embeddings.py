import hashlib
import re
import numpy as np
from . import config

_model = None
_STOP = set("a an the of to in on for and or is are was were be by with as at from that this it its what how do does which who when where can i".split())


def stem(w: str) -> str:
    """Very crude plural/verb stemmer used only by the offline test stand-ins."""
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _hash_embed(texts: list[str], dim: int = 1024) -> np.ndarray:
    """Offline bag-of-words hashing embedder. For tests/offline use only (no semantic understanding)."""
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            if w not in _STOP:
                out[i, int(hashlib.md5(stem(w).encode()).hexdigest(), 16) % dim] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1, norms)


def embed(texts: list[str]) -> np.ndarray:
    """Return L2-normalised float32 vectors, so dot product == cosine similarity."""
    global _model
    if config.EMBEDDING_BACKEND == "hash":
        return _hash_embed(texts)
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=config.EMBEDDING_MODEL)
    vecs = np.array(list(_model.embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.where(norms == 0, 1, norms)
