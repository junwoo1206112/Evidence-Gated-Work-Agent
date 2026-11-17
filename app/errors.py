from __future__ import annotations

from typing import Any


class AppError(Exception):
    """A public, typed application error.

    The message is safe to show to the browser. Internal exception details are
    logged by the API layer and never included in the response body.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 409,
        *,
        run_id: str | None = None,
        server_state: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.run_id = run_id
        self.server_state = server_state
        self.details = details or {}

    def to_body(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.run_id:
            error["run_id"] = self.run_id
        if self.server_state:
            error["server_state"] = self.server_state
        if self.details:
            error["details"] = self.details
        return {"error": error}


def not_found(run_id: str) -> AppError:
    return AppError(
        "E_NOT_FOUND",
        "해당 run을 찾을 수 없습니다.",
        404,
        run_id=run_id,
    )


def state_conflict(run_id: str, state: str, message: str) -> AppError:
    return AppError(
        "E_STATE_CONFLICT",
        message,
        409,
        run_id=run_id,
        server_state=state,
    )
