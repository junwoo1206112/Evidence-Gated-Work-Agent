from __future__ import annotations

import re
from typing import Any

from app.domain.models import GatePass
from app.textutil import canonical_json, normalize_text, sha256_text

HASH_SCHEME = "egwa-plan-v1"
ALLOWED_ACTIONS = ("create_demo_draft", "simulate_notification")
DEMO_MODES = ("none", "fail_once", "fail_twice")

_NOTIFICATION = re.compile(r"알림|통보|공지|메일")
_DRAFT = re.compile(r"초안|작성|문서|공문|보고서")


def compute_plan_hash(payload: dict[str, Any]) -> str:
    return sha256_text(canonical_json(payload))


def build_plan(
    request: str,
    gate_pass: GatePass,
    *,
    demo_mode: str = "none",
    max_attempts: int = 2,
) -> tuple[dict[str, Any], str]:
    if not isinstance(gate_pass, GatePass):
        raise TypeError("planner.build_plan에는 EvidenceGate가 발급한 GatePass가 필요합니다.")
    if demo_mode not in DEMO_MODES:
        raise ValueError(f"지원하지 않는 demo_mode입니다: {demo_mode}")
    if len(gate_pass.document_ids) < 2:
        raise ValueError("계획 생성에는 공개 유효 인용 2개 이상이 필요합니다.")

    request_text = normalize_text(request)
    if _NOTIFICATION.search(request_text):
        action = "simulate_notification"
        summary = "검증된 근거를 대조하고 데모 알림을 준비합니다."
        final_step = "검증된 근거 범위 안에서 데모 알림 미리보기를 만든다."
    else:
        action = "create_demo_draft"
        summary = "검증된 근거를 대조하고 데모 초안을 준비합니다."
        final_step = "검증된 근거 범위 안에서 데모 초안 미리보기를 만든다."

    evidence_ids = list(gate_pass.document_ids[:3])
    attempts = max(1, min(2, int(max_attempts)))
    payload: dict[str, Any] = {
        "hash_scheme": HASH_SCHEME,
        "plan_version": "1.0",
        "run_id": gate_pass.run_id,
        "goal": request_text,
        "summary": summary,
        "risk_level": "medium",
        "allowed_action": action,
        "required_evidence_ids": evidence_ids,
        "steps": [
            {
                "step_id": "s1",
                "title": "요청 범위 확인",
                "description": "요청 문장과 승인 범위를 확인하고, 코퍼스 밖 실행을 요구하지 않는지 점검한다.",
                "uses_evidence_ids": [],
                "side_effect": "none",
            },
            {
                "step_id": "s2",
                "title": "근거 대조",
                "description": "인용된 공개 규정 요약과 계획 단계가 서로 일치하는지 대조한다.",
                "uses_evidence_ids": evidence_ids,
                "side_effect": "none",
            },
            {
                "step_id": "s3",
                "title": "모의 실행 준비",
                "description": final_step,
                "uses_evidence_ids": evidence_ids,
                "side_effect": "simulated_only",
            },
        ],
        "simulation": {
            "mode": demo_mode,
            "max_attempts": attempts,
            "external_side_effects": False,
        },
        "limits": {
            "external_side_effects": False,
            "allowed_actions": list(ALLOWED_ACTIONS),
            "network_calls": False,
            "real_procurement_execution": False,
        },
        "gate": {
            "config_hash": gate_pass.config_hash,
            "corpus_sha256": gate_pass.corpus_sha256,
            "evidence_fingerprint": gate_pass.evidence_fingerprint,
            "as_of": gate_pass.as_of,
        },
    }
    return payload, compute_plan_hash(payload)
