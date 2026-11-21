"""Mapeia um diff do git para as funções indexadas que mudaram (base do PR bot)."""

from __future__ import annotations

import re

from .models import Chunk
from .store import Store

_FILE = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_ranges(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Intervalos de linhas novas por arquivo, a partir de `git diff -U0`."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if m := _FILE.match(line):
            current = m.group(1)
        elif current and (m := _HUNK.match(line)):
            start = int(m.group(1))
            length = int(m.group(2)) if m.group(2) is not None else 1
            if length > 0:  # length 0 = só remoção, sem linhas novas
                ranges.setdefault(current, []).append((start, start + length - 1))
    return ranges


def changed_functions(store: Store, diff: str) -> list[Chunk]:
    found: dict[str, Chunk] = {}
    for path, spans in changed_ranges(diff).items():
        if not path.endswith(".py"):
            continue
        for chunk in store.chunks_in_file(path):
            if chunk.kind == "function" and any(chunk.start_line <= e and chunk.end_line >= s for s, e in spans):
                found[chunk.id] = chunk
    return list(found.values())
