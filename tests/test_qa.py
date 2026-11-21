from legacylens.config import Settings
from legacylens.qa import NO_EVIDENCE, CodebaseQA, split_citations
from legacylens.telemetry import Telemetry

from helpers import ScriptedLLM, build_index


def make_qa(tmp_path, llm, min_overlap=0.0):
    settings = Settings(log_path=tmp_path / "t.jsonl", min_evidence_overlap=min_overlap)
    _, retriever = build_index()
    return CodebaseQA(retriever, llm, settings, Telemetry(settings))


def test_overlap_gate_abstains_without_calling_the_llm(tmp_path):
    llm = ScriptedLLM()
    answer = make_qa(tmp_path, llm, min_overlap=0.34).ask("how does kubernetes load balancing work?")
    assert answer.abstained and answer.text == NO_EVIDENCE
    assert llm.calls == []


def test_answer_keeps_only_citations_that_exist_in_the_evidence(tmp_path):
    store, _ = build_index()
    v = store.find_by_name("PaymentService.validate_payment")[0]
    llm = ScriptedLLM(f"A validação ocorre em [{v.ref}], mas também em [app/outro.py:1-5].")
    answer = make_qa(tmp_path, llm).ask("onde validate_payment valida o cartão?")
    assert not answer.abstained
    assert answer.citations == [v.ref]
    assert answer.invalid_citations == ["app/outro.py:1-5"]


def test_citation_inside_a_retrieved_range_is_accepted(tmp_path):
    store, retriever = build_index()
    hits = retriever.search("validate_payment", k=2)
    v = next(h.chunk for h in hits if h.chunk.name == "PaymentService.validate_payment")
    inner = f"{v.path}:{v.start_line + 1}-{v.start_line + 2}"
    valid, invalid = split_citations(f"veja [{inner}]", hits)
    assert valid == [inner] and invalid == []


def test_telemetry_records_tokens_and_latency(tmp_path):
    store, _ = build_index()
    v = store.find_by_name("PaymentService.validate_payment")[0]
    make_qa(tmp_path, ScriptedLLM(f"[{v.ref}]")).ask("onde validate_payment valida o cartão?")
    line = (tmp_path / "t.jsonl").read_text().splitlines()[-1]
    assert '"input_tokens": 100' in line and '"latency_ms"' in line
