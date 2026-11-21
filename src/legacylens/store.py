"""Índice em SQLite: FTS5 para BM25, vetores em BLOB e tabela de chamadas.

SQLite basta para repositórios de dezenas de milhares de funções e deixa o
projeto rodar sem serviços externos. Limites e saída para pgvector/Qdrant
estão em docs/decisions.md (ADR-003).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from .models import Chunk
from .text import query_terms, tokens

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
    start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, text TEXT NOT NULL,
    docstring TEXT, calls TEXT NOT NULL, imports TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE TABLE IF NOT EXISTS calls (chunk_id TEXT NOT NULL, callee TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee);
CREATE TABLE IF NOT EXISTS vectors (chunk_id TEXT PRIMARY KEY, vec BLOB NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, body, tokenize='unicode61');
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._matrix: np.ndarray | None = None
        self._matrix_ids: list[str] = []

    def close(self) -> None:
        self._db.close()

    def reset(self) -> None:
        for table in ("chunks", "calls", "vectors", "chunks_fts"):
            self._db.execute(f"DELETE FROM {table}")
        self._db.commit()
        self._matrix = None

    # --- escrita ---------------------------------------------------------

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        with self._db:
            for chunk, vec in zip(chunks, vectors):
                self._db.execute(
                    "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (chunk.id, chunk.path, chunk.name, chunk.kind, chunk.start_line, chunk.end_line,
                     chunk.text, chunk.docstring, json.dumps(chunk.calls), json.dumps(chunk.imports)),
                )
                self._db.executemany("INSERT INTO calls VALUES (?,?)", [(chunk.id, c) for c in chunk.calls])
                body = " ".join(tokens(f"{chunk.path} {chunk.name} {chunk.text}"))
                self._db.execute("INSERT INTO chunks_fts(chunk_id, body) VALUES (?,?)", (chunk.id, body))
                self._db.execute("INSERT OR REPLACE INTO vectors VALUES (?,?)", (chunk.id, vec.astype(np.float32).tobytes()))
        self._matrix = None

    # --- leitura ---------------------------------------------------------

    def count(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def get(self, chunk_id: str) -> Chunk | None:
        row = self._db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        return _row_to_chunk(row) if row else None

    def find_by_name(self, name: str) -> list[Chunk]:
        """Aceita nome qualificado (`A.b`) ou simples (`b`)."""
        rows = self._db.execute(
            "SELECT * FROM chunks WHERE name = ? OR name LIKE ? ORDER BY path, start_line",
            (name, f"%.{name}"),
        ).fetchall()
        return [_row_to_chunk(r) for r in rows]

    def chunks_in_file(self, path: str) -> list[Chunk]:
        rows = self._db.execute("SELECT * FROM chunks WHERE path=? ORDER BY start_line", (path,)).fetchall()
        return [_row_to_chunk(r) for r in rows]

    def callers_of(self, simple_name: str, limit: int = 5) -> list[Chunk]:
        rows = self._db.execute(
            "SELECT c.* FROM chunks c JOIN calls k ON k.chunk_id = c.id WHERE k.callee = ? LIMIT ?",
            (simple_name, limit),
        ).fetchall()
        return [_row_to_chunk(r) for r in rows]

    def callees_of(self, chunk: Chunk, limit: int = 5) -> list[Chunk]:
        found: dict[str, Chunk] = {}
        for callee in chunk.calls:
            for candidate in self.find_by_name(callee):
                if candidate.kind == "function" and candidate.id != chunk.id:
                    found.setdefault(candidate.id, candidate)
            if len(found) >= limit:
                break
        return list(found.values())[:limit]

    def search_bm25(self, query: str, limit: int = 30) -> list[tuple[str, float]]:
        terms = query_terms(query)
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        try:
            rows = self._db.execute(
                "SELECT chunk_id, bm25(chunks_fts) AS s FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY s LIMIT ?",
                (match, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(r["chunk_id"], -float(r["s"])) for r in rows]  # bm25() do SQLite: menor é melhor

    def search_vector(self, query_vec: np.ndarray, limit: int = 30) -> list[tuple[str, float]]:
        matrix, ids = self._load_matrix()
        if matrix is None:
            return []
        scores = matrix @ query_vec.astype(np.float32)
        top = np.argsort(-scores)[:limit]
        return [(ids[i], float(scores[i])) for i in top if scores[i] > 0]

    def _load_matrix(self) -> tuple[np.ndarray | None, list[str]]:
        if self._matrix is None:
            rows = self._db.execute("SELECT chunk_id, vec FROM vectors").fetchall()
            if not rows:
                return None, []
            self._matrix_ids = [r["chunk_id"] for r in rows]
            self._matrix = np.vstack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
        return self._matrix, self._matrix_ids


def _row_to_chunk(row: sqlite3.Row) -> Chunk:
    return Chunk(
        id=row["id"], path=row["path"], name=row["name"], kind=row["kind"],
        start_line=row["start_line"], end_line=row["end_line"], text=row["text"],
        docstring=row["docstring"], calls=tuple(json.loads(row["calls"])),
        imports=tuple(json.loads(row["imports"])),
    )
