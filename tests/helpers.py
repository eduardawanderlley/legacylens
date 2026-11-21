from __future__ import annotations

from legacylens.embeddings import HashingEmbedder
from legacylens.ingest.chunker import chunk_python_source
from legacylens.llm import Completion
from legacylens.retrieval import Retriever
from legacylens.store import Store

PAYMENTS = '''"""Pagamentos."""
import decimal
from .audit import log_event


def _luhn_ok(number):
    digits = [int(d) for d in number if d.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PaymentService:
    """Orquestra cobranças."""

    retries = 3

    def validate_payment(self, card_number, amount):
        """Valida cartão e valor antes de cobrar."""
        if amount <= 0:
            raise ValueError("valor inválido")
        if not _luhn_ok(card_number):
            log_event("card_rejected")
            return False
        return True

    @staticmethod
    def fee(amount):
        return decimal.Decimal(amount) * decimal.Decimal("0.03")

    def charge(self, card_number, amount):
        if not self.validate_payment(card_number, amount):
            return None
        return amount + self.fee(amount)
'''

AUDIT = '''def log_event(name):
    """Registra evento de auditoria."""
    print(name)
'''


def build_index() -> tuple[Store, Retriever]:
    store = Store(":memory:")
    embedder = HashingEmbedder()
    chunks = chunk_python_source("app/payments.py", PAYMENTS) + chunk_python_source("app/audit.py", AUDIT)
    store.add(chunks, embedder.embed([f"{c.path} {c.name}\n{c.text}" for c in chunks]))
    return store, Retriever(store, embedder)


class ScriptedLLM:
    """LLM de teste: devolve respostas pré-definidas em ordem e guarda as chamadas."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete(self, system, messages, max_tokens=1500):
        self.calls.append(messages)
        return Completion(self.replies.pop(0), input_tokens=100, output_tokens=20)
