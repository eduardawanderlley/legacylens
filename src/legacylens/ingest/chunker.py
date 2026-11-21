"""Divisão de código Python em chunks por estrutura (AST), não por tamanho.

Uma função nunca é cortada no meio. O custo é aceitar chunks de tamanhos
muito diferentes; ver docs/decisions.md (ADR-001).
"""

from __future__ import annotations

import ast
import hashlib

from ..models import Chunk


def _first_line(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *[d.lineno for d in decorators]])  # type: ignore[attr-defined]


def _called_names(node: ast.AST) -> tuple[str, ...]:
    names: dict[str, None] = {}
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.setdefault(func.id)
            elif isinstance(func, ast.Attribute):
                names.setdefault(func.attr)
    return tuple(names)


def _module_imports(tree: ast.Module) -> tuple[str, ...]:
    found: dict[str, None] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.setdefault(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            for alias in node.names:
                found.setdefault(f"{prefix}.{alias.name}".strip("."))
    return tuple(found)


def _chunk_id(path: str, name: str, start: int) -> str:
    return hashlib.sha1(f"{path}:{name}:{start}".encode()).hexdigest()[:12]


def chunk_python_source(path: str, source: str) -> list[Chunk]:
    """Um chunk por função/método, um cabeçalho por classe e um de módulo.

    Arquivos com erro de sintaxe (típico de Python 2) devolvem lista vazia;
    quem chama decide se isso merece um aviso.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    imports = _module_imports(tree)
    chunks: list[Chunk] = []

    def emit(node: ast.AST, name: str, kind: str, start: int, end: int, doc: str | None) -> None:
        chunks.append(
            Chunk(
                id=_chunk_id(path, name, start),
                path=path,
                name=name,
                kind=kind,
                start_line=start,
                end_line=end,
                text="\n".join(lines[start - 1 : end]),
                docstring=doc,
                calls=_called_names(node) if kind == "function" else (),
                imports=imports,
            )
        )

    def visit(body: list[ast.stmt], scope: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{scope}.{node.name}" if scope else node.name
                emit(node, qual, "function", _first_line(node), node.end_lineno or node.lineno, ast.get_docstring(node))
            elif isinstance(node, ast.ClassDef):
                qual = f"{scope}.{node.name}" if scope else node.name
                methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                start = _first_line(node)
                # O chunk da classe vai até o primeiro método; os métodos têm chunks próprios.
                end = (min(_first_line(m) for m in methods) - 1) if methods else (node.end_lineno or node.lineno)
                emit(node, qual, "class", start, max(start, end), ast.get_docstring(node))
                visit(node.body, qual)

    leading = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) or _is_docstring(n)]
    if leading:
        header_end = min(max((n.end_lineno or n.lineno) for n in leading), 60)
        emit(tree, "<module>", "module", 1, header_end, ast.get_docstring(tree))

    visit(tree.body, "")
    return chunks


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
