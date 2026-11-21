"""Registro de latência, tokens e custo por operação, em JSON Lines."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings


@dataclass
class Span:
    op: str
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict = field(default_factory=dict)


class Telemetry:
    def __init__(self, settings: Settings) -> None:
        self._path = settings.log_path
        self._price_in = settings.price_in_per_mtok
        self._price_out = settings.price_out_per_mtok

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float | None:
        if not (self._price_in or self._price_out):
            return None  # preços não configurados: melhor não inventar custo
        return (input_tokens * self._price_in + output_tokens * self._price_out) / 1_000_000

    @contextmanager
    def span(self, op: str):
        span = Span(op)
        start = time.perf_counter()
        try:
            yield span
        finally:
            record = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "op": op,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "input_tokens": span.input_tokens,
                "output_tokens": span.output_tokens,
                "cost_usd": self.cost_usd(span.input_tokens, span.output_tokens),
                **span.extra,
            }
            self._write(record)

    def _write(self, record: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
