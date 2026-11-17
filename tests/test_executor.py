from __future__ import annotations

import pytest

from app.services.execution import ExecutionPolicyError, MockExecutor, SimulatedFailure


def plan(action: str = "create_demo_draft", mode: str = "none") -> dict:
    return {
        "goal": "테스트 요청",
        "allowed_action": action,
        "simulation": {"mode": mode, "max_attempts": 2},
    }


def test_draft_execution_is_deterministic() -> None:
    executor = MockExecutor()
    first = executor.run(plan(), run_id="run_x", attempt=1)
    second = executor.run(plan(), run_id="run_x", attempt=1)
    assert first == second
    assert first["simulated"] is True
    assert first["external_side_effects"] is False
    assert first["draft_id"].startswith("draft-")
    assert first["attempt"] == 1


def test_attempt_changes_result_id() -> None:
    executor = MockExecutor()
    first = executor.run(plan(), run_id="run_x", attempt=1)
    second = executor.run(plan(), run_id="run_x", attempt=2)
    assert first["draft_id"] != second["draft_id"]


def test_notification_execution() -> None:
    result = MockExecutor().run(plan(action="simulate_notification"), run_id="run_x", attempt=1)
    assert result["notification_id"].startswith("notif-")
    assert result["channel"] == "demo-console"


def test_disallowed_action_is_rejected() -> None:
    with pytest.raises(ExecutionPolicyError):
        MockExecutor().run(plan(action="delete_procurement_data"), run_id="run_x", attempt=1)


def test_fail_once_fails_first_attempt_then_succeeds() -> None:
    executor = MockExecutor()
    with pytest.raises(SimulatedFailure) as exc:
        executor.run(plan(mode="fail_once"), run_id="run_x", attempt=1)
    assert exc.value.reason == "SIMULATED_TRANSIENT_FAILURE"
    result = executor.run(plan(mode="fail_once"), run_id="run_x", attempt=2)
    assert result["attempt"] == 2


def test_fail_twice_fails_both_attempts() -> None:
    executor = MockExecutor()
    for attempt in (1, 2):
        with pytest.raises(SimulatedFailure) as exc:
            executor.run(plan(mode="fail_twice"), run_id="run_x", attempt=attempt)
        assert exc.value.reason == "SIMULATED_PERSISTENT_FAILURE"


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ExecutionPolicyError):
        MockExecutor().run(plan(mode="maybe"), run_id="run_x", attempt=1)
