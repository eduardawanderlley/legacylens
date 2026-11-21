"""Tokenização de identificadores, compartilhada por busca lexical e embeddings."""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

STOPWORDS = frozenset(
    """a o as os um uma de da do das dos em no na nos nas por para com sem que e ou se
    onde como quando qual quais isso esse essa este esta é são foi ser tem há
    the an of in on at to for with is are was how what where when which does do and or if it this that
    """.split()
)


def split_identifier(word: str) -> list[str]:
    """`validatePayment_v2` -> ['validate', 'payment', 'v2']."""
    parts: list[str] = []
    for piece in word.split("_"):
        if not piece:
            continue
        parts.extend(p.lower() for p in _CAMEL.split(piece) if p)
    return parts


def tokens(text: str) -> list[str]:
    """Tokens em minúsculo, com identificadores quebrados em partes."""
    out: list[str] = []
    for word in _WORD.findall(text):
        out.extend(split_identifier(word))
    return out


def query_terms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for tok in tokens(text):
        if len(tok) >= 3 and tok not in STOPWORDS:
            seen.setdefault(tok)
    return list(seen)
