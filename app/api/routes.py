from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas import ApprovalRequest, CreateRunRequest, ExecutionRequest

router = APIRouter(prefix="/api", tags=["workflow"])


@router.post("/runs", status_code=201)
def create_run(payload: CreateRunRequest, request: Request) -> dict:
    service = request.app.state.service
    return service.create_run(payload.request, payload.demo_mode)


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    return request.app.state.service.get_run(run_id)


@router.post("/runs/{run_id}/approval")
def decide(run_id: str, payload: ApprovalRequest, request: Request) -> dict:
    return request.app.state.service.decide(run_id, payload.decision, payload.reason)


@router.post("/runs/{run_id}/executions")
def execute(run_id: str, payload: ExecutionRequest, request: Request) -> dict:
    result = request.app.state.service.execute(run_id, payload.idempotency_key)
    body = dict(result.detail)
    body["meta"] = {"replayed": result.replayed}
    return body
