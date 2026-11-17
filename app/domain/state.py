from __future__ import annotations

STATUSES: tuple[str, ...] = (
    "DRAFT",
    "RETRIEVING",
    "EVIDENCE_INSUFFICIENT",
    "PENDING_APPROVAL",
    "APPROVED",
    "EXECUTING",
    "EXECUTED",
    "FAILED",
    "RETRYING",
    "REJECTED",
)

TERMINAL_STATUSES = frozenset({"EVIDENCE_INSUFFICIENT", "EXECUTED", "REJECTED"})

# The single source of truth for allowed transitions. Every state change goes
# through WorkflowService._transition(), which calls assert_transition().
TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"RETRIEVING"}),
    "RETRIEVING": frozenset({"EVIDENCE_INSUFFICIENT", "PENDING_APPROVAL"}),
    "PENDING_APPROVAL": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"EXECUTING"}),
    "EXECUTING": frozenset({"EXECUTED", "FAILED"}),
    "FAILED": frozenset({"RETRYING"}),
    "RETRYING": frozenset({"EXECUTED", "FAILED"}),
    "EVIDENCE_INSUFFICIENT": frozenset(),
    "EXECUTED": frozenset(),
    "REJECTED": frozenset(),
}


class InvalidTransition(Exception):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"허용되지 않은 상태 전이입니다: {source} -> {target}")
        self.source = source
        self.target = target


def can_transition(source: str, target: str) -> bool:
    return target in TRANSITIONS.get(source, frozenset())


def assert_transition(source: str, target: str) -> None:
    if source not in TRANSITIONS:
        raise InvalidTransition(source, target)
    if not can_transition(source, target):
        raise InvalidTransition(source, target)


def is_terminal(status: str, attempts: int | None = None) -> bool:
    if status == "FAILED":
        # FAILED is transient after attempt 1 and terminal after the retry budget.
        return attempts is not None and attempts >= 2
    return status in TERMINAL_STATUSES


def status_label(status: str) -> str:
    return {
        "DRAFT": "초안",
        "RETRIEVING": "근거 검색 중",
        "EVIDENCE_INSUFFICIENT": "근거 부족",
        "PENDING_APPROVAL": "승인 대기",
        "APPROVED": "승인됨",
        "EXECUTING": "모의 실행 중",
        "EXECUTED": "모의 실행 완료",
        "FAILED": "실행 실패",
        "RETRYING": "재시도 중",
        "REJECTED": "반려됨",
    }.get(status, status)
