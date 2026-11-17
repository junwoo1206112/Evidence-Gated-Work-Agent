from __future__ import annotations

import unicodedata
from datetime import date

import pytest

from app.services.planner import ALLOWED_ACTIONS, compute_plan_hash, build_plan
from app.textutil import canonical_json
from tests.conftest import SUFFICIENT_REQUEST

AS_OF = date(2026, 11, 17)


@pytest.fixture
def gate_pass(service):
    result = service.gate.evaluate(
        "run_fixed_plan",
        service.retriever.search(SUFFICIENT_REQUEST, 5),
        AS_OF,
    )
    assert result.passed
    return service.gate.make_pass(result)


def test_plan_structure_is_restricted(gate_pass) -> None:
    payload, plan_hash = build_plan(SUFFICIENT_REQUEST, gate_pass, demo_mode="none")
    assert plan_hash == compute_plan_hash(payload)
    assert len(plan_hash) == 64
    assert payload["hash_scheme"] == "egwa-plan-v1"
    assert payload["allowed_action"] in ALLOWED_ACTIONS
    assert payload["risk_level"] == "medium"
    assert payload["required_evidence_ids"]
    assert payload["required_evidence_ids"] == list(gate_pass.document_ids[:3])
    assert len(payload["steps"]) == 3
    assert payload["simulation"]["external_side_effects"] is False
    assert payload["limits"]["network_calls"] is False
    assert payload["limits"]["real_procurement_execution"] is False
    assert payload["gate"]["evidence_fingerprint"] == gate_pass.evidence_fingerprint
    assert payload["gate"]["config_hash"] == gate_pass.config_hash
    assert payload["gate"]["corpus_sha256"] == gate_pass.corpus_sha256


def test_plan_has_no_timestamps(gate_pass) -> None:
    payload, _ = build_plan(SUFFICIENT_REQUEST, gate_pass)
    encoded = canonical_json(payload)
    assert "created_at" not in encoded
    assert "occurred_at" not in encoded
    assert "timestamp" not in encoded


def test_plan_hash_is_stable(gate_pass) -> None:
    first, hash_one = build_plan(SUFFICIENT_REQUEST, gate_pass)
    second, hash_two = build_plan(SUFFICIENT_REQUEST, gate_pass)
    assert canonical_json(first) == canonical_json(second)
    assert hash_one == hash_two


def test_plan_hash_normalizes_unicode(gate_pass) -> None:
    composed = {"x": "계약보증금", "n": 1}
    decomposed = {"x": unicodedata.normalize("NFD", "계약보증금"), "n": 1}
    assert canonical_json(composed) == canonical_json(decomposed)
    assert compute_plan_hash(composed) == compute_plan_hash(decomposed)


def test_plan_hash_changes_when_evidence_changes(gate_pass) -> None:
    payload, hash_one = build_plan(SUFFICIENT_REQUEST, gate_pass)
    changed = dict(payload)
    changed["gate"] = dict(payload["gate"])
    changed["gate"]["evidence_fingerprint"] = "0" * 64
    assert compute_plan_hash(changed) != hash_one


def test_notification_request_selects_notification_action(gate_pass) -> None:
    payload, _ = build_plan("지연배상금 기준을 확인해 담당자에게 알림을 준비해줘", gate_pass)
    assert payload["allowed_action"] == "simulate_notification"


def test_draft_request_selects_draft_action(gate_pass) -> None:
    payload, _ = build_plan("시설공사 계약보증금 기준을 확인해 초안을 작성해줘", gate_pass)
    assert payload["allowed_action"] == "create_demo_draft"


def test_invalid_demo_mode_rejected(gate_pass) -> None:
    with pytest.raises(ValueError):
        build_plan(SUFFICIENT_REQUEST, gate_pass, demo_mode="always")


def test_failure_mode_is_recorded(gate_pass) -> None:
    payload, _ = build_plan(SUFFICIENT_REQUEST, gate_pass, demo_mode="fail_once")
    assert payload["simulation"]["mode"] == "fail_once"
    assert payload["simulation"]["max_attempts"] == 2


def test_max_attempts_is_bounded(gate_pass) -> None:
    one, _ = build_plan(SUFFICIENT_REQUEST, gate_pass, max_attempts=1)
    many, _ = build_plan(SUFFICIENT_REQUEST, gate_pass, max_attempts=9)
    assert one["simulation"]["max_attempts"] == 1
    assert many["simulation"]["max_attempts"] == 2
