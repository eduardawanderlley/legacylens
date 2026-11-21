from legacylens.retrieval import SearchMode

from helpers import build_index


def test_exact_identifier_is_found_by_bm25():
    _, retriever = build_index()
    hits = retriever.search("validate_payment", k=3, mode=SearchMode.BM25)
    assert hits[0].chunk.name == "PaymentService.validate_payment"


def test_hybrid_puts_the_right_function_first():
    _, retriever = build_index()
    hits = retriever.search("onde é feita a validação do cartão com luhn", k=3, mode=SearchMode.HYBRID)
    assert hits[0].chunk.name in {"_luhn_ok", "PaymentService.validate_payment"}


def test_graph_expansion_adds_callees_marked_as_graph():
    _, retriever = build_index()
    hits = retriever.search("charge", k=1, mode=SearchMode.HYBRID_GRAPH)
    graph = [h for h in hits if h.via == "graph"]
    assert hits[0].chunk.name == "PaymentService.charge"
    assert {h.chunk.name for h in graph} & {"PaymentService.validate_payment", "PaymentService.fee"}


def test_graph_neighbours_never_duplicate_direct_hits():
    _, retriever = build_index()
    hits = retriever.search("charge validate_payment", k=4)
    ids = [h.chunk.id for h in hits]
    assert len(ids) == len(set(ids))


def test_store_callers_and_callees():
    store, _ = build_index()
    validate = store.find_by_name("PaymentService.validate_payment")[0]
    assert "charge" in {c.simple_name for c in store.callers_of("validate_payment")}
    assert "_luhn_ok" in {c.name for c in store.callees_of(validate)}


def test_empty_query_returns_nothing():
    _, retriever = build_index()
    assert retriever.search("???", k=3, mode=SearchMode.BM25) == []
