from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=500)
    demo_mode: Literal["none", "fail_once", "fail_twice"] = "none"


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=300)


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=64)
