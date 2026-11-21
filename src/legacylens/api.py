"""API HTTP (extra `api`). Uso: uvicorn legacylens.api:app"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import Settings
from .embeddings import make_embedder
from .llm import AnthropicLLM
from .qa import CodebaseQA
from .retrieval import Retriever, SearchMode
from .store import Store

settings = Settings()
store = Store(settings.db_path)
retriever = Retriever(store, make_embedder(settings.embedder))
app = FastAPI(title="LegacyLens", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    k: int = Field(default=8, ge=1, le=20)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "chunks": store.count()}


@app.get("/search")
def search(q: str, k: int = 8, mode: SearchMode = SearchMode.HYBRID_GRAPH) -> list[dict]:
    hits = retriever.search(q, k=k, mode=mode)
    return [{"ref": h.chunk.ref, "name": h.chunk.name, "score": h.score, "via": h.via} for h in hits]


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    if store.count() == 0:
        raise HTTPException(409, "índice vazio; rode `legacylens index <repo>`")
    answer = CodebaseQA(retriever, AnthropicLLM(settings.model), settings).ask(req.question, req.k)
    return {
        "answer": answer.text,
        "citations": answer.citations,
        "invalid_citations": answer.invalid_citations,
        "abstained": answer.abstained,
    }
