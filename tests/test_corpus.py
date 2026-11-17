from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.corpus import CorpusError, load_corpus
from tests.conftest import CORPUS_PATH

ALLOWED = ("law.go.kr", "www.law.go.kr", "example.com")


def load(path: Path, min_chars: int = 40):
    return load_corpus(path, allowed_hosts=ALLOWED, min_excerpt_chars=min_chars)


def variant(tmp_path: Path, mutate) -> Path:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "documents.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def doc(payload: dict, document_id: str) -> dict:
    return next(item for item in payload["documents"] if item["document_id"] == document_id)


def test_loads_expected_documents() -> None:
    corpus = load(CORPUS_PATH)
    assert len(corpus.documents) == 14
    assert len(corpus.public_documents) == 10
    assert {doc.source_tier for doc in corpus.documents} == {"public_summary", "synthetic_fixture"}


def test_corpus_hash_is_raw_file_sha256() -> None:
    corpus = load(CORPUS_PATH)
    expected = hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()
    assert corpus.sha256 == expected


def test_corpus_hash_is_stable_across_loads() -> None:
    assert load(CORPUS_PATH).sha256 == load(CORPUS_PATH).sha256


def test_duplicate_document_id_rejected(tmp_path: Path) -> None:
    def mutate(payload):
        payload["documents"].append(dict(doc(payload, "pps-price-survey")))

    with pytest.raises(CorpusError):
        load(variant(tmp_path, mutate))


def test_public_document_requires_source_url(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "pps-price-survey")["source_url"] = ""

    with pytest.raises(CorpusError, match="source_url"):
        load(variant(tmp_path, mutate))


def test_public_document_rejects_non_https(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "pps-price-survey")["source_url"] = "http://www.law.go.kr/x"

    with pytest.raises(CorpusError, match="https"):
        load(variant(tmp_path, mutate))


def test_public_document_rejects_unknown_host(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "pps-price-survey")["source_url"] = "https://example.com/x"

    with pytest.raises(CorpusError, match="호스트"):
        load(variant(tmp_path, mutate))


def test_synthetic_fixture_rejects_public_host(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "fixture-goods-guarantee-10")["source_url"] = "https://www.law.go.kr/x"

    with pytest.raises(CorpusError, match="example.com"):
        load(variant(tmp_path, mutate))


def test_short_excerpt_rejected(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "pps-price-survey")["excerpt"] = "짧음"

    with pytest.raises(CorpusError, match="짧"):
        load(variant(tmp_path, mutate))


def test_excerpt_must_be_substring_of_content(tmp_path: Path) -> None:
    def mutate(payload):
        target = doc(payload, "pps-price-survey")
        target["excerpt"] = "이 문장은 본문에 존재하지 않는 검증용 발췌 문장입니다. 길이는 충분합니다."

    with pytest.raises(CorpusError, match="본문"):
        load(variant(tmp_path, mutate))


def test_ellipsis_excerpt_rejected(tmp_path: Path) -> None:
    def mutate(payload):
        target = doc(payload, "pps-price-survey")
        target["excerpt"] = target["excerpt"] + "…"
        target["content"] = target["content"] + "…"

    with pytest.raises(CorpusError, match="말줄임표"):
        load(variant(tmp_path, mutate))


def test_duplicate_excerpt_rejected(tmp_path: Path) -> None:
    def mutate(payload):
        first = doc(payload, "pps-price-survey")
        second = doc(payload, "pps-design-competition")
        second["excerpt"] = first["excerpt"]
        second["content"] = first["excerpt"] + " 추가 문장."

    with pytest.raises(CorpusError, match="중복 발췌"):
        load(variant(tmp_path, mutate))


def test_synthetic_policy_requires_scope_and_value(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "fixture-goods-guarantee-10")["policy_value"] = None

    with pytest.raises(CorpusError, match="policy_key"):
        load(variant(tmp_path, mutate))


def test_invalid_effective_date_rejected(tmp_path: Path) -> None:
    def mutate(payload):
        doc(payload, "pps-price-survey")["effective_from"] = "not-a-date"

    with pytest.raises(CorpusError, match="유효기간"):
        load(variant(tmp_path, mutate))


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "missing.json")
