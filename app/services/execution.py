from __future__ import annotations

from typing import Any

from app.services.planner import ALLOWED_ACTIONS
from app.textutil import canonical_json, sha256_text


class ExecutionPolicyError(ValueError):
    pass


class SimulatedFailure(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MockExecutor:
    """Deterministic, side-effect-free executor.

    There is no network, filesystem, mail, calendar, or procurement adapter in
    this project. The result payload is derived only from the approved plan.
    """

    def run(self, plan: dict[str, Any], *, run_id: str, attempt: int) -> dict[str, Any]:
        action = plan.get("allowed_action")
        if action not in ALLOWED_ACTIONS:
            raise ExecutionPolicyError(f"허용되지 않은 action입니다: {action}")

        simulation = plan.get("simulation") or {}
        mode = simulation.get("mode", "none")
        if mode == "fail_once" and attempt == 1:
            raise SimulatedFailure("SIMULATED_TRANSIENT_FAILURE")
        if mode == "fail_twice":
            raise SimulatedFailure("SIMULATED_PERSISTENT_FAILURE")
        if mode not in {"none", "fail_once", "fail_twice"}:
            raise ExecutionPolicyError(f"허용되지 않은 simulation mode입니다: {mode}")

        goal = str(plan.get("goal", ""))[:120]
        seed = sha256_text(canonical_json({"run_id": run_id, "plan": plan, "attempt": attempt}))[:12]
        if action == "create_demo_draft":
            result = {
                "action": action,
                "simulated": True,
                "external_side_effects": False,
                "attempt": attempt,
                "draft_id": f"draft-{seed}",
                "title": f"[모의 초안] {goal}",
                "preview": (
                    "검증된 근거 범위 안에서 작성된 데모 초안입니다. "
                    "실제 문서 시스템에 저장되지 않았습니다."
                ),
            }
        else:
            result = {
                "action": action,
                "simulated": True,
                "external_side_effects": False,
                "attempt": attempt,
                "notification_id": f"notif-{seed}",
                "channel": "demo-console",
                "preview": (
                    "검증된 근거 범위 안에서 생성된 데모 알림입니다. "
                    "실제 메일·메신저로 발송되지 않았습니다."
                ),
            }
        return result
