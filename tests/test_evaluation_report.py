from __future__ import annotations

import json

from app.services.evaluation_report import build_evaluation_report


def test_evaluation_report_exposes_fixed_suite_scope() -> None:
    report = build_evaluation_report()

    assert report["report_available"] is True
    assert report["summary"] == {"total": 14, "passed": 14, "failed": 0, "all_passed": True}
    assert report["splits"]["dev"] == {"total": 8, "passed": 8}
    assert report["splits"]["holdout"] == {"total": 6, "passed": 6}
    assert [item["id"] for item in report["negative_cases"]] == ["EG-06", "EG-07", "EG-09"]
    assert all(item["passed"] for item in report["negative_cases"])
    assert "운영 텔레메트리" in report["scope"]


def test_evaluation_report_is_safe_when_results_are_missing(tmp_path) -> None:
    report = build_evaluation_report(tmp_path / "missing.json")
    assert report == {
        "report_available": False,
        "reason": "results_missing",
        "scope": "체크인된 고정 회귀 평가 결과를 읽는 포트폴리오 리포트입니다.",
    }


def test_evaluation_report_rejects_incomplete_or_inconsistent_results(tmp_path) -> None:
    payload = {
        "summary": {"total": 14, "passed": 14, "failed": 0, "all_passed": True},
        "cases": [{"id": "EG-06", "title": "상충", "split": "dev", "passed": True, "failure": None}],
    }
    result_path = tmp_path / "results.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    report = build_evaluation_report(result_path)
    assert report["report_available"] is False
    assert report["reason"] == "results_schema_invalid"


def test_evaluation_report_rejects_invalid_json(tmp_path) -> None:
    result_path = tmp_path / "results.json"
    result_path.write_text("not-json", encoding="utf-8")
    assert build_evaluation_report(result_path)["reason"] == "results_invalid"


def test_evaluation_report_api_and_page(client) -> None:
    api = client.get("/api/evaluation-report")
    assert api.status_code == 200
    assert api.json()["report_available"] is True
    assert api.json()["metrics"][0]["total"] == 4
    assert [item["id"] for item in api.json()["negative_cases"]] == ["EG-06", "EG-07", "EG-09"]

    page = client.get("/evaluation")
    assert page.status_code == 200
    assert "고정 회귀 평가 리포트" in page.text
    assert "대표 음성·실패 경로 3개" in page.text
    assert "전체 회귀 테스트" in page.text
