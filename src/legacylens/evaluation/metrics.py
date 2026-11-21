"""Avaliação com gabarito. Tudo aqui é determinístico e roda sem LLM, exceto `evaluate_answers`.

Formato do gabarito (JSON Lines), uma pergunta por linha:
  {"id": "q1", "question": "...", "answerable": true,
   "gold": [{"path": "app/pay.py", "start_line": 10, "end_line": 40}]}
Perguntas sem resposta no código usam "answerable": false e "gold": [].
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..qa import CodebaseQA
from ..retrieval import Retriever, SearchMode


@dataclass(frozen=True)
class GoldSpan:
    path: str
    start_line: int
    end_line: int

    def overlaps(self, path: str, start: int, end: int) -> bool:
        return self.path == path and start <= self.end_line and end >= self.start_line


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    answerable: bool
    gold: tuple[GoldSpan, ...]


def load_questions(path: Path) -> list[Question]:
    questions = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            raw = json.loads(line)
            questions.append(
                Question(
                    id=raw["id"],
                    question=raw["question"],
                    answerable=raw.get("answerable", True),
                    gold=tuple(GoldSpan(**g) for g in raw.get("gold", [])),
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"{path}:{lineno}: linha inválida no gabarito ({exc})") from exc
    return questions


def evaluate_retrieval(retriever: Retriever, questions: list[Question], k: int = 5, mode: SearchMode = SearchMode.HYBRID_GRAPH) -> dict:
    """recall@k e MRR sobre as perguntas respondíveis."""
    scored = [q for q in questions if q.answerable and q.gold]
    hits_at_k = 0
    reciprocal = 0.0
    misses: list[str] = []
    for q in scored:
        results = retriever.search(q.question, k=k, mode=mode)
        rank = next(
            (i for i, h in enumerate(results, start=1)
             if any(g.overlaps(h.chunk.path, h.chunk.start_line, h.chunk.end_line) for g in q.gold)),
            None,
        )
        if rank is not None and rank <= len(results):
            hits_at_k += 1
            reciprocal += 1.0 / rank
        else:
            misses.append(q.id)
    n = len(scored) or 1
    return {"mode": mode.value, "k": k, "questions": len(scored), f"recall@{k}": hits_at_k / n, "mrr": reciprocal / n, "misses": misses}


def evaluate_answers(qa: CodebaseQA, questions: list[Question], k: int = 8) -> dict:
    """Qualidade das respostas: citação correta, citação inválida e abstenção certa.

    `citation_correct`: pelo menos uma citação válida cai sobre o trecho do gabarito.
    `invalid_citation_rate`: respostas com alguma citação fora da evidência fornecida.
    `abstention_correct`: perguntas sem resposta em que o sistema disse que não sabe.
    `false_abstention`: perguntas com resposta em que o sistema se recusou.
    """
    answerable = [q for q in questions if q.answerable]
    unanswerable = [q for q in questions if not q.answerable]
    correct = invalid = false_abstain = 0
    for q in answerable:
        ans = qa.ask(q.question, k=k)
        false_abstain += ans.abstained
        invalid += bool(ans.invalid_citations)
        for ref in ans.citations:
            path, _, span = ref.rpartition(":")
            a, b = (int(x) for x in span.split("-"))
            if any(g.overlaps(path, a, b) for g in q.gold):
                correct += 1
                break
    right_abstain = sum(qa.ask(q.question, k=k).abstained for q in unanswerable)
    na, nu = len(answerable) or 1, len(unanswerable) or 1
    return {
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "citation_correct": correct / na,
        "invalid_citation_rate": invalid / na,
        "false_abstention": false_abstain / na,
        "abstention_correct": right_abstain / nu,
    }
