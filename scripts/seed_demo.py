"""Seed a few demo runs in the local SQLite database.

Usage:
    python scripts/seed_demo.py
Then open the printed URLs while the server is running.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import create_app

SCENARIOS = [
    (
        "충분 근거",
        "시설공사 계약보증금과 지연배상금 기준을 확인해 초안을 작성해줘",
        "none",
    ),
    (
        "부족 근거",
        "우주발사체 발사보험 면책 특약과 발사허가 절차를 정리해줘",
        "none",
    ),
    (
        "상충 근거",
        "물품 계약보증금 비율 기준을 확인해줘",
        "none",
    ),
    (
        "실패→재시도",
        "시설공사 지연배상금 산정 기준과 계약업무 처리 절차를 확인해 알림을 준비해줘",
        "fail_once",
    ),
]


def main() -> int:
    app = create_app()
    service = app.state.service
    base = "http://127.0.0.1:8000"
    print(f"database: {app.state.settings.db_path}")
    for label, request, mode in SCENARIOS:
        detail = service.create_run(request, mode)
        run_id = detail["run"]["run_id"]
        print(f"[{label}] {detail['run']['status']} {base}/runs/{run_id}")
        if label == "충분 근거":
            service.decide(run_id, "approve", "시드 데모 승인")
            result = service.execute(run_id, "seed-demo-key-0001")
            print(f"  approved+executed: {result.detail['run']['status']} (replayed={result.replayed})")
    print("\n서버 실행: python -m uvicorn app.main:create_app --factory --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
