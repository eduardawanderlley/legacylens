"""Busca híbrida: BM25 + vetores fundidos por RRF, reranking e expansão por grafo."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from ..embeddings import Embedder
from ..models import Chunk, Hit
from ..store import Store
from ..text import query_terms, split_identifier

RRF_K = 60  # constante do artigo original de Reciprocal Rank Fusion


class SearchMode(str, Enum):
    BM25 = "bm25"
    VECTOR = "vector"
    HYBRID = "hybrid"
    HYBRID_GRAPH = "hybrid+graph"


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]: ...


class IdentifierReranker:
    """Reranker barato: premia chunks cujo nome ou caminho aparecem na pergunta.

    Em código, quem pergunta costuma citar o identificador quase exato.
    Chunks de módulo e de classe pesam menos que funções.
    """

    def __init__(self, name_boost: float = 0.5, path_boost: float = 0.15) -> None:
        self.name_boost = name_boost
        self.path_boost = path_boost

    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        terms = set(query_terms(query))
        rescored: list[Hit] = []
        for hit in hits:
            name_parts = set(split_identifier(hit.chunk.simple_name))
            path_parts = {p for seg in hit.chunk.path.split("/") for p in split_identifier(seg.removesuffix(".py"))}
            bonus = self.name_boost * (len(name_parts & terms) / max(len(name_parts), 1))
            bonus += self.path_boost * (len(path_parts & terms) / max(len(path_parts), 1))
            if hit.chunk.kind != "function":
                bonus -= 0.05
            rescored.append(Hit(hit.chunk, hit.score + bonus * _scale(hits), hit.via))
        return sorted(rescored, key=lambda h: h.score, reverse=True)


def _scale(hits: list[Hit]) -> float:
    return max((h.score for h in hits), default=1.0) or 1.0


class CrossEncoderReranker:
    """Reranker neural opcional (extra `semantic`)."""

    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model)

    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        if not hits:
            return hits
        scores = self._model.predict([(query, h.chunk.text[:2000]) for h in hits])
        order = sorted(zip(hits, scores), key=lambda p: p[1], reverse=True)
        return [Hit(h.chunk, float(s), h.via) for h, s in order]


class Retriever:
    def __init__(self, store: Store, embedder: Embedder, reranker: Reranker | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.reranker = reranker if reranker is not None else IdentifierReranker()

    def search(self, query: str, k: int = 8, mode: SearchMode = SearchMode.HYBRID_GRAPH, pool: int = 30) -> list[Hit]:
        fused = self._fuse(query, mode, pool)
        hits = [Hit(chunk, score) for chunk, score in fused if chunk is not None]
        if mode in (SearchMode.HYBRID, SearchMode.HYBRID_GRAPH):
            hits = self.reranker.rerank(query, hits)
        hits = hits[:k]
        if mode is SearchMode.HYBRID_GRAPH:
            hits += self._expand(hits, limit=max(2, k // 2))
        return hits

    def _fuse(self, query: str, mode: SearchMode, pool: int) -> list[tuple[Chunk | None, float]]:
        rankings: list[list[str]] = []
        if mode is not SearchMode.VECTOR:
            rankings.append([cid for cid, _ in self.store.search_bm25(query, pool)])
        if mode is not SearchMode.BM25:
            qvec = self.embedder.embed([query])[0]
            rankings.append([cid for cid, _ in self.store.search_vector(qvec, pool)])
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, cid in enumerate(ranking, start=1):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [(self.store.get(cid), s) for cid, s in ordered]

    def _expand(self, hits: list[Hit], limit: int) -> list[Hit]:
        """Traz vizinhos no grafo de chamadas (quem é chamado e quem chama).

        Os vizinhos entram depois dos resultados da busca e marcados com
        via="graph", com score abaixo do menor resultado direto.
        """
        seen = {h.chunk.id for h in hits}
        floor = min((h.score for h in hits), default=0.0)
        extra: list[Hit] = []
        for hit in hits[:3]:
            if hit.chunk.kind != "function":
                continue
            neighbours = self.store.callees_of(hit.chunk, limit=3) + self.store.callers_of(hit.chunk.simple_name, limit=2)
            for n in neighbours:
                if n.id not in seen and len(extra) < limit:
                    seen.add(n.id)
                    extra.append(Hit(n, floor * 0.99, via="graph"))
        return extra
