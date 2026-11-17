from __future__ import annotations

from datetime import date

import pytest

from app.domain.models import GatePass
from app.services.corpus import CorpusDocument
from app.services.retrieval import RetrievalHit
from app.services.planner import build_plan
from tests.conftest import CONFLICT_REQUEST, LOW_SCORE_REQUEST, SUFFICIENT_REQUEST

AS_OF = date(2026, 11, 17)


@pytest.fixture
def gate(app):
    return app.state.service.gate


@pytest.fixture
def retriever(app):
    return app.state.service.retriever


def evaluate(gate, retriever, query: str):
    return gate.evaluate("run_test", retriever.search(query, 5), AS_OF)


def make_doc(**overrides) -> CorpusDocument:
    base = {
        "document_id": "test-doc",
        "title": "테스트 문서",
        "section": "테스트 조항",
        "source_url": "https://www.law.go.kr/LSW/test",
        "source_tier": "public_summary",
        "excerpt": "테스트 문서의 검증용 발췌 문장입니다. 충분히 긴 문장으로 구성했습니다.",
        "content": "테스트 문서의 검증용 발췌 문장입니다. 충분히 긴 문장으로 구성했습니다. 추가 본문입니다.",
        "policy_key": None,
        "policy_scope": None,
        "policy_value": None,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "usage_basis": "테스트",
        "excerpt_type": "summary",
    }
    base.update(overrides)
    return CorpusDocument(**base)


def make_hit(document: CorpusDocument, score: float = 0.9) -> RetrievalHit:
    return RetrievalHit(
        document=document,
        score=score,
        coverage=0.9,
        bm25=1.0,
        matched_terms=("테스트",),
    )


def test_sufficient_query_passes(gate, retriever) -> None:
    result = evaluate(gate, retriever, SUFFICIENT_REQUEST)
    assert result.passed
    assert result.category is None
    assert result.public_valid_count >= 2
    assert result.valid_count >= 2


def test_low_score_query_is_blocked(gate, retriever) -> None:
    result = evaluate(gate, retriever, LOW_SCORE_REQUEST)
    assert not result.passed
    assert result.category == "low_score"
    assert result.public_valid_count == 0


def test_conflict_is_detected_and_blocks(gate, retriever) -> None:
    result = evaluate(gate, retriever, CONFLICT_REQUEST)
    assert not result.passed
    assert result.category == "conflict"
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["policy_key"] == "goods_contract_guarantee_rate"
    assert {item["value"] for item in result.conflicts[0]["values"]} == {"10%", "5%"}
    # Synthetic fixtures never count toward the public citation minimum.
    assert result.public_valid_count == 1


def test_missing_url_is_invalid(gate, retriever) -> None:
    from tests.conftest import MISSING_URL_REQUEST

    result = evaluate(gate, retriever, MISSING_URL_REQUEST)
    assert not result.passed
    assert result.category == "invalid_citation"
    assert result.checks[0].invalid_reason == "missing_source_url"


def test_superseded_evidence_is_invalid(gate, retriever) -> None:
    result = evaluate(gate, retriever, "물품 계약보증금 비율 기준을 확인해줘")
    old = next(check for check in result.checks if check.document_id == "fixture-goods-guarantee-old")
    assert not old.citation_valid
    assert "superseded" in old.invalid_reasons


@pytest.mark.parametrize(
    ("url", "tier", "reason"),
    [
        ("http://www.law.go.kr/x", "public_summary", "url_not_https"),
        ("https://evil.example.org/x", "public_summary", "url_host_not_allowed"),
        ("https://user:pass@www.law.go.kr/x", "public_summary", "url_has_credentials"),
        ("https://127.0.0.1/x", "public_summary", "url_ip_host"),
        ("https://www.law.go.kr:8443/x", "public_summary", "url_has_port"),
        ("https://www.law.go.kr/x", "synthetic_fixture", "url_host_not_allowed"),
        ("", "public_summary", "missing_source_url"),
    ],
)
def test_url_validation_matrix(gate, url: str, tier: str, reason: str) -> None:
    check = gate._validate_url(url, tier)
    assert not check.ok
    assert check.reason == reason


