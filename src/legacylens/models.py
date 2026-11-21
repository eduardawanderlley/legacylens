from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """Uma unidade de código indexável: função, método ou cabeçalho de classe."""

    id: str
    path: str
    name: str  # nome qualificado, ex.: "PaymentService.validate"
    kind: str  # "function" | "class" | "module"
    start_line: int
    end_line: int
    text: str
    docstring: str | None = None
    calls: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()

    @property
    def simple_name(self) -> str:
        return self.name.rsplit(".", 1)[-1]

    @property
    def ref(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    via: str = "search"  # "search" | "graph"
