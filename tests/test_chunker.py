from legacylens.ingest.chunker import chunk_python_source
from legacylens.text import split_identifier

from helpers import PAYMENTS


def by_name(chunks):
    return {c.name: c for c in chunks}


def test_one_chunk_per_function_and_method():
    names = set(by_name(chunk_python_source("app/payments.py", PAYMENTS)))
    assert {"_luhn_ok", "PaymentService", "PaymentService.validate_payment", "PaymentService.fee", "PaymentService.charge"} <= names


def test_function_is_never_split_and_lines_match_source():
    chunk = by_name(chunk_python_source("app/payments.py", PAYMENTS))["PaymentService.validate_payment"]
    lines = PAYMENTS.splitlines()
    assert chunk.text == "\n".join(lines[chunk.start_line - 1 : chunk.end_line])
    assert chunk.text.rstrip().endswith("return True")


def test_decorator_is_part_of_the_chunk():
    chunk = by_name(chunk_python_source("app/payments.py", PAYMENTS))["PaymentService.fee"]
    assert chunk.text.lstrip().startswith("@staticmethod")


def test_class_chunk_stops_before_first_method():
    chunk = by_name(chunk_python_source("app/payments.py", PAYMENTS))["PaymentService"]
    assert "retries = 3" in chunk.text
    assert "def validate_payment" not in chunk.text


def test_calls_and_docstring_are_extracted():
    chunk = by_name(chunk_python_source("app/payments.py", PAYMENTS))["PaymentService.validate_payment"]
    assert {"_luhn_ok", "log_event"} <= set(chunk.calls)
    assert chunk.docstring == "Valida cartão e valor antes de cobrar."


def test_syntax_error_returns_empty():
    assert chunk_python_source("old.py", "print 'python 2'") == []


def test_split_identifier():
    assert split_identifier("validatePayment_v2") == ["validate", "payment", "v2"]
    assert split_identifier("HTTPServer") == ["http", "server"]
