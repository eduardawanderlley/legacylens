from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from ..embeddings import Embedder
from ..models import Chunk
from ..store import Store
from .chunker import chunk_python_source

log = logging.getLogger(__name__)

SKIP_DIRS = {
    ".git", ".hg", ".venv", "venv", "env", "node_modules", "__pycache__",
    "build", "dist", ".tox", ".legacylens", "site-packages",
}


def iter_python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def embed_text(chunk: Chunk) -> str:
    """Texto enviado ao embedder. Caminho e nome ajudam perguntas por localização."""
    return f"{chunk.path} {chunk.name}\n{chunk.text}"


def index_repository(root: Path, store: Store, embedder: Embedder, *, batch_size: int = 64) -> dict[str, int]:
    """Reindexa o repositório inteiro e devolve contagens para o log do CLI."""
    root = root.resolve()
    store.reset()
    stats = {"files": 0, "chunks": 0, "skipped": 0}
    pending: list[Chunk] = []

    def flush() -> None:
        if pending:
            store.add(pending, embedder.embed([embed_text(c) for c in pending]))
            pending.clear()

    for path in iter_python_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.warning("não consegui ler %s: %s", rel, exc)
            stats["skipped"] += 1
            continue
        chunks = chunk_python_source(rel, source)
        if not chunks:
            stats["skipped"] += 1
            continue
        stats["files"] += 1
        stats["chunks"] += len(chunks)
        pending.extend(chunks)
        if len(pending) >= batch_size:
            flush()
    flush()
    return stats
