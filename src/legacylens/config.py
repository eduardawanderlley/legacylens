from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    """Configuração lida do ambiente. Valores padrão servem para uso local."""

    db_path: Path = field(default_factory=lambda: Path(os.getenv("LEGACYLENS_DB", ".legacylens/index.db")))
    log_path: Path = field(default_factory=lambda: Path(os.getenv("LEGACYLENS_LOG", ".legacylens/telemetry.jsonl")))
    model: str = field(default_factory=lambda: os.getenv("LEGACYLENS_MODEL", "claude-sonnet-5-5"))
    embedder: str = field(default_factory=lambda: os.getenv("LEGACYLENS_EMBEDDER", "hashing"))
    # Preços em USD por milhão de tokens. Zero significa "não informado".
    price_in_per_mtok: float = field(default_factory=lambda: _float("LEGACYLENS_PRICE_IN", 0.0))
    price_out_per_mtok: float = field(default_factory=lambda: _float("LEGACYLENS_PRICE_OUT", 0.0))
    # Filtro lexical opcional antes de chamar o LLM: fração mínima dos termos da pergunta
    # que precisa aparecer na evidência. Desligado por padrão (0.0) porque perguntas em
    # português sobre identificadores em inglês falhariam nele; ver docs/limitations.md.
    min_evidence_overlap: float = field(default_factory=lambda: _float("LEGACYLENS_MIN_OVERLAP", 0.0))
