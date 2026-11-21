from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from .text import tokens


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Matriz (n, dim) com linhas normalizadas (norma L2 = 1)."""
        ...


class HashingEmbedder:
    """Embedder local, sem dependências e determinístico (hashing trick).

    Não captura semântica. Serve para rodar o projeto offline, em CI e nos
    testes. Para uso real, troque por `SentenceTransformerEmbedder`.
    """

    name = "hashing-v1"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            toks = tokens(text)
            for tok in toks:
                digest = hashlib.blake2b(tok.encode(), digest_size=8).digest()
                h = int.from_bytes(digest, "little")
                sign = 1.0 if (h >> 63) == 0 else -1.0
                out[row, h % self.dim] += sign
            # bigramas dão alguma noção de ordem
            for a, b in zip(toks, toks[1:]):
                h = int.from_bytes(hashlib.blake2b(f"{a} {b}".encode(), digest_size=8).digest(), "little")
                out[row, h % self.dim] += 0.5 * (1.0 if (h >> 63) == 0 else -1.0)
        return _normalize(out)


class SentenceTransformerEmbedder:
    """Embeddings semânticos locais via sentence-transformers (extra `semantic`)."""

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer  # import tardio: dependência opcional

        self._model = SentenceTransformer(model)
        self.name = f"st:{model}"
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def make_embedder(kind: str) -> Embedder:
    if kind == "hashing":
        return HashingEmbedder()
    if kind.startswith("st:"):
        return SentenceTransformerEmbedder(kind[3:])
    raise ValueError(f"embedder desconhecido: {kind!r} (use 'hashing' ou 'st:<modelo>')")
