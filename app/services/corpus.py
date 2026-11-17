from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.textutil import normalize_text, parse_date, sha256_bytes


class CorpusError(ValueError):
    pass


@dataclass(frozen=True)
class CorpusDocument:
    document_id: str
    title: str
    section: str
    source_url: str
    source_tier: str
    excerpt: str
    content: str
    policy_key: str | None
    policy_scope: str | None
    policy_value: str | None
    effective_from: str | None
    effective_to: str | None
    usage_basis: str
    excerpt_type: str

    def snapshot(self) -> dict:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "section": self.section,
            "source_url": self.source_url,
            "source_tier": self.source_tier,
            "excerpt": self.excerpt,
            "content": self.content,
            "policy_key": self.policy_key,
            "policy_scope": self.policy_scope,
            "policy_value": self.policy_value,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "usage_basis": self.usage_basis,
            "excerpt_type": self.excerpt_type,
        }


@dataclass(frozen=True)
class Corpus:
    version: str
    sha256: str
    documents: tuple[CorpusDocument, ...]
    by_id: dict[str, CorpusDocument]

    @property
    def public_documents(self) -> tuple[CorpusDocument, ...]:
        return tuple(doc for doc in self.documents if doc.source_tier == "public_summary")


def _canonical_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() != "https":
        raise CorpusError(f"https URL만 허용합니다: {value}")
    if parts.username or parts.password:
        raise CorpusError(f"URL에 사용자 정보가 포함될 수 없습니다: {value}")
    host = (parts.hostname or "").lower()
    if not host:
        raise CorpusError(f"URL 호스트가 없습니다: {value}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise CorpusError(f"IP 주소 URL은 허용하지 않습니다: {value}")
    if parts.port is not None and parts.port != 443:
        raise CorpusError(f"기본 포트 외 URL은 허용하지 않습니다: {value}")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def load_corpus(path: Path, *, allowed_hosts: tuple[str, ...], min_excerpt_chars: int) -> Corpus:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"코퍼스 JSON을 읽을 수 없습니다: {exc}") from exc

    version = str(payload.get("corpus_version", "")).strip()
    if not version:
        raise CorpusError("corpus_version이 필요합니다.")

    documents: list[CorpusDocument] = []
    seen_ids: set[str] = set()
    seen_excerpts: set[str] = set()
    allowed = {host.lower() for host in allowed_hosts}

    for item in payload.get("documents", []):
        document_id = normalize_text(str(item.get("document_id", "")))
        title = normalize_text(str(item.get("title", "")))
        section = normalize_text(str(item.get("section", "")))
        if not document_id or not title or not section:
            raise CorpusError("document_id, title, section은 필수입니다.")
        if document_id in seen_ids:
            raise CorpusError(f"중복 document_id: {document_id}")
        seen_ids.add(document_id)

        source_tier = str(item.get("source_tier", "")).strip()
        if source_tier not in {"public_summary", "synthetic_fixture"}:
            raise CorpusError(f"알 수 없는 source_tier: {source_tier} ({document_id})")

        raw_url = str(item.get("source_url", ""))
        if source_tier == "public_summary" and not raw_url:
            raise CorpusError(f"공개 문서에 source_url이 없습니다: {document_id}")
        source_url = _canonical_url(raw_url) if raw_url else ""
        if source_url:
            host = urlsplit(source_url).hostname or ""
            if source_tier == "public_summary" and (host not in allowed or host == "example.com"):
                raise CorpusError(f"허용되지 않은 출처 호스트입니다: {host} ({document_id})")
            if source_tier == "synthetic_fixture" and host != "example.com":
                raise CorpusError(f"합성 fixture는 example.com만 사용할 수 있습니다: {document_id}")

        excerpt = normalize_text(str(item.get("excerpt", "")))
        content = normalize_text(str(item.get("content", "")))
        if len(excerpt) < min_excerpt_chars:
            raise CorpusError(f"발췌가 너무 짧습니다({len(excerpt)}자): {document_id}")
        if excerpt.endswith("...") or "…" in excerpt:
            raise CorpusError(f"말줄임표가 포함된 발췌는 인용으로 인정하지 않습니다: {document_id}")
        if excerpt not in content:
            raise CorpusError(f"발췌가 본문에 포함되지 않습니다: {document_id}")
        if excerpt in seen_excerpts:
            raise CorpusError(f"중복 발췌: {document_id}")
        for existing in documents:
            if excerpt in existing.excerpt or existing.excerpt in excerpt:
                raise CorpusError(f"발췌가 다른 문서와 구분되지 않습니다: {document_id}")
        seen_excerpts.add(excerpt)

        effective_from = item.get("effective_from")
        effective_to = item.get("effective_to")
        try:
            parse_date(effective_from)
            parse_date(effective_to)
        except ValueError as exc:
            raise CorpusError(f"유효기간 형식이 잘못되었습니다: {document_id}") from exc

        policy_key = item.get("policy_key")
        policy_scope = item.get("policy_scope")
        policy_value = item.get("policy_value")
        if policy_key and (not policy_scope or not policy_value):
            raise CorpusError(f"policy_key에는 scope와 value가 필요합니다: {document_id}")

        documents.append(
            CorpusDocument(
                document_id=document_id,
                title=title,
                section=section,
                source_url=source_url,
                source_tier=source_tier,
                excerpt=excerpt,
                content=content,
                policy_key=policy_key,
                policy_scope=policy_scope,
                policy_value=policy_value,
                effective_from=effective_from,
                effective_to=effective_to,
                usage_basis=normalize_text(str(item.get("usage_basis", ""))),
                excerpt_type=normalize_text(str(item.get("excerpt_type", ""))),
            )
        )

    if len(documents) < 5:
        raise CorpusError("코퍼스 문서가 너무 적습니다.")
    if not any(doc.source_tier == "public_summary" for doc in documents):
        raise CorpusError("공개 문서가 최소 1개 필요합니다.")

    by_id = {doc.document_id: doc for doc in documents}
    return Corpus(
        version=version,
        sha256=sha256_bytes(raw),
        documents=tuple(documents),
        by_id=by_id,
    )
