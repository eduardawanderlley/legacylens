import json

from legacylens.evaluation import evaluate_answers, evaluate_retrieval, load_questions
from legacylens.config import Settings
from legacylens.pr import changed_functions, changed_ranges
from legacylens.qa import CodebaseQA
from legacylens.retrieval import SearchMode
from legacylens.telemetry import Telemetry

from helpers import ScriptedLLM, build_index


def write_dataset(tmp_path, store):
    v = store.find_by_name("PaymentService.validate_payment")[0]
    rows = [
        {"id": "q1", "question": "onde validate_payment valida o cartão?", "gold": [dict(path=v.path, start_line=v.start_line, end_line=v.end_line)]},
        {"id": "q2", "question": "how does kubernetes load balancing work?", "answerable": False, "gold": []},
    ]
    path = tmp_path / "gold.jsonl"
    path.write_text("# comentário\n" + "\n".join(json.dumps(r) for r in rows))
    return path


def test_retrieval_metrics(tmp_path):
    store, retriever = build_index()
    questions = load_questions(write_dataset(tmp_path, store))
    report = evaluate_retrieval(retriever, questions, k=3, mode=SearchMode.HYBRID)
    assert report["questions"] == 1 and report["recall@3"] == 1.0 and 0 < report["mrr"] <= 1


def test_answer_metrics(tmp_path):
    store, retriever = build_index()
    questions = load_questions(write_dataset(tmp_path, store))
    v = store.find_by_name("PaymentService.validate_payment")[0]
    settings = Settings(log_path=tmp_path / "t.jsonl", min_evidence_overlap=0.34)
    qa = CodebaseQA(retriever, ScriptedLLM(f"[{v.ref}]"), settings, Telemetry(settings))
    report = evaluate_answers(qa, questions)
    assert report["citation_correct"] == 1.0 and report["abstention_correct"] == 1.0
    assert report["false_abstention"] == 0.0


def test_bad_dataset_line_reports_file_and_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "x"}\n')
    try:
        load_questions(path)
    except ValueError as exc:
        assert "bad.jsonl:1" in str(exc)
    else:
        raise AssertionError("deveria falhar")


DIFF = """diff --git a/app/payments.py b/app/payments.py
--- a/app/payments.py
+++ b/app/payments.py
@@ -25,0 +26,2 @@ class PaymentService:
+        pass
+        pass
@@ -40 +42 @@ def x
-a
+b
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-a
+b
"""


def test_changed_ranges_ignores_pure_deletions():
    ranges = changed_ranges("+++ b/a.py\n@@ -5,2 +5,0 @@\n-x\n-y\n")
    assert ranges == {}
    assert changed_ranges(DIFF)["app/payments.py"] == [(26, 27), (42, 42)]


def test_changed_functions_maps_lines_to_chunks_and_skips_non_python():
    store, _ = build_index()
    names = {c.name for c in changed_functions(store, DIFF)}
    assert "PaymentService.validate_payment" in names
