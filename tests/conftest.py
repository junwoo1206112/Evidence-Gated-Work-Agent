from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SUFFICIENT_REQUEST = "시설공사 계약보증금과 지연배상금 기준을 확인해 초안을 작성해줘"
INSUFFICIENT_REQUEST = "우주발사체 발사보험 면책 특약과 발사허가 절차를 정리해줘"
LOW_SCORE_REQUEST = "우주 발사체 보험 특약 면책 한도 규정"
CONFLICT_REQUEST = "물품 계약보증금 비율 기준을 확인해줘"
MISSING_URL_REQUEST = "무효 URL 테스트 조항"
RETRY_REQUEST = "시설공사 지연배상금 산정 기준과 계약업무 처리 절차를 확인해 알림을 준비해줘"
CORPUS_PATH = ROOT / "data" / "public_corpus" / "documents.json"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        corpus_path=CORPUS_PATH,
        rate_limit_per_minute=0,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def service(app):
    return app.state.service


def create_run(client: TestClient, request: str = SUFFICIENT_REQUEST, demo_mode: str = "none"):
    return client.post("/api/runs", json={"request": request, "demo_mode": demo_mode})


def approve(client: TestClient, run_id: str, decision: str = "approve", reason: str = "테스트 승인"):
    return client.post(
        f"/api/runs/{run_id}/approval",
        json={"decision": decision, "reason": reason},
    )


def execute(client: TestClient, run_id: str, key: str = "test-key-0001"):
    return client.post(f"/api/runs/{run_id}/executions", json={"idempotency_key": key})


def run_id_of(response) -> str:
    return response.json()["run"]["run_id"]
