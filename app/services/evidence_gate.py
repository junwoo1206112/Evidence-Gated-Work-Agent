from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable
from urllib.parse import urlsplit

from app.config import Settings
from app.domain.models import (
    EvidenceCheck,
    EvidenceRecord,
    GatePass,
    GateResult,
    _make_gate_pass,
)
from app.services.corpus import CorpusDocument
from app.services.retrieval import RetrievalHit
from app.textutil import (
    canonical_json,
    normalize_policy_value,
    normalize_text,
    parse_date,
    sha256_text,
)

REASON_LABELS = {
    "missing_source_url": "출처 URL이 없습니다.",
    "url_not_https": "출처 URL이 https가 아닙니다.",
    "url_host_not_allowed": "허용된 공개 출처 도메인이 아닙니다.",
    "url_has_credentials": "URL에 사용자 정보가 포함되어 있습니다.",
    "url_has_port": "기본 포트가 아닌 URL입니다.",
    "url_ip_host": "IP 주소를 호스트로 사용하는 URL입니다.",
    "excerpt_too_short": "인용 발췌가 최소 길이보다 짧습니다.",
    "excerpt_not_in_content": "인용 발췌가 문서 본문에 포함되지 않습니다.",
    "excerpt_has_ellipsis": "말줄임표가 포함된 발췌는 인용으로 인정하지 않습니다.",
    "below_min_score": "검색 점수가 기준 미만입니다.",
    "not_yet_effective": "아직 시행되지 않은 근거입니다.",
    "superseded": "유효기간이 지난 근거입니다.",
    "invalid_source_tier": "근거 등급을 알 수 없습니다.",
    "invalid_policy_metadata": "상충 비교에 필요한 정책 메타데이터가 없습니다.",
    "duplicate_document": "동일 문서가 중복 검색되었습니다.",
    "synthetic_only": "합성 fixture는 공개 인용 최소 수에 포함되지 않습니다.",
}


@dataclass(frozen=True)
class _UrlCheck:
    ok: bool
    reason: str | None
    detail: str | None


