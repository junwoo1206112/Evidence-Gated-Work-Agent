from __future__ import annotations

import pytest

from app.domain.state import (
    STATUSES,
    TRANSITIONS,
    InvalidTransition,
    assert_transition,
    can_transition,
    is_terminal,
    status_label,
)


EXPECTED_TRANSITIONS = {
    "DRAFT": {"RETRIEVING"},
    "RETRIEVING": {"EVIDENCE_INSUFFICIENT", "PENDING_APPROVAL"},
    "EVIDENCE_INSUFFICIENT": set(),
    "PENDING_APPROVAL": {"APPROVED", "REJECTED"},
    "APPROVED": {"EXECUTING"},
    "EXECUTING": {"EXECUTED", "FAILED"},
    "EXECUTED": set(),
    "FAILED": {"RETRYING"},
    "RETRYING": {"EXECUTED", "FAILED"},
    "REJECTED": set(),
}


def test_transition_table_matches_explicit_matrix() -> None:
    actual = {source: set(targets) for source, targets in TRANSITIONS.items()}
    assert actual == EXPECTED_TRANSITIONS
    assert set(STATUSES) == set(EXPECTED_TRANSITIONS)
    for targets in EXPECTED_TRANSITIONS.values():
        assert targets <= set(STATUSES)


def test_allowed_transitions() -> None:
    allowed = [
        ("DRAFT", "RETRIEVING"),
        ("RETRIEVING", "PENDING_APPROVAL"),
        ("RETRIEVING", "EVIDENCE_INSUFFICIENT"),
        ("PENDING_APPROVAL", "APPROVED"),
        ("PENDING_APPROVAL", "REJECTED"),
        ("APPROVED", "EXECUTING"),
        ("EXECUTING", "EXECUTED"),
        ("EXECUTING", "FAILED"),
        ("FAILED", "RETRYING"),
        ("RETRYING", "EXECUTED"),
        ("RETRYING", "FAILED"),
    ]
    for source, target in allowed:
        assert can_transition(source, target), (source, target)
        assert_transition(source, target)


def test_forbidden_transitions() -> None:
    forbidden = [
        ("PENDING_APPROVAL", "EXECUTED"),
        ("APPROVED", "EXECUTED"),
        ("DRAFT", "PENDING_APPROVAL"),
        ("DRAFT", "EXECUTED"),
        ("EXECUTED", "RETRYING"),
        ("EVIDENCE_INSUFFICIENT", "PENDING_APPROVAL"),
        ("REJECTED", "APPROVED"),
        ("RETRYING", "APPROVED"),
    ]
    for source, target in forbidden:
        assert not can_transition(source, target), (source, target)
        with pytest.raises(InvalidTransition):
            assert_transition(source, target)


def test_terminal_statuses() -> None:
    assert is_terminal("EXECUTED")
    assert is_terminal("EVIDENCE_INSUFFICIENT")
    assert is_terminal("REJECTED")
    assert not is_terminal("FAILED")
    assert not is_terminal("FAILED", attempts=1)
    assert is_terminal("FAILED", attempts=2)
    assert not is_terminal("PENDING_APPROVAL")


def test_status_labels_are_korean() -> None:
    assert status_label("PENDING_APPROVAL") == "승인 대기"
    assert status_label("EXECUTED") == "모의 실행 완료"
