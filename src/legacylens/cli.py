from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from .config import Settings
from .embeddings import make_embedder
from .evaluation import evaluate_answers, evaluate_retrieval, load_questions
from .ingest import index_repository
from .llm import AnthropicLLM
from .pr import changed_functions
from .qa import CodebaseQA
from .retrieval import Retriever, SearchMode
from .store import Store
from .telemetry import Telemetry
from .testgen import PytestRunner, TestGenerator


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="legacylens", description="Perguntas e testes sobre código legado.")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("index", help="indexa um repositório")
    s.add_argument("repo", type=Path)

    s = sub.add_parser("ask", help="pergunta sobre o código indexado")
    s.add_argument("question")
    s.add_argument("-k", type=int, default=8)

    s = sub.add_parser("search", help="só a recuperação, sem LLM")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=8)
    s.add_argument("--mode", choices=[m.value for m in SearchMode], default=SearchMode.HYBRID_GRAPH.value)

    s = sub.add_parser("testgen", help="gera testes que passam para uma função")
    s.add_argument("target", help="'caminho.py::Classe.metodo' ou 'Classe.metodo'")
    s.add_argument("--repo", type=Path, default=Path("."))
    s.add_argument("--attempts", type=int, default=3)
    s.add_argument("--mutation", action="store_true", help="calcula mutation score (requer mutmut<3)")

    s = sub.add_parser("eval", help="avalia recuperação (e respostas, com --answers)")
    s.add_argument("dataset", type=Path)
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--answers", action="store_true", help="também avalia respostas (usa o LLM)")

    s = sub.add_parser("pr-suggest", help="sugere testes para funções alteradas entre dois commits")
    s.add_argument("--base", default="origin/main")
    s.add_argument("--repo", type=Path, default=Path("."))
    s.add_argument("--limit", type=int, default=3)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    settings = Settings()
    store = Store(settings.db_path)
    embedder = make_embedder(settings.embedder)
    retriever = Retriever(store, embedder)

    if args.cmd == "index":
        stats = index_repository(args.repo, store, embedder)
        print(f"{stats['files']} arquivos, {stats['chunks']} chunks ({stats['skipped']} ignorados)")
        return 0

    if store.count() == 0:
        print("Índice vazio. Rode `legacylens index <repo>` primeiro.", file=sys.stderr)
        return 2

    if args.cmd == "search":
        for hit in retriever.search(args.query, k=args.k, mode=SearchMode(args.mode)):
            print(f"{hit.score:.4f}  {hit.chunk.ref}  {hit.chunk.name}  [{hit.via}]")
        return 0

    llm = AnthropicLLM(settings.model)
    telemetry = Telemetry(settings)

    if args.cmd == "ask":
        answer = CodebaseQA(retriever, llm, settings, telemetry).ask(args.question, k=args.k)
        print(answer.text)
        if answer.invalid_citations:
            print(f"\naviso: citações fora da evidência: {', '.join(answer.invalid_citations)}", file=sys.stderr)
        return 0

    if args.cmd == "testgen":
        gen = TestGenerator(store, llm, PytestRunner(), args.repo, telemetry, max_attempts=args.attempts)
        result = gen.generate(args.target)
        print(f"{result.target}: {'passou' if result.passed else 'falhou'} em {len(result.attempts)} tentativa(s)")
        if not result.passed:
            print(result.reason, file=sys.stderr)
            return 1
        print(f"teste salvo em {result.test_path}")
        if args.mutation:
            from .testgen.mutation import run_mutation

            chunk = gen.resolve_target(args.target)
            m = run_mutation(args.repo, chunk.path, result.test_path)
            score = "n/d" if m.score is None else f"{m.score:.0%}"
            print(f"mutation score: {score} ({m.killed} mortos, {m.survived} sobreviventes, {m.other} outros)")
        return 0

    if args.cmd == "eval":
        questions = load_questions(args.dataset)
        report = {"retrieval": [evaluate_retrieval(retriever, questions, k=args.k, mode=m) for m in SearchMode]}
        if args.answers:
            report["answers"] = evaluate_answers(CodebaseQA(retriever, llm, settings, telemetry), questions)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "pr-suggest":
        diff = subprocess.run(["git", "diff", "-U0", f"{args.base}...HEAD"], cwd=args.repo, capture_output=True, text=True, check=True).stdout
        gen = TestGenerator(store, llm, PytestRunner(), args.repo, telemetry)
        lines = ["### Testes sugeridos pelo LegacyLens", ""]
        for chunk in changed_functions(store, diff)[: args.limit]:
            res = gen.generate(f"{chunk.path}::{chunk.name}")
            if res.passed and res.test_path:
                lines += [f"<details><summary><code>{chunk.name}</code> ({chunk.path})</summary>", "", "```python", res.test_path.read_text(), "```", "</details>", ""]
            else:
                lines.append(f"- `{chunk.name}`: não consegui gerar um teste que passe ({res.reason}).")
        print("\n".join(lines))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