class EvidenceGate:
    """Pure evidence policy.

    The gate is the only producer of GatePass. Planner requires a GatePass, so a
    route or helper cannot skip the gate by calling the planner directly.
    """

    def __init__(self, settings: Settings, corpus_sha256: str, documents=()) -> None:
        self.settings = settings
        self.corpus_sha256 = corpus_sha256
        self.config_hash = settings.gate_config_hash()
        self._documents = tuple(documents)

    # -- public API ---------------------------------------------------------

    def evaluate(self, run_id: str, hits: Iterable[RetrievalHit], as_of: date) -> GateResult:
        checks: list[EvidenceCheck] = []
        seen: set[str] = set()
        for hit in hits:
            duplicate = hit.document.document_id in seen
            seen.add(hit.document.document_id)
            checks.append(self._check_document(hit.document, hit, as_of, duplicate=duplicate))
        return self._result(run_id, checks, as_of)

    def revalidate(
        self,
        run_id: str,
        records: Iterable[EvidenceRecord],
        as_of: date,
        *,
        corpus_sha256: str,
        config_hash: str,
    ) -> tuple[GateResult, bool]:
        """Re-check stored evidence only. Never re-runs retrieval.

        Returns (gate_result, stored_values_tampered). The caller separately
        compares config/corpus hashes and the evidence fingerprint.
        """

        checks: list[EvidenceCheck] = []
        tampered = False
        for record in records:
            snapshot = self._load_snapshot(record)
            document = self._document_from_snapshot(snapshot)
            hit = RetrievalHit(
                document=document,
                score=record.retrieval_score,
                coverage=record.coverage,
                bm25=record.bm25,
                matched_terms=record.matched_terms,
            )
            check = self._check_document(document, hit, as_of, duplicate=False)
            if bool(record.citation_valid) != check.citation_valid:
                tampered = True
            if record.invalid_reason != check.invalid_reason:
                tampered = True
            # The snapshot is authoritative. A mismatch between the denormalized
            # evidence columns and the snapshot is also treated as tampering.
            if (
                record.document_id != document.document_id
                or record.title != document.title
                or record.section != document.section
                or record.excerpt != document.excerpt
                or record.source_url != document.source_url
                or record.source_tier != document.source_tier
                or record.policy_key != document.policy_key
                or record.policy_scope != document.policy_scope
                or record.policy_value != document.policy_value
                or record.effective_from != document.effective_from
                or record.effective_to != document.effective_to
                or abs(record.retrieval_score - check.score) > 1e-6
            ):
                tampered = True
            checks.append(check)
        return self._result(run_id, checks, as_of, corpus_sha256=corpus_sha256, config_hash=config_hash), tampered

    def make_pass(self, result: GateResult) -> GatePass:
        if not result.passed:
            raise ValueError("게이트를 통과하지 않은 결과로 GatePass를 만들 수 없습니다.")
        public_ids = tuple(check.document_id for check in result.checks if check.public_countable)
        return _make_gate_pass(
            run_id=result.run_id,
            document_ids=public_ids,
            evidence_fingerprint=self.fingerprint(result.checks),
            config_hash=self.config_hash,
            corpus_sha256=self.corpus_sha256,
            as_of=result.as_of,
        )

    @staticmethod
    def fingerprint(checks: Iterable[EvidenceCheck]) -> str:
        payload = [
            {
                "document_id": check.document_id,
                "score": check.score,
                "coverage": check.coverage,
                "citation_valid": check.citation_valid,
                "invalid_reasons": list(check.invalid_reasons),
                "snapshot_sha256": sha256_text(canonical_json(check.snapshot)),
            }
            for check in sorted(checks, key=lambda item: item.document_id)
        ]
        return sha256_text(canonical_json(payload))

    # -- checks -------------------------------------------------------------

    @staticmethod
    def _load_snapshot(record: EvidenceRecord) -> dict[str, Any]:
        import json

        try:
            snapshot = json.loads(record.snapshot_json)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"저장된 evidence snapshot이 손상되었습니다: {record.document_id}") from exc
        if not isinstance(snapshot, dict):
            raise ValueError(f"저장된 evidence snapshot 형식이 잘못되었습니다: {record.document_id}")
        return snapshot

    @staticmethod
    def _document_from_snapshot(snapshot: dict[str, Any]) -> CorpusDocument:
        required = ("document_id", "title", "section", "source_url", "source_tier", "excerpt", "content")
        if any(key not in snapshot for key in required):
            raise ValueError("저장된 evidence snapshot에 필수 필드가 없습니다.")
        return CorpusDocument(
            document_id=str(snapshot["document_id"]),
            title=str(snapshot["title"]),
            section=str(snapshot["section"]),
            source_url=str(snapshot["source_url"]),
            source_tier=str(snapshot["source_tier"]),
            excerpt=str(snapshot["excerpt"]),
            content=str(snapshot["content"]),
            policy_key=snapshot.get("policy_key"),
            policy_scope=snapshot.get("policy_scope"),
            policy_value=snapshot.get("policy_value"),
            effective_from=snapshot.get("effective_from"),
            effective_to=snapshot.get("effective_to"),
            usage_basis=str(snapshot.get("usage_basis", "")),
            excerpt_type=str(snapshot.get("excerpt_type", "")),
        )

    def _check_document(
        self,
        document: CorpusDocument,
        hit: RetrievalHit,
        as_of: date,
        *,
        duplicate: bool = False,
    ) -> EvidenceCheck:
        reasons: list[str] = []
        details: list[str] = []

        url_check = self._validate_url(document.source_url, document.source_tier)
        if not url_check.ok:
            reasons.append(url_check.reason or "missing_source_url")
            if url_check.detail:
                details.append(url_check.detail)

        excerpt = normalize_text(document.excerpt)
        content = normalize_text(document.content)
        if len(excerpt) < self.settings.min_excerpt_chars:
            reasons.append("excerpt_too_short")
            details.append(f"발췌 {len(excerpt)}자 < 기준 {self.settings.min_excerpt_chars}자")
        if excerpt.endswith("...") or "…" in excerpt:
            reasons.append("excerpt_has_ellipsis")
        if excerpt not in content:
            reasons.append("excerpt_not_in_content")
        if hit.score < self.settings.min_citation_score:
            reasons.append("below_min_score")
            details.append(f"점수 {hit.score:.4f} < 기준 {self.settings.min_citation_score:.2f}")

        start = parse_date(document.effective_from)
        end = parse_date(document.effective_to)
        if start and as_of < start:
            reasons.append("not_yet_effective")
            details.append(f"시행일 {start.isoformat()} > 기준일 {as_of.isoformat()}")
        if end and as_of > end:
            reasons.append("superseded")
            details.append(f"유효기간 종료 {end.isoformat()} < 기준일 {as_of.isoformat()}")

        if document.source_tier not in {"public_summary", "synthetic_fixture"}:
            reasons.append("invalid_source_tier")
        if document.policy_key and (not document.policy_scope or not document.policy_value):
            reasons.append("invalid_policy_metadata")
        if duplicate:
            reasons.append("duplicate_document")

        valid = not reasons
        return EvidenceCheck(
            document_id=document.document_id,
            title=document.title,
            section=document.section,
            excerpt=document.excerpt,
            source_url=document.source_url,
            source_tier=document.source_tier,
            score=round(hit.score, 6),
            coverage=round(hit.coverage, 6),
            bm25=round(hit.bm25, 6),
            matched_terms=tuple(hit.matched_terms),
            citation_valid=valid,
            invalid_reason=reasons[0] if reasons else None,
            invalid_detail="; ".join(details) if details else None,
            invalid_reasons=tuple(reasons),
            policy_key=document.policy_key,
            policy_scope=document.policy_scope,
            policy_value=document.policy_value,
            effective_from=document.effective_from,
            effective_to=document.effective_to,
            snapshot=document.snapshot(),
        )

    def _validate_url(self, source_url: str, source_tier: str) -> _UrlCheck:
        if not source_url:
            return _UrlCheck(False, "missing_source_url", "source_url이 비어 있습니다.")
        try:
            parts = urlsplit(source_url)
        except ValueError:
            return _UrlCheck(False, "missing_source_url", "URL을 해석할 수 없습니다.")
        if parts.scheme.lower() != "https":
            return _UrlCheck(False, "url_not_https", "https 스킴이 아닙니다.")
        if parts.username or parts.password:
            return _UrlCheck(False, "url_has_credentials", "사용자 정보가 포함되어 있습니다.")
        host = (parts.hostname or "").lower()
        if not host:
            return _UrlCheck(False, "url_host_not_allowed", "호스트가 없습니다.")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return _UrlCheck(False, "url_ip_host", "IP 주소 호스트입니다.")
        if parts.port is not None and parts.port != 443:
            return _UrlCheck(False, "url_has_port", f"포트 {parts.port}")
        allowed = {item.lower() for item in self.settings.allowed_hosts}
        if host not in allowed:
            return _UrlCheck(False, "url_host_not_allowed", f"호스트 {host}")
        if source_tier == "public_summary" and host == "example.com":
            return _UrlCheck(False, "url_host_not_allowed", "공개 문서에 합성 fixture 호스트가 사용되었습니다.")
        if source_tier == "synthetic_fixture" and host != "example.com":
            return _UrlCheck(False, "url_host_not_allowed", "합성 fixture 호스트가 아닙니다.")
        return _UrlCheck(True, None, None)

    # -- result -------------------------------------------------------------

    def _result(
        self,
        run_id: str,
        checks: list[EvidenceCheck],
        as_of: date,
        *,
        corpus_sha256: str | None = None,
        config_hash: str | None = None,
    ) -> GateResult:
        conflicts = self._find_conflicts(checks, as_of)
        valid = [check for check in checks if check.citation_valid]
        public_valid = [check for check in valid if check.source_tier == "public_summary"]
        required = max(
            self.settings.min_valid_citations,
            self.settings.min_public_citations,
        )

        if not checks:
            category: str | None = "no_evidence"
        elif conflicts:
            category = "conflict"
        elif len(public_valid) >= required:
            category = None
        elif not any(check.score >= self.settings.min_citation_score for check in checks):
            category = "low_score"
        elif any(
            set(check.invalid_reasons)
            & {
                "missing_source_url",
                "url_not_https",
                "url_host_not_allowed",
                "url_has_credentials",
                "url_has_port",
                "url_ip_host",
                "excerpt_too_short",
                "excerpt_not_in_content",
                "excerpt_has_ellipsis",
                "not_yet_effective",
                "superseded",
                "invalid_source_tier",
                "invalid_policy_metadata",
            }
            for check in checks
        ):
            category = "invalid_citation"
        else:
            category = "too_few_citations"

        passed = category is None
        reasons: list[str] = []
        if category == "no_evidence":
            reasons.append("검색된 근거 후보가 없습니다.")
        if conflicts:
            for conflict in conflicts:
                reasons.append(conflict["message"])
        if len(public_valid) < required:
            reasons.append(
                f"공개 문서 유효 인용 {len(public_valid)}개 < 필요 {required}개입니다. "
                "(합성 fixture는 최소 인용 수에 포함하지 않습니다.)"
            )
        if category == "low_score":
            reasons.append(
                f"모든 후보의 검색 점수가 기준 {self.settings.min_citation_score:.2f} 미만입니다."
            )
        if category == "invalid_citation":
            invalid = [
                f"{check.document_id}: {REASON_LABELS.get(check.invalid_reason or '', check.invalid_reason)}"
                for check in checks
                if not check.citation_valid
            ]
            reasons.extend(invalid)

        return GateResult(
            run_id=run_id,
            passed=passed,
            category=category,
            reasons=tuple(reasons),
            checks=tuple(checks),
            valid_count=len(valid),
            public_valid_count=len(public_valid),
            required_count=required,
            conflicts=tuple(conflicts),
            config_hash=config_hash or self.config_hash,
            corpus_sha256=corpus_sha256 or self.corpus_sha256,
            as_of=as_of.isoformat(),
        )

    def _find_conflicts(self, checks: list[EvidenceCheck], as_of: date) -> list[dict[str, Any]]:
        # Conflict detection is corpus-wide for any policy key that this query
        # actually reached. This prevents a contradictory document from being
        # hidden merely because its retrieval score fell below the citation
        # threshold or outside top-k.
        keys = {
            (check.policy_key, check.policy_scope or "")
            for check in checks
            if check.policy_key and check.score >= self.settings.conflict_scan_floor
        }
        if not keys:
            return []

        conflicts: list[dict[str, Any]] = []
        for policy_key, scope in sorted(keys):
            candidates = [
                document
                for document in self._documents
                if document.policy_key == policy_key and (document.policy_scope or "") == scope
            ]
            if not candidates:
                # Fallback for a caller that supplied evidence snapshots without
                # the corpus (unit tests). Only structurally valid checks count.
                candidates = [
                    self._document_from_snapshot(check.snapshot)
                    for check in checks
                    if check.policy_key == policy_key
                    and (check.policy_scope or "") == scope
                    and check.citation_valid
                ]
            grouped: dict[str, list[Any]] = {}
            for document in candidates:
                if not self._structurally_valid(document, as_of):
                    continue
                if document.policy_value is None:
                    continue
                normalized = normalize_policy_value(document.policy_value)
                if normalized is None:
                    continue
                grouped.setdefault(normalized, []).append(document)

            if len(grouped) > 1:
                values = [
                    {
                        "document_id": document.document_id,
                        "value": document.policy_value,
                        "normalized": normalized,
                    }
                    for normalized, documents in grouped.items()
                    for document in documents
                ]
                conflicts.append(
                    {
                        "policy_key": policy_key,
                        "scope": scope,
                        "values": values,
                        "message": (
                            f"동일 정책 키 '{policy_key}'·범위 '{scope}'에서 "
                            f"서로 다른 값이 검색되었습니다: "
                            + ", ".join(
                                f"{item['value']}({item['document_id']})" for item in values
                            )
                        ),
                    }
                )
        return conflicts

    def _structurally_valid(self, document: CorpusDocument, as_of: date) -> bool:
        """Validity checks that do not depend on the retrieval score."""
        if not self._validate_url(document.source_url, document.source_tier).ok:
            return False
        excerpt = normalize_text(document.excerpt)
        content = normalize_text(document.content)
        if len(excerpt) < self.settings.min_excerpt_chars:
            return False
        if excerpt.endswith("...") or "…" in excerpt:
            return False
        if excerpt not in content:
            return False
        if document.source_tier not in {"public_summary", "synthetic_fixture"}:
            return False
        if document.policy_key and (not document.policy_scope or not document.policy_value):
            return False
        start = parse_date(document.effective_from)
        end = parse_date(document.effective_to)
        if start and as_of < start:
            return False
        if end and as_of > end:
            return False
        return True
