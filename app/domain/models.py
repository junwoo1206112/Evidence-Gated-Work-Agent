from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    user_request: str
    status: str
    created_at: str
    updated_at: str
    as_of: str
    demo_mode: str
    corpus_sha256: str
    config_hash: str
    gate_category: str | None
    gate_reason: str | None
    gate_json: str | None
    evidence_fingerprint: str | None


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: int
    run_id: str
    document_id: str
    title: str
    section: str
    excerpt: str
    source_url: str
    source_tier: str
    retrieval_score: float
    coverage: float
    bm25: float
    matched_terms: tuple[str, ...]
    citation_valid: bool
    invalid_reason: str | None
    invalid_detail: str | None
    policy_key: str | None
    policy_scope: str | None
    policy_value: str | None
    effective_from: str | None
    effective_to: str | None
    snapshot_json: str
    created_at: str


@dataclass(frozen=True)
class PlanRecord:
    run_id: str
    plan_version: str
    plan_json: str
    plan_hash: str
    evidence_fingerprint: str
    config_hash: str
    corpus_sha256: str
    created_at: str


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: int
    run_id: str
    approved_by: str
    decision: str
    plan_hash: str
    reason: str
    decided_at: str


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: int
    run_id: str
    idempotency_key: str
    attempt: int
    status: str
    result_json: str | None
    error_reason: str | None
    executed_at: str


@dataclass(frozen=True)
class AuditEventRecord:
    event_id: int
    run_id: str
    seq: int
    event_type: str
    payload_json: str
    occurred_at: str
    prev_hash: str
    event_hash: str


@dataclass(frozen=True)
class EvidenceCheck:
    document_id: str
    title: str
    section: str
    excerpt: str
    source_url: str
    source_tier: str
    score: float
    coverage: float
    bm25: float
    matched_terms: tuple[str, ...]
    citation_valid: bool
    invalid_reason: str | None
    invalid_detail: str | None
    invalid_reasons: tuple[str, ...]
    policy_key: str | None
    policy_scope: str | None
    policy_value: str | None
    effective_from: str | None
    effective_to: str | None
    snapshot: dict[str, Any]

    @property
    def public_countable(self) -> bool:
        return self.citation_valid and self.source_tier == "public_summary"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "section": self.section,
            "excerpt": self.excerpt,
            "source_url": self.source_url,
            "source_tier": self.source_tier,
            "score": self.score,
            "coverage": self.coverage,
            "bm25": self.bm25,
            "matched_terms": list(self.matched_terms),
            "citation_valid": self.citation_valid,
            "invalid_reason": self.invalid_reason,
            "invalid_detail": self.invalid_detail,
            "invalid_reasons": list(self.invalid_reasons),
            "policy_key": self.policy_key,
            "policy_scope": self.policy_scope,
            "policy_value": self.policy_value,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
        }


@dataclass(frozen=True)
class GateResult:
    run_id: str
    passed: bool
    category: str | None
    reasons: tuple[str, ...]
    checks: tuple[EvidenceCheck, ...]
    valid_count: int
    public_valid_count: int
    required_count: int
    conflicts: tuple[dict[str, Any], ...]
    config_hash: str
    corpus_sha256: str
    as_of: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "category": self.category,
            "reasons": list(self.reasons),
            "valid_count": self.valid_count,
            "public_valid_count": self.public_valid_count,
            "required_count": self.required_count,
            "conflicts": list(self.conflicts),
            "config_hash": self.config_hash,
            "corpus_sha256": self.corpus_sha256,
            "as_of": self.as_of,
            "checks": [check.to_public_dict() for check in self.checks],
        }


# A caller can only obtain a GatePass by passing through EvidenceGate.evaluate().
# The sentinel prevents accidentally constructing one in a route or test helper.
_GATE_SEAL = object()


@dataclass(frozen=True)
class GatePass:
    run_id: str
    document_ids: tuple[str, ...]
    evidence_fingerprint: str
    config_hash: str
    corpus_sha256: str
    as_of: str
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _GATE_SEAL:
            raise ValueError("GatePass는 EvidenceGate.evaluate()를 통해서만 생성할 수 있습니다.")


def _make_gate_pass(
    *,
    run_id: str,
    document_ids: tuple[str, ...],
    evidence_fingerprint: str,
    config_hash: str,
    corpus_sha256: str,
    as_of: str,
) -> GatePass:
    return GatePass(
        run_id=run_id,
        document_ids=document_ids,
        evidence_fingerprint=evidence_fingerprint,
        config_hash=config_hash,
        corpus_sha256=corpus_sha256,
        as_of=as_of,
        _seal=_GATE_SEAL,
    )


@dataclass(frozen=True)
class ExecutionOutcome:
    attempt: int
    status: str
    result: dict[str, Any] | None
    error_reason: str | None