def test_valid_urls(gate) -> None:
    assert gate._validate_url("https://www.law.go.kr/LSW/x?seq=1", "public_summary").ok
    assert gate._validate_url("https://example.com/fixture", "synthetic_fixture").ok


def test_excerpt_checks(gate) -> None:
    short = make_doc(excerpt="짧음", content="짧음")
    check = gate._check_document(short, make_hit(short), AS_OF)
    assert "excerpt_too_short" in check.invalid_reasons

    ellipsis = make_doc(
        excerpt="가" * 45 + "…",
        content="가" * 45 + "…",
    )
    check = gate._check_document(ellipsis, make_hit(ellipsis), AS_OF)
    assert "excerpt_has_ellipsis" in check.invalid_reasons

    mismatch = make_doc(
        excerpt="나" * 50,
        content="다" * 50,
    )
    check = gate._check_document(mismatch, make_hit(mismatch), AS_OF)
    assert "excerpt_not_in_content" in check.invalid_reasons


def test_low_score_and_effective_dates(gate) -> None:
    low = make_doc()
    check = gate._check_document(low, make_hit(low, score=0.1), AS_OF)
    assert "below_min_score" in check.invalid_reasons

    expired = make_doc(effective_to="2020-01-01")
    check = gate._check_document(expired, make_hit(expired), AS_OF)
    assert "superseded" in check.invalid_reasons

    future = make_doc(effective_from="2030-01-01")
    check = gate._check_document(future, make_hit(future), AS_OF)
    assert "not_yet_effective" in check.invalid_reasons


def test_duplicate_document_is_invalid(gate) -> None:
    document = make_doc()
    result = gate.evaluate(
        "run_dup",
        [make_hit(document), make_hit(document)],
        AS_OF,
    )
    assert result.valid_count == 1
    assert "duplicate_document" in result.checks[1].invalid_reasons


def test_fingerprint_changes_with_score(gate, retriever) -> None:
    first = evaluate(gate, retriever, SUFFICIENT_REQUEST)
    hit = make_hit(make_doc(), score=0.95)
    second = gate.evaluate("run_test", [hit], AS_OF)
    assert gate.fingerprint(first.checks) != gate.fingerprint(second.checks)
    assert gate.fingerprint(first.checks) == gate.fingerprint(first.checks)


def test_gate_pass_cannot_be_constructed_directly() -> None:
    with pytest.raises(ValueError):
        GatePass(
            run_id="run_x",
            document_ids=("a", "b"),
            evidence_fingerprint="x",
            config_hash="y",
            corpus_sha256="z",
            as_of="2026-11-17",
        )


def test_planner_requires_gate_pass() -> None:
    with pytest.raises(TypeError):
        build_plan(SUFFICIENT_REQUEST, None)  # type: ignore[arg-type]


def test_failed_gate_cannot_make_pass(gate, retriever) -> None:
    result = evaluate(gate, retriever, LOW_SCORE_REQUEST)
    with pytest.raises(ValueError):
        gate.make_pass(result)


def test_conflict_scan_is_not_limited_to_valid_top_k(gate, retriever) -> None:
    documents = {document.document_id: document for document in gate._documents}
    hits = [
        make_hit(documents["pps-facility-contract-guarantee"]),
        make_hit(documents["pps-facility-contract-delay"]),
        make_hit(documents["fixture-goods-guarantee-5"]),
    ]
    # The contradictory 10% fixture is NOT in the hits. A corpus-wide scan for
    # the tagged policy key must still find it.
    result = gate.evaluate("run_hidden_conflict", hits, AS_OF)
    assert not result.passed
    assert result.category == "conflict"
    assert {item["value"] for item in result.conflicts[0]["values"]} == {"5%", "10%"}


def test_policy_value_normalization() -> None:
    from app.textutil import normalize_policy_value

    assert normalize_policy_value("10%") == normalize_policy_value("100분의 10")
    assert normalize_policy_value("5%") != normalize_policy_value("10%")
