"""Ask the Codebase: respostas ancoradas em evidência, com citação arquivo:linha."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Settings
from .llm import LLM
from .models import Hit
from .retrieval import Retriever
from .telemetry import Telemetry
from .text import query_terms, tokens

NO_EVIDENCE = "Não encontrei evidência suficiente no código indexado para responder com segurança."

SYSTEM_PROMPT = """Você ajuda desenvolvedores a entender um código legado.
Responda somente com base nos trechos fornecidos. Regras:
- Cite a fonte de cada afirmação no formato [caminho:inicio-fim], copiando exatamente a referência do trecho.
- Se os trechos não bastam para responder, diga isso claramente em vez de supor.
- Não invente funções, arquivos ou comportamentos que não aparecem nos trechos.
- Seja direto. Responda no idioma da pergunta."""

_CITATION = re.compile(r"\[([^\[\]:\s]+(?:/[^\[\]:\s]+)*):(\d+)-(\d+)\]")


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    abstained: bool = False
    evidence: list[Hit] = field(default_factory=list)


def evidence_overlap(question: str, hits: list[Hit]) -> float:
    """Fração dos termos da pergunta que aparece em algum trecho recuperado."""
    terms = query_terms(question)
    if not terms or not hits:
        return 0.0
    corpus = set()
    for hit in hits:
        corpus.update(tokens(f"{hit.chunk.path} {hit.chunk.name} {hit.chunk.text}"))
    return sum(t in corpus for t in terms) / len(terms)


def format_evidence(hits: list[Hit]) -> str:
    blocks = []
    for hit in hits:
        c = hit.chunk
        blocks.append(f"### [{c.ref}] {c.name}\n```python\n{c.text}\n```")
    return "\n\n".join(blocks)


def split_citations(text: str, hits: list[Hit]) -> tuple[list[str], list[str]]:
    """Separa citações que apontam para evidência fornecida das que não apontam."""
    valid_refs = {h.chunk.ref for h in hits}
    ranges: dict[str, list[tuple[int, int]]] = {}
    for h in hits:
        ranges.setdefault(h.chunk.path, []).append((h.chunk.start_line, h.chunk.end_line))
    valid: list[str] = []
    invalid: list[str] = []
    for path, a, b in _CITATION.findall(text):
        ref = f"{path}:{a}-{b}"
        inside = any(s <= int(a) and int(b) <= e for s, e in ranges.get(path, []))
        target = valid if (ref in valid_refs or inside) else invalid
        if ref not in target:
            target.append(ref)
    return valid, invalid


class CodebaseQA:
    def __init__(self, retriever: Retriever, llm: LLM, settings: Settings, telemetry: Telemetry | None = None) -> None:
        self.retriever = retriever
        self.llm = llm
        self.settings = settings
        self.telemetry = telemetry or Telemetry(settings)

    def ask(self, question: str, k: int = 8) -> Answer:
        with self.telemetry.span("ask") as span:
            hits = self.retriever.search(question, k=k)
            overlap = evidence_overlap(question, hits)
            span.extra.update(hits=len(hits), overlap=round(overlap, 3))
            if not hits or (self.settings.min_evidence_overlap and overlap < self.settings.min_evidence_overlap):
                span.extra["abstained"] = True
                return Answer(NO_EVIDENCE, abstained=True, evidence=hits)

            prompt = f"Trechos do código:\n\n{format_evidence(hits)}\n\nPergunta: {question}"
            completion = self.llm.complete(SYSTEM_PROMPT, [{"role": "user", "content": prompt}])
            span.input_tokens, span.output_tokens = completion.input_tokens, completion.output_tokens

            valid, invalid = split_citations(completion.text, hits)
            span.extra.update(citations=len(valid), invalid_citations=len(invalid), abstained=False)
            return Answer(completion.text.strip(), valid, invalid, False, hits)
