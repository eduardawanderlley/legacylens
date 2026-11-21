"""Gera testes pytest para uma função: gerar, executar, ler o erro, corrigir.

Só entrega testes que passam e que de fato verificam algo.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..llm import LLM
from ..models import Chunk
from ..store import Store
from ..telemetry import Telemetry
from .runner import Runner

SYSTEM_PROMPT = """Você escreve testes unitários pytest para código Python legado.
Regras:
- Devolva um único arquivo de teste completo em um bloco ```python.
- Importe a função alvo do módulo indicado. Não reescreva nem copie o código testado.
- Teste o comportamento observável: valores de retorno, exceções, efeitos nos argumentos.
- Cubra caminho feliz, bordas e erros que o código realmente trata. Não teste o que o código não faz.
- Sem rede, sem escrita fora de tmp_path, sem sleep. Use monkeypatch para dependências externas.
- Todo teste precisa de pelo menos um assert (ou pytest.raises)."""

_CODE_BLOCK = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


@dataclass
class Attempt:
    number: int
    code: str
    passed: bool
    output: str


@dataclass
class GenerationResult:
    target: str
    passed: bool
    test_path: Path | None
    attempts: list[Attempt] = field(default_factory=list)
    reason: str = ""

    @property
    def first_try(self) -> bool:
        return bool(self.attempts) and self.attempts[0].passed


def extract_code(text: str) -> str | None:
    blocks = _CODE_BLOCK.findall(text)
    return max(blocks, key=len).strip() + "\n" if blocks else None


def check_test_quality(code: str) -> str | None:
    """Devolve o motivo da rejeição, ou None se o arquivo parece um teste de verdade."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"
    tests = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
    if not tests:
        return "nenhuma função test_* encontrada"
    for fn in tests:
        has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(fn)) or any(
            isinstance(n, ast.Attribute) and n.attr in {"raises", "approx"} for n in ast.walk(fn)
        )
        if not has_assert:
            return f"{fn.name} não verifica nada (sem assert/pytest.raises)"
    return None


def module_name(path: str) -> str:
    parts = Path(path).with_suffix("").parts
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


class TestGenerator:
    __test__ = False  # evita que o pytest tente coletar esta classe

    def __init__(self, store: Store, llm: LLM, runner: Runner, repo: Path, telemetry: Telemetry, max_attempts: int = 3) -> None:
        self.store, self.llm, self.runner = store, llm, runner
        self.repo, self.telemetry, self.max_attempts = repo.resolve(), telemetry, max_attempts

    def resolve_target(self, target: str) -> Chunk:
        """`pkg/mod.py::Classe.metodo` ou apenas `Classe.metodo`."""
        path, _, name = target.rpartition("::")
        matches = [c for c in self.store.find_by_name(name) if c.kind == "function"]
        if path:
            matches = [c for c in matches if c.path == path]
        if not matches:
            raise LookupError(f"função não encontrada no índice: {target}")
        if len(matches) > 1:
            options = ", ".join(f"{c.path}::{c.name}" for c in matches)
            raise LookupError(f"alvo ambíguo, use caminho::nome. Candidatos: {options}")
        return matches[0]

    def generate(self, target: str) -> GenerationResult:
        chunk = self.resolve_target(target)
        out_dir = self.repo / ".legacylens" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        test_path = out_dir / f"test_{chunk.simple_name}_{chunk.id}.py"
        result = GenerationResult(target=f"{chunk.path}::{chunk.name}", passed=False, test_path=None)

        messages = [{"role": "user", "content": self._first_prompt(chunk)}]
        for number in range(1, self.max_attempts + 1):
            with self.telemetry.span("testgen.attempt") as span:
                completion = self.llm.complete(SYSTEM_PROMPT, messages, max_tokens=2500)
                span.input_tokens, span.output_tokens = completion.input_tokens, completion.output_tokens
                span.extra.update(target=result.target, attempt=number)

                code = extract_code(completion.text)
                if code is None:
                    attempt = Attempt(number, "", False, "a resposta não continha bloco de código")
                elif (problem := check_test_quality(code)) is not None:
                    attempt = Attempt(number, code, False, f"teste rejeitado antes de rodar: {problem}")
                else:
                    test_path.write_text(code, encoding="utf-8")
                    run = self.runner.run(test_path, self.repo)
                    attempt = Attempt(number, code, run.passed, run.output)
                span.extra["passed"] = attempt.passed

            result.attempts.append(attempt)
            if attempt.passed:
                result.passed, result.test_path = True, test_path
                return result
            messages += [
                {"role": "assistant", "content": completion.text},
                {"role": "user", "content": self._fix_prompt(attempt.output)},
            ]

        test_path.unlink(missing_ok=True)  # nada que falhe fica no repositório
        result.reason = f"sem teste válido após {self.max_attempts} tentativas"
        return result

    def _first_prompt(self, chunk: Chunk) -> str:
        related = self.store.callees_of(chunk, limit=3)
        context = "\n\n".join(f"# {c.ref}\n{c.text}" for c in related) or "(nenhuma dependência interna encontrada)"
        return (
            f"Módulo: `{module_name(chunk.path)}` (arquivo {chunk.path})\n"
            f"Função alvo: `{chunk.name}`\n\n"
            f"Código alvo:\n```python\n{chunk.text}\n```\n\n"
            f"Funções internas que ela chama (apenas contexto):\n```python\n{context}\n```\n\n"
            "Escreva o arquivo de teste."
        )

    @staticmethod
    def _fix_prompt(output: str) -> str:
        tail = output[-4000:]
        return (
            "O arquivo não passou. Saída do pytest:\n\n"
            f"```\n{tail}\n```\n\n"
            "Corrija o TESTE (o código testado está correto, a menos que o erro mostre o contrário). "
            "Se o comportamento real difere do que você assumiu, ajuste a expectativa para o comportamento real. "
            "Devolva o arquivo completo."
        )
