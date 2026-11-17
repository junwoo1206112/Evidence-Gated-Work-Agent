from __future__ import annotations

import pytest

from app.services.corpus import load_corpus
from app.services.retrieval import Retriever, korean_bigrams, strip_particle
from tests.conftest import (
    CONFLICT_REQUEST,
    CORPUS_PATH,
    INSUFFICIENT_REQUEST,
    LOW_SCORE_REQUEST,
    SUFFICIENT_REQUEST,
)

ALLOWED = ("law.go.kr", "www.law.go.kr", "example.com")


@pytest.fixture
def corpus():
    return load_corpus(CORPUS_PATH, allowed_hosts=ALLOWED, min_excerpt_chars=40)


@pytest.fixture
def retriever(corpus):
    return Retriever(corpus)


def ids(hits):
    return [hit.document.document_id for hit in hits]


def test_particle_and_stopword_stripping() -> None:
    assert strip_particle("계약보증금과") == "계약보증금"
    assert strip_particle("지연배상금을") == "지연배상금"
    assert strip_particle("기준으로") == "기준"
    assert strip_particle("서울") == "서울"
    assert Retriever.query_terms("계약보증금과 지연배상금을 확인해 초안을 작성해줘") == [
        "계약보증금",
        "지연배상금",
    ]


def test_korean_bigrams() -> None:
    assert korean_bigrams("계약") == ["계약"]
    assert korean_bigrams("계약보증금") == ["계약", "약보", "보증", "증금"]
    assert korean_bigrams("A") == []


def test_sufficient_query_matches_two_public_documents(retriever) -> None:
    hits = retriever.search(SUFFICIENT_REQUEST, top_k=5)
    found = ids(hits)
    assert "pps-facility-contract-delay" in found
    assert "pps-facility-contract-guarantee" in found
    assert hits[0].score > 0.6
    # The score must be absolute, not min-max normalized: only the top hit may
    # reach 1.0 and the runner-up must remain visibly lower.
    assert hits[1].score < 0.9


def test_conflict_query_reaches_contradictory_fixtures(retriever) -> None:
    hits = retriever.search(CONFLICT_REQUEST, top_k=5)
    found = ids(hits)
    assert "fixture-goods-guarantee-10" in found
    assert "fixture-goods-guarantee-5" in found
    top = [hit for hit in hits if hit.document.document_id.startswith("fixture-goods-guarantee")][:2]
    assert all(hit.score >= 0.42 for hit in top)


def test_low_score_query_stays_below_threshold(retriever) -> None:
    hits = retriever.search(LOW_SCORE_REQUEST, top_k=5)
    assert hits
    assert all(hit.score < 0.42 for hit in hits)


def test_insufficient_query_stays_below_threshold(retriever) -> None:
    hits = retriever.search(INSUFFICIENT_REQUEST, top_k=5)
    assert all(hit.score < 0.42 for hit in hits)


def test_domain_out_query_has_no_candidates(retriever) -> None:
    assert retriever.search("오늘 점심 메뉴 추천", top_k=5) == []


def test_search_order_is_deterministic(retriever) -> None:
    first = [(hit.document.document_id, hit.score) for hit in retriever.search(SUFFICIENT_REQUEST, top_k=5)]
    second = [(hit.document.document_id, hit.score) for hit in retriever.search(SUFFICIENT_REQUEST, top_k=5)]
    assert first == second


def test_query_without_content_terms_returns_empty(retriever) -> None:
    assert retriever.search("확인해 작성해줘", top_k=5) == []


def test_matched_terms_are_reported_for_explainability(retriever) -> None:
    hits = retriever.search(SUFFICIENT_REQUEST, top_k=1)
    assert hits[0].matched_terms
