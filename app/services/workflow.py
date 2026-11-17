from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.db import Database
from app.domain.models import (
    ApprovalRecord,
    AuditEventRecord,
    EvidenceRecord,
    ExecutionOutcome,
    ExecutionRecord,
    GatePass,
    PlanRecord,
    RunRecord,
)
from app.domain.state import assert_transition, status_label
from app.errors import AppError, not_found, state_conflict
from app.services.audit import AuditLog
from app.services.corpus import Corpus
from app.services.evidence_gate import EvidenceGate
from app.services.execution import ExecutionPolicyError, MockExecutor, SimulatedFailure
from app.services.planner import DEMO_MODES, build_plan, compute_plan_hash
from app.services.retrieval import Retriever
from app.textutil import canonical_json, normalize_text
from app.version import APP_VERSION, DEMO_NOTICE

logger = logging.getLogger(__name__)

IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
SENSITIVE_PATTERNS = re.compile(
    r"ignore\s+(all|previous)|system\s+prompt|지시를\s*무시|비밀번호|주민등록번호|"
    r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b|"
    r"(?:^|\D)(?:01[016789])[-. ]?\d{3,4}[-. ]?\d{4}(?:$|\D)|"
    r"<script|javascript:|api[_\s-]?key",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExecuteResult:
    detail: dict[str, Any]
    replayed: bool


class WorkflowService:
    def __init__(self, settings: Settings, corpus: Corpus, db: Database) -> None:
        self.settings = settings
        self.corpus = corpus
        self.db = db
        self.retriever = Retriever(corpus)
        self.gate = EvidenceGate(settings, corpus.sha256, corpus.documents)
        self.executor = MockExecutor()
        self.audit = AuditLog(db)

    # -- request validation -------------------------------------------------

    def validate_request(self, value: str) -> str:
        request = normalize_text(value or "")
        if not request:
            raise AppError(
                "E_VALIDATION",
                "구체적인 업무 요청을 입력해주세요.",
                422,
            )
        if len(request) > self.settings.max_request_chars:
            raise AppError(
                "E_VALIDATION",
                f"요청은 {self.settings.max_request_chars}자 이하여야 합니다.",
                422,
            )
        if SENSITIVE_PATTERNS.search(request):
            raise AppError(
                "E_SENSITIVE_INPUT",
                "민감정보 또는 지시 우회 문구는 계획으로 처리하지 않습니다. 업무 목적만 다시 작성해주세요.",
                422,
            )
        return request

    # -- create -------------------------------------------------------------

    def create_run(self, request: str, demo_mode: str = "none") -> dict[str, Any]:
        request = self.validate_request(request)
        if demo_mode not in DEMO_MODES:
            raise AppError("E_VALIDATION", "지원하지 않는 demo_mode입니다.", 422)

        now = self.settings.now()
        now_iso = self._iso(now)
        as_of = now.date()
        run_id = f"run_{uuid.uuid4().hex}"
        hits = self.retriever.search(request, self.settings.top_k)
        gate_result = self.gate.evaluate(run_id, hits, as_of)
        fingerprint = self.gate.fingerprint(gate_result.checks)

        gate_pass: GatePass | None = None
        plan_payload: dict[str, Any] | None = None
        plan_hash: str | None = None
        if gate_result.passed:
            gate_pass = self.gate.make_pass(gate_result)
            plan_payload, plan_hash = build_plan(
                request,
                gate_pass,
                demo_mode=demo_mode,
                max_attempts=self.settings.max_attempts,
            )

        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, user_request, status, created_at, updated_at, as_of, demo_mode,
                    corpus_sha256, config_hash, gate_category, gate_reason, gate_json,
                    evidence_fingerprint
                ) VALUES (?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    request,
                    now_iso,
                    now_iso,
                    as_of.isoformat(),
                    demo_mode,
                    self.corpus.sha256,
                    self.gate.config_hash,
                    gate_result.category,
                    "; ".join(gate_result.reasons) if gate_result.reasons else None,
                    canonical_json(gate_result.to_public_dict()),
                    gate_pass.evidence_fingerprint if gate_pass else None,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "RUN_CREATED",
                {
                    "user_request": request,
                    "demo_mode": demo_mode,
                    "as_of": as_of.isoformat(),
                    "corpus_version": self.corpus.version,
                    "corpus_sha256": self.corpus.sha256,
                    "config_hash": self.gate.config_hash,
                },
                now_iso,
            )
            self._transition(connection, run_id, "DRAFT", "RETRIEVING", now_iso, reason="retrieval_started")
            self._append_event(
                connection,
                run_id,
                "EVIDENCE_RETRIEVED",
                {
                    "candidate_count": len(gate_result.checks),
                    "top_documents": [
                        {
                            "document_id": check.document_id,
                            "score": check.score,
                            "coverage": check.coverage,
                        }
                        for check in gate_result.checks[: self.settings.top_k]
                    ],
                },
                now_iso,
            )
            self._insert_evidence(connection, run_id, gate_result.checks, now_iso)
            self._append_event(
                connection,
                run_id,
                "EVIDENCE_GATE_PASSED" if gate_result.passed else "EVIDENCE_GATE_FAILED",
                {
                    "category": gate_result.category,
                    "reasons": list(gate_result.reasons),
                    "valid_count": gate_result.valid_count,
                    "public_valid_count": gate_result.public_valid_count,
                    "required_count": gate_result.required_count,
                    "conflicts": list(gate_result.conflicts),
                },
                now_iso,
            )
            if gate_result.passed and gate_pass and plan_payload and plan_hash:
                self._insert_plan(connection, run_id, plan_payload, plan_hash, gate_pass, now_iso)
                self._append_event(
                    connection,
                    run_id,
                    "PLAN_CREATED",
                    {
                        "plan_hash": plan_hash,
                        "allowed_action": plan_payload["allowed_action"],
                        "required_evidence_ids": plan_payload["required_evidence_ids"],
                        "risk_level": plan_payload["risk_level"],
                    },
                    now_iso,
                )
                self._transition(
                    connection,
                    run_id,
                    "RETRIEVING",
                    "PENDING_APPROVAL",
                    now_iso,
                    reason="evidence_gate_passed",
                )
            else:
                self._transition(
                    connection,
                    run_id,
                    "RETRIEVING",
                    "EVIDENCE_INSUFFICIENT",
                    now_iso,
                    reason=gate_result.category or "insufficient",
                )

        logger.info(
            "run created run_id=%s status=%s category=%s candidates=%s",
            run_id,
            "PENDING_APPROVAL" if gate_result.passed else "EVIDENCE_INSUFFICIENT",
            gate_result.category,
            len(gate_result.checks),
        )
        return self.get_run(run_id)

    # -- read ---------------------------------------------------------------

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.db.read() as connection:
            run_row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run_row is None:
                raise not_found(run_id)
            evidence_rows = connection.execute(
                "SELECT * FROM evidence WHERE run_id = ? ORDER BY retrieval_score DESC, document_id ASC",
                (run_id,),
            ).fetchall()
            plan_row = connection.execute("SELECT * FROM plans WHERE run_id = ?", (run_id,)).fetchone()
            approval_row = connection.execute(
                "SELECT * FROM approvals WHERE run_id = ?", (run_id,)
            ).fetchone()
            execution_rows = connection.execute(
                "SELECT * FROM executions WHERE run_id = ? ORDER BY attempt ASC", (run_id,)
            ).fetchall()
            audit_events = self.audit.list_with_connection(connection, run_id)

        run = self._row_to_run(run_row)
        evidence = [self._row_to_evidence(row) for row in evidence_rows]
        plan = self._row_to_plan(plan_row) if plan_row else None
        approval = self._row_to_approval(approval_row) if approval_row else None
        executions = [self._row_to_execution(row) for row in execution_rows]
        chain = self.audit.verify_chain_events(audit_events)
        integrity_warning = None
        gate_payload = self._safe_json(run.gate_json, None)
        plan_payload = None
        if gate_payload is None and run.gate_json:
            integrity_warning = "게이트 결과 JSON이 손상되어 표시할 수 없습니다."
        if plan is not None:
            plan_payload = self._safe_json(plan.plan_json, None)
            if plan_payload is None:
                integrity_warning = "계획 JSON이 손상되어 승인·실행을 차단했습니다."

        return {
            "app_version": APP_VERSION,
            "server_time": self._iso(self.settings.now()),
            "demo_notice": DEMO_NOTICE,
            "integrity_warning": integrity_warning,
            "run": {
                "run_id": run.run_id,
                "user_request": run.user_request,
                "status": run.status,
                "status_label": status_label(run.status),
                "created_at": run.created_at,
                "updated_at": run.updated_at,
                "as_of": run.as_of,
                "demo_mode": run.demo_mode,
                "corpus_sha256": run.corpus_sha256,
                "config_hash": run.config_hash,
                "gate_category": run.gate_category,
                "gate_reason": run.gate_reason,
                "evidence_fingerprint": run.evidence_fingerprint,
            },
            "corpus": {
                "version": self.corpus.version,
                "sha256": self.corpus.sha256,
                "documents": len(self.corpus.documents),
                "public_documents": len(self.corpus.public_documents),
            },
            "gate": gate_payload,
            "evidence": [self._evidence_dict(record) for record in evidence],
            "plan": (
                {
                    "plan": plan_payload,
                    "plan_hash": plan.plan_hash,
                    "plan_version": plan.plan_version,
                }
                if plan is not None and plan_payload is not None
                else None
            ),
            "approval": (
                {
                    "approved_by": approval.approved_by,
                    "decision": approval.decision,
                    "plan_hash": approval.plan_hash,
                    "reason": approval.reason,
                    "decided_at": approval.decided_at,
                }
                if approval
                else None
            ),
            "executions": [self._execution_dict(record) for record in executions],
            "audit": [self._audit_dict(record) for record in audit_events],
            "audit_chain": {
                "valid": chain.valid,
                "events": chain.events,
                "broken_at_seq": chain.broken_at_seq,
            },
            "capabilities": self._capabilities(run, plan, plan_payload, approval, executions),
        }

    def _capabilities(
        self,
        run: RunRecord,
        plan: PlanRecord | None,
        plan_payload: dict | None,
        approval: ApprovalRecord | None,
        executions: list[ExecutionRecord],
    ) -> dict[str, Any]:
        has_plan = plan is not None and plan_payload is not None
        can_approve = run.status == "PENDING_APPROVAL" and has_plan and approval is None
        can_execute = (
            run.status == "APPROVED"
            and has_plan
            and approval is not None
            and approval.decision == "approve"
        )
        can_replay = run.status in {"EXECUTED", "FAILED"}
        reason = {
            "EVIDENCE_INSUFFICIENT": "근거가 부족해 계획·승인·실행으로 진행할 수 없습니다.",
            "PENDING_APPROVAL": "사람 승인 후 모의 실행을 요청할 수 있습니다.",
            "APPROVED": "모의 실행을 시작할 수 있습니다.",
            "EXECUTING": "모의 실행이 진행 중입니다.",
            "RETRYING": "자동 재시도가 진행 중입니다.",
            "FAILED": "재시도 한도를 소진했습니다. 새 요청으로 다시 시작하세요.",
            "EXECUTED": "이미 실행되었습니다. 같은 idempotency key로만 재요청할 수 있습니다.",
            "REJECTED": "반려된 요청입니다.",
        }.get(run.status)
        if run.status == "PENDING_APPROVAL" and not can_approve:
            reason = "계획 또는 승인 기록이 없어 승인할 수 없습니다."
        return {
            "can_approve": can_approve,
            "can_reject": can_approve,
            "can_execute": can_execute,
            "can_replay": can_replay,
            "block_reason": None if (can_approve or can_execute or can_replay) else reason,
            "approval_block_reason": None if can_approve else reason,
            "execution_block_reason": None
            if (can_execute or (can_replay and run.status == "EXECUTED"))
            else reason,
            "has_plan": has_plan,
            "execution_attempts": len(executions),
        }

    # -- approval -----------------------------------------------------------

    def decide(self, run_id: str, decision: str, reason: str = "") -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise AppError("E_VALIDATION", "decision은 approve 또는 reject여야 합니다.", 422)
        now_iso = self._iso(self.settings.now())
        reason = normalize_text(reason)[:300]
        if reason and SENSITIVE_PATTERNS.search(reason):
            raise AppError(
                "E_SENSITIVE_INPUT",
                "승인/반려 사유에 민감정보를 저장할 수 없습니다.",
                422,
                run_id=run_id,
            )
        try:
            with self.db.transaction() as connection:
                run = self._load_run(connection, run_id)
                if run.status != "PENDING_APPROVAL":
                    raise state_conflict(
                        run_id,
                        run.status,
                        "승인 대기 상태에서만 승인 또는 반려할 수 있습니다.",
                    )
                plan = self._load_plan(connection, run_id)
                if plan is None:
                    raise AppError(
                        "E_STATE_CONFLICT",
                        "승인할 계획이 없습니다.",
                        409,
                        run_id=run_id,
                        server_state=run.status,
                    )
                existing = self._load_approval(connection, run_id)
                if existing is not None:
                    raise state_conflict(run_id, run.status, "이미 승인 또는 반려된 run입니다.")

                records = self._load_evidence(connection, run_id)
                self._revalidate_for_action(run, plan, records)

                self._insert_approval(
                    connection,
                    run_id=run_id,
                    decision=decision,
                    plan_hash=plan.plan_hash,
                    reason=reason or ("데모 검토자 승인" if decision == "approve" else "데모 검토자 반려"),
                    decided_at=now_iso,
                )
                target = "APPROVED" if decision == "approve" else "REJECTED"
                self._transition(
                    connection,
                    run_id,
                    "PENDING_APPROVAL",
                    target,
                    now_iso,
                    reason=f"reviewer_{decision}",
                )
                self._append_event(
                    connection,
                    run_id,
                    "APPROVAL_GRANTED" if decision == "approve" else "APPROVAL_REJECTED",
                    {
                        "approved_by": self.settings.demo_reviewer,
                        "decision": decision,
                        "plan_hash": plan.plan_hash,
                        "reason": reason or "",
                        "identity_note": "공개 데모의 고정 비개인 식별자이며 실제 신원 인증이 아닙니다.",
                    },
                    now_iso,
                )
        except AppError as exc:
            self._audit_denied(run_id, "APPROVAL", exc)
            raise

        return self.get_run(run_id)

    # -- execution ----------------------------------------------------------

    def execute(self, run_id: str, idempotency_key: str) -> ExecuteResult:
        key = (idempotency_key or "").strip()
        if not IDEMPOTENCY_PATTERN.fullmatch(key):
            raise AppError(
                "E_VALIDATION",
                "idempotency_key는 영문·숫자·._:- 조합 8~64자여야 합니다.",
                422,
                run_id=run_id,
            )

        plan_payload: dict[str, Any] | None = None
        now_iso = self._iso(self.settings.now())
        max_attempts = max(1, min(2, int(self.settings.max_attempts)))
        replay = False
        try:
            with self.db.transaction() as connection:
                run = self._load_run(connection, run_id)
                existing_rows = self._load_executions(connection, run_id)
                same_key = [row for row in existing_rows if row.idempotency_key == key]

                if run.status == "EXECUTED":
                    if same_key:
                        replay = True
                    else:
                        raise AppError(
                            "E_ALREADY_EXECUTED",
                            "이미 다른 idempotency key로 실행이 완료되었습니다.",
                            409,
                            run_id=run_id,
                            server_state=run.status,
                        )
                elif run.status == "FAILED" and same_key:
                    # Terminal failure is a cached outcome. Replaying the same
                    # key must return it instead of pretending a new attempt is
                    # allowed. A different key still gets E_RETRY_LIMIT.
                    replay = True
                elif run.status in {"EXECUTING", "RETRYING"}:
                    raise AppError(
                        "E_IN_PROGRESS",
                        "모의 실행이 진행 중입니다. 잠시 후 다시 확인해주세요.",
                        409,
                        run_id=run_id,
                        server_state=run.status,
                    )
                elif run.status == "FAILED":
                    raise AppError(
                        "E_RETRY_LIMIT",
                        "재시도 한도를 소진했습니다. 새 요청으로 다시 시작하세요.",
                        409,
                        run_id=run_id,
                        server_state=run.status,
                    )
                elif run.status != "APPROVED":
                    raise state_conflict(
                        run_id,
                        run.status,
                        "승인된 상태에서만 모의 실행을 요청할 수 있습니다.",
                    )

                if not replay:
                    if same_key:
                        raise AppError(
                            "E_IDEMPOTENCY_CONFLICT",
                            "이미 기록된 idempotency key와 실행 이력이 일치하지 않습니다.",
                            409,
                            run_id=run_id,
                            server_state=run.status,
                        )
                    if existing_rows:
                        raise AppError(
                            "E_ALREADY_EXECUTED",
                            "이 run에는 이미 실행 이력이 있습니다.",
                            409,
                            run_id=run_id,
                            server_state=run.status,
                        )
                    approval = self._load_approval(connection, run_id)
                    if approval is None or approval.decision != "approve":
                        raise state_conflict(run_id, run.status, "사람 승인 기록이 없습니다.")
                    plan = self._load_plan(connection, run_id)
                    if plan is None:
                        raise AppError(
                            "E_STATE_CONFLICT",
                            "실행할 계획이 없습니다.",
                            409,
                            run_id=run_id,
                            server_state=run.status,
                        )
                    plan_payload = json.loads(plan.plan_json)
                    if not isinstance(plan_payload, dict):
                        raise AppError(
                            "E_PLAN_HASH_MISMATCH",
                            "저장된 계획 형식이 올바르지 않습니다.",
                            409,
                            run_id=run_id,
                            server_state=run.status,
                        )
                    computed_hash = compute_plan_hash(plan_payload)
                    if computed_hash != plan.plan_hash or approval.plan_hash != plan.plan_hash:
                        raise AppError(
                            "E_PLAN_HASH_MISMATCH",
                            "계획 hash가 승인 시점과 일치하지 않습니다.",
                            409,
                            run_id=run_id,
                            server_state=run.status,
                            details={
                                "stored_plan_hash": plan.plan_hash,
                                "computed_plan_hash": computed_hash,
                                "approved_plan_hash": approval.plan_hash,
                            },
                        )
                    self._revalidate_for_action(
                        run,
                        plan,
                        self._load_evidence(connection, run_id),
                    )
                    self._transition(
                        connection,
                        run_id,
                        "APPROVED",
                        "EXECUTING",
                        now_iso,
                        reason="execution_started",
                    )
                    self._append_event(
                        connection,
                        run_id,
                        "EXECUTION_STARTED",
                        {
                            "idempotency_key": key,
                            "attempt": 1,
                            "allowed_action": plan_payload.get("allowed_action"),
                        },
                        now_iso,
                    )
        except AppError as exc:
            self._audit_denied(run_id, "EXECUTION", exc)
            raise

        if replay:
            return ExecuteResult(detail=self.get_run(run_id), replayed=True)

        assert plan_payload is not None
        first = self._attempt(plan_payload, run_id, attempt=1, idempotency_key=key)
        now_iso = self._iso(self.settings.now())
        with self.db.transaction() as connection:
            self._insert_execution(connection, run_id, key, first, now_iso)
            if first.status == "EXECUTED":
                self._transition(
                    connection,
                    run_id,
                    "EXECUTING",
                    "EXECUTED",
                    now_iso,
                    reason="execution_succeeded",
                )
                self._append_event(
                    connection,
                    run_id,
                    "EXECUTION_SUCCEEDED",
                    {
                        "idempotency_key": key,
                        "attempt": 1,
                        "result": first.result,
                    },
                    now_iso,
                )
            else:
                self._transition(
                    connection,
                    run_id,
                    "EXECUTING",
                    "FAILED",
                    now_iso,
                    reason="execution_failed",
                )
                self._append_event(
                    connection,
                    run_id,
                    "EXECUTION_FAILED",
                    {
                        "idempotency_key": key,
                        "attempt": 1,
                        "error_reason": first.error_reason,
                    },
                    now_iso,
                )
                if max_attempts >= 2:
                    self._transition(
                        connection,
                        run_id,
                        "FAILED",
                        "RETRYING",
                        now_iso,
                        reason="automatic_retry_policy",
                    )
                    self._append_event(
                        connection,
                        run_id,
                        "RETRY_SCHEDULED",
                        {
                            "idempotency_key": key,
                            "next_attempt": 2,
                            "max_attempts": max_attempts,
                        },
                        now_iso,
                    )

        if first.status == "EXECUTED":
            return ExecuteResult(detail=self.get_run(run_id), replayed=False)
        if max_attempts < 2:
            return ExecuteResult(detail=self.get_run(run_id), replayed=False)

        second = self._attempt(plan_payload, run_id, attempt=2, idempotency_key=key)
        now_iso = self._iso(self.settings.now())
        with self.db.transaction() as connection:
            self._insert_execution(connection, run_id, key, second, now_iso)
            target = "EXECUTED" if second.status == "EXECUTED" else "FAILED"
            self._transition(
                connection,
                run_id,
                "RETRYING",
                target,
                now_iso,
                reason="retry_execution_succeeded" if target == "EXECUTED" else "retry_exhausted",
            )
            self._append_event(
                connection,
                run_id,
                "EXECUTION_SUCCEEDED" if target == "EXECUTED" else "EXECUTION_FAILED",
                {
                    "idempotency_key": key,
                    "attempt": 2,
                    "error_reason": second.error_reason,
                    "result": second.result,
                },
                now_iso,
            )
        return ExecuteResult(detail=self.get_run(run_id), replayed=False)

    def _attempt(
        self,
        plan_payload: dict[str, Any],
        run_id: str,
        *,
        attempt: int,
        idempotency_key: str,
    ) -> ExecutionOutcome:
        try:
            result = self.executor.run(plan_payload, run_id=run_id, attempt=attempt)
            return ExecutionOutcome(attempt=attempt, status="EXECUTED", result=result, error_reason=None)
        except SimulatedFailure as exc:
            return ExecutionOutcome(attempt=attempt, status="FAILED", result=None, error_reason=exc.reason)
        except ExecutionPolicyError as exc:
            return ExecutionOutcome(
                attempt=attempt,
                status="FAILED",
                result=None,
                error_reason=f"POLICY_ERROR: {exc}",
            )
        except Exception:
            logger.exception(
                "unexpected executor error run_id=%s attempt=%s key=%s",
                run_id,
                attempt,
                idempotency_key,
            )
            return ExecutionOutcome(
                attempt=attempt,
                status="FAILED",
                result=None,
                error_reason="EXECUTOR_ERROR",
            )

    # -- revalidation -------------------------------------------------------

    def _revalidate_for_action(
        self,
        run: RunRecord,
        plan: PlanRecord,
        records: list[EvidenceRecord],
    ) -> None:
        if run.config_hash != self.gate.config_hash:
            raise AppError(
                "E_CONFIG_CHANGED",
                "게이트 설정이 승인 당시와 달라졌습니다. 새 요청으로 다시 시작하세요.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        if run.corpus_sha256 != self.corpus.sha256:
            raise AppError(
                "E_CORPUS_CHANGED",
                "코퍼스가 생성 당시와 달라졌습니다. 새 요청으로 다시 시작하세요.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        events = self.audit.list(run.run_id)
        chain = self.audit.verify_chain_events(events)
        if not chain.valid:
            raise AppError(
                "E_AUDIT_CHAIN_INVALID",
                "감사 hash chain이 손상되어 승인·실행을 진행할 수 없습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        plan_event = next((event for event in events if event.event_type == "PLAN_CREATED"), None)
        if plan_event is None:
            raise AppError(
                "E_PLAN_HASH_MISMATCH",
                "계획 생성 감사 이벤트가 없습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        anchored_hash = AuditLog.payload(plan_event).get("plan_hash")
        if anchored_hash != plan.plan_hash:
            raise AppError(
                "E_PLAN_HASH_MISMATCH",
                "계획 hash가 생성 시점의 감사 기록과 일치하지 않습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
                details={"anchored_plan_hash": anchored_hash, "stored_plan_hash": plan.plan_hash},
            )
        plan_payload = json.loads(plan.plan_json)
        if not isinstance(plan_payload, dict):
            raise AppError(
                "E_PLAN_HASH_MISMATCH",
                "저장된 계획 형식이 올바르지 않습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        if compute_plan_hash(plan_payload) != plan.plan_hash:
            raise AppError(
                "E_PLAN_HASH_MISMATCH",
                "저장된 계획이 변조되었거나 손상되었습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        if plan_payload.get("run_id") != run.run_id:
            raise AppError(
                "E_PLAN_HASH_MISMATCH",
                "계획의 run_id가 현재 run과 일치하지 않습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        try:
            result, stored_tampered = self.gate.revalidate(
                run.run_id,
                records,
                date.fromisoformat(run.as_of),
                corpus_sha256=self.corpus.sha256,
                config_hash=self.gate.config_hash,
            )
        except ValueError as exc:
            raise AppError(
                "E_EVIDENCE_STALE",
                "저장된 근거 스냅샷을 검증할 수 없습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
                details={"reason": str(exc)},
            ) from exc
        current_fingerprint = self.gate.fingerprint(result.checks)
        public_ids = {check.document_id for check in result.checks if check.public_countable}
        required_ids = set(plan_payload.get("required_evidence_ids") or [])
        if not required_ids or not required_ids.issubset(public_ids):
            raise AppError(
                "E_EVIDENCE_STALE",
                "계획이 참조하는 근거가 현재 유효한 공개 인용과 일치하지 않습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        if result.config_hash != run.config_hash or result.corpus_sha256 != run.corpus_sha256:
            raise AppError(
                "E_EVIDENCE_STALE",
                "근거 검증에 사용한 설정 또는 코퍼스가 달라졌습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )
        if (
            stored_tampered
            or not result.passed
            or current_fingerprint != run.evidence_fingerprint
            or current_fingerprint != plan.evidence_fingerprint
        ):
            raise AppError(
                "E_EVIDENCE_STALE",
                "저장된 근거가 생성 당시의 게이트 판정과 일치하지 않습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
                details={
                    "gate_category": result.category,
                    "reasons": list(result.reasons),
                    "fingerprint_match": current_fingerprint == run.evidence_fingerprint,
                },
            )
        gate_block = plan_payload.get("gate", {})
        if (
            gate_block.get("config_hash") != run.config_hash
            or gate_block.get("corpus_sha256") != run.corpus_sha256
            or gate_block.get("evidence_fingerprint") != run.evidence_fingerprint
        ):
            raise AppError(
                "E_EVIDENCE_STALE",
                "계획에 기록된 근거 지문이 실행 시점과 일치하지 않습니다.",
                409,
                run_id=run.run_id,
                server_state=run.status,
            )

    # -- recovery -----------------------------------------------------------

    def reconcile_stale_runs(self, older_than_seconds: int = 300) -> int:
        cutoff = self.settings.now() - timedelta(seconds=older_than_seconds)
        cutoff_iso = self._iso(cutoff)
        with self.db.read() as connection:
            rows = connection.execute(
                "SELECT run_id FROM runs WHERE status IN ('EXECUTING','RETRYING') AND updated_at < ?",
                (cutoff_iso,),
            ).fetchall()
        reconciled = 0
        for row in rows:
            run_id = str(row["run_id"])
            now_iso = self._iso(self.settings.now())
            try:
                with self.db.transaction() as connection:
                    run = self._load_run(connection, run_id)
                    if run.status not in {"EXECUTING", "RETRYING"}:
                        continue
                    self._transition(
                        connection,
                        run_id,
                        run.status,
                        "FAILED",
                        now_iso,
                        reason="interrupted_execution_reconciled",
                    )
                    self._append_event(
                        connection,
                        run_id,
                        "RECONCILED_INTERRUPTED",
                        {
                            "previous_status": run.status,
                            "error_reason": "INTERRUPTED_EXECUTION",
                            "policy": "프로세스가 실행 중 종료되어 실패로 종결했습니다.",
                        },
                        now_iso,
                    )
                    reconciled += 1
            except Exception:
                logger.exception("failed to reconcile run_id=%s", run_id)
        return reconciled

    # -- SQL helpers --------------------------------------------------------

    @staticmethod
    def _iso(value) -> str:
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _safe_json(value: str | None, default):
        if value is None:
            return default
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default

    def _append_event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        payload: dict,
        occurred_at: str,
    ) -> AuditEventRecord:
        return self.audit.append(
            connection,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
        )

    def _transition(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        source: str,
        target: str,
        occurred_at: str,
        *,
        reason: str,
    ) -> None:
        assert_transition(source, target)
        cursor = connection.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ? AND status = ?",
            (target, occurred_at, run_id, source),
        )
        if cursor.rowcount != 1:
            row = connection.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            current = str(row["status"]) if row else "MISSING"
            raise state_conflict(run_id, current, "동시 상태 변경이 감지되었습니다. 다시 시도해주세요.")
        self._append_event(
            connection,
            run_id,
            "STATE_TRANSITION",
            {"from": source, "to": target, "reason": reason},
            occurred_at,
        )

    def _insert_evidence(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        checks,
        created_at: str,
    ) -> None:
        for check in checks:
            connection.execute(
                """
                INSERT INTO evidence (
                    run_id, document_id, title, section, excerpt, source_url, source_tier,
                    retrieval_score, coverage, bm25, matched_terms_json, citation_valid,
                    invalid_reason, invalid_detail, policy_key, policy_scope, policy_value,
                    effective_from, effective_to, snapshot_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    check.document_id,
                    check.title,
                    check.section,
                    check.excerpt,
                    check.source_url,
                    check.source_tier,
                    check.score,
                    check.coverage,
                    check.bm25,
                    canonical_json(list(check.matched_terms)),
                    1 if check.citation_valid else 0,
                    check.invalid_reason,
                    check.invalid_detail,
                    check.policy_key,
                    check.policy_scope,
                    check.policy_value,
                    check.effective_from,
                    check.effective_to,
                    canonical_json(check.snapshot),
                    created_at,
                ),
            )

    def _insert_plan(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        payload: dict[str, Any],
        plan_hash: str,
        gate_pass: GatePass,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO plans (
                run_id, plan_version, plan_json, plan_hash, evidence_fingerprint,
                config_hash, corpus_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                str(payload["plan_version"]),
                canonical_json(payload),
                plan_hash,
                gate_pass.evidence_fingerprint,
                gate_pass.config_hash,
                gate_pass.corpus_sha256,
                created_at,
            ),
        )

    def _insert_approval(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        decision: str,
        plan_hash: str,
        reason: str,
        decided_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO approvals (run_id, approved_by, decision, plan_hash, reason, decided_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, self.settings.demo_reviewer, decision, plan_hash, reason, decided_at),
        )

    def _insert_execution(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        key: str,
        outcome: ExecutionOutcome,
        executed_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO executions (
                run_id, idempotency_key, attempt, status, result_json, error_reason, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                key,
                outcome.attempt,
                outcome.status,
                canonical_json(outcome.result) if outcome.result is not None else None,
                outcome.error_reason,
                executed_at,
            ),
        )

    def _load_run(self, connection: sqlite3.Connection, run_id: str) -> RunRecord:
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise not_found(run_id)
        return self._row_to_run(row)

    def _load_plan(self, connection: sqlite3.Connection, run_id: str) -> PlanRecord | None:
        row = connection.execute("SELECT * FROM plans WHERE run_id = ?", (run_id,)).fetchone()
        return self._row_to_plan(row) if row else None

    def _load_approval(self, connection: sqlite3.Connection, run_id: str) -> ApprovalRecord | None:
        row = connection.execute("SELECT * FROM approvals WHERE run_id = ?", (run_id,)).fetchone()
        return self._row_to_approval(row) if row else None

    def _load_evidence(self, connection: sqlite3.Connection, run_id: str) -> list[EvidenceRecord]:
        rows = connection.execute(
            "SELECT * FROM evidence WHERE run_id = ? ORDER BY retrieval_score DESC, document_id ASC",
            (run_id,),
        ).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def _load_executions(self, connection: sqlite3.Connection, run_id: str) -> list[ExecutionRecord]:
        rows = connection.execute(
            "SELECT * FROM executions WHERE run_id = ? ORDER BY attempt ASC",
            (run_id,),
        ).fetchall()
        return [self._row_to_execution(row) for row in rows]

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=str(row["run_id"]),
            user_request=str(row["user_request"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            as_of=str(row["as_of"]),
            demo_mode=str(row["demo_mode"]),
            corpus_sha256=str(row["corpus_sha256"]),
            config_hash=str(row["config_hash"]),
            gate_category=row["gate_category"],
            gate_reason=row["gate_reason"],
            gate_json=row["gate_json"],
            evidence_fingerprint=row["evidence_fingerprint"],
        )

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=int(row["evidence_id"]),
            run_id=str(row["run_id"]),
            document_id=str(row["document_id"]),
            title=str(row["title"]),
            section=str(row["section"]),
            excerpt=str(row["excerpt"]),
            source_url=str(row["source_url"]),
            source_tier=str(row["source_tier"]),
            retrieval_score=float(row["retrieval_score"]),
            coverage=float(row["coverage"]),
            bm25=float(row["bm25"]),
            matched_terms=tuple(WorkflowService._safe_json(row["matched_terms_json"], []) or []),
            citation_valid=bool(row["citation_valid"]),
            invalid_reason=row["invalid_reason"],
            invalid_detail=row["invalid_detail"],
            policy_key=row["policy_key"],
            policy_scope=row["policy_scope"],
            policy_value=row["policy_value"],
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
            snapshot_json=str(row["snapshot_json"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> PlanRecord:
        return PlanRecord(
            run_id=str(row["run_id"]),
            plan_version=str(row["plan_version"]),
            plan_json=str(row["plan_json"]),
            plan_hash=str(row["plan_hash"]),
            evidence_fingerprint=str(row["evidence_fingerprint"]),
            config_hash=str(row["config_hash"]),
            corpus_sha256=str(row["corpus_sha256"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _row_to_approval(row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=int(row["approval_id"]),
            run_id=str(row["run_id"]),
            approved_by=str(row["approved_by"]),
            decision=str(row["decision"]),
            plan_hash=str(row["plan_hash"]),
            reason=str(row["reason"]),
            decided_at=str(row["decided_at"]),
        )

    @staticmethod
    def _row_to_execution(row: sqlite3.Row) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=int(row["execution_id"]),
            run_id=str(row["run_id"]),
            idempotency_key=str(row["idempotency_key"]),
            attempt=int(row["attempt"]),
            status=str(row["status"]),
            result_json=row["result_json"],
            error_reason=row["error_reason"],
            executed_at=str(row["executed_at"]),
        )

    @staticmethod
    def _evidence_dict(record: EvidenceRecord) -> dict[str, Any]:
        return {
            "evidence_id": record.evidence_id,
            "document_id": record.document_id,
            "title": record.title,
            "section": record.section,
            "excerpt": record.excerpt,
            "source_url": record.source_url,
            "source_tier": record.source_tier,
            "retrieval_score": record.retrieval_score,
            "coverage": record.coverage,
            "bm25": record.bm25,
            "matched_terms": list(record.matched_terms),
            "citation_valid": record.citation_valid,
            "invalid_reason": record.invalid_reason,
            "invalid_detail": record.invalid_detail,
            "policy_key": record.policy_key,
            "policy_scope": record.policy_scope,
            "policy_value": record.policy_value,
            "effective_from": record.effective_from,
            "effective_to": record.effective_to,
        }

    @staticmethod
    def _execution_dict(record: ExecutionRecord) -> dict[str, Any]:
        return {
            "execution_id": record.execution_id,
            "idempotency_key": record.idempotency_key,
            "attempt": record.attempt,
            "status": record.status,
            "result": WorkflowService._safe_json(record.result_json, None),
            "error_reason": record.error_reason,
            "executed_at": record.executed_at,
        }

    @staticmethod
    def _audit_dict(record: AuditEventRecord) -> dict[str, Any]:
        return {
            "seq": record.seq,
            "event_type": record.event_type,
            "payload": AuditLog.payload(record),
            "occurred_at": record.occurred_at,
            "prev_hash": record.prev_hash,
            "event_hash": record.event_hash,
        }

    def _audit_denied(self, run_id: str, action: str, exc: AppError) -> None:
        if exc.code == "E_NOT_FOUND":
            return
        try:
            self.audit.record_denied(
                run_id=run_id,
                action=action,
                code=exc.code,
                server_state=exc.server_state or "UNKNOWN",
                details=exc.details,
                occurred_at=self._iso(self.settings.now()),
            )
        except Exception:
            logger.exception("failed to record denied %s event run_id=%s", action, run_id)
