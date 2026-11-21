from pathlib import Path

from legacylens.config import Settings
from legacylens.telemetry import Telemetry
from legacylens.testgen import RunResult, TestGenerator
from legacylens.testgen.generator import check_test_quality, extract_code, module_name
from legacylens.testgen.mutation import parse_junit

from helpers import ScriptedLLM, build_index

GOOD = "```python\nfrom app.payments import PaymentService\n\ndef test_fee():\n    assert PaymentService.fee(100) == 3\n```"
VACUOUS = "```python\ndef test_nothing():\n    pass\n```"


class FakeRunner:
    """Passa só se o arquivo contiver a marca esperada; registra as execuções."""

    def __init__(self, *outcomes: bool) -> None:
        self.outcomes = list(outcomes)
        self.runs = 0

    def run(self, test_file: Path, cwd: Path) -> RunResult:
        self.runs += 1
        ok = self.outcomes.pop(0)
        return RunResult(ok, "" if ok else "E   assert 3.00 == 3\nFAILED")


def make(tmp_path, llm, runner, attempts=3):
    store, _ = build_index()
    settings = Settings(log_path=tmp_path / "t.jsonl")
    return TestGenerator(store, llm, runner, tmp_path, Telemetry(settings), max_attempts=attempts)


def test_passes_on_first_try(tmp_path):
    gen = make(tmp_path, ScriptedLLM(GOOD), FakeRunner(True))
    result = gen.generate("app/payments.py::PaymentService.fee")
    assert result.passed and result.first_try and result.test_path.exists()


def test_error_output_is_sent_back_and_second_attempt_can_pass(tmp_path):
    llm = ScriptedLLM(GOOD, GOOD)
    result = make(tmp_path, llm, FakeRunner(False, True)).generate("PaymentService.fee")
    assert result.passed and not result.first_try and len(result.attempts) == 2
    assert "assert 3.00 == 3" in llm.calls[1][-1]["content"]


def test_gives_up_and_leaves_no_failing_file(tmp_path):
    result = make(tmp_path, ScriptedLLM(GOOD, GOOD), FakeRunner(False, False), attempts=2).generate("PaymentService.fee")
    assert not result.passed and result.test_path is None
    assert not list((tmp_path / ".legacylens" / "generated").glob("*.py"))


def test_vacuous_test_is_rejected_without_running(tmp_path):
    runner = FakeRunner(True)
    result = make(tmp_path, ScriptedLLM(VACUOUS, GOOD), runner).generate("PaymentService.fee")
    assert result.passed and runner.runs == 1
    assert "não verifica nada" in result.attempts[0].output


def test_ambiguous_or_missing_target_raises(tmp_path):
    gen = make(tmp_path, ScriptedLLM(), FakeRunner())
    for bad in ("nao_existe", "app/payments.py::nao_existe"):
        try:
            gen.generate(bad)
        except LookupError:
            continue
        raise AssertionError(f"deveria falhar para {bad}")


def test_helpers():
    assert extract_code("texto\n```python\nx = 1\n```") == "x = 1\n"
    assert extract_code("sem código") is None
    assert check_test_quality("def test_a():\n    assert True") is None
    assert "SyntaxError" in check_test_quality("def (")
    assert module_name("src/pkg/mod.py") == "pkg.mod"


def test_parse_mutmut_junit():
    xml = '<testsuites><testsuite tests="10" failures="3" errors="1" skipped="0"></testsuite></testsuites>'
    result = parse_junit(xml)
    assert (result.killed, result.survived, result.other) == (6, 3, 1)
    assert abs(result.score - 6 / 9) < 1e-9
