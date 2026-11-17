from __future__ import annotations

import json
from pathlib import Path

from evals.run_evals import CASES_PATH, RESULTS_JSON, run_all

ROOT = Path(__file__).resolve().parents[1]


def test_all_fixed_eval_cases_pass() -> None:
    report = run_all(write=False)
    assert report["summary"]["all_passed"] is True
    assert report["summary"]["total"] == 14
    assert report["summary"]["failed"] == 0
    assert report["splits"]["dev"]["passed"] == 8
    assert report["splits"]["holdout"]["passed"] == 6
    for case in report["cases"]:
        assert case["passed"], case
        assert case["checks"], case["id"]


def test_eval_cases_cover_required_scenarios() -> None:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    ids = [case["id"] for case in payload["cases"]]
    assert ids == [f"EG-{index:02d}" for index in range(1, 15)]
    titles = " ".join(case["title"] for case in payload["cases"])
    for keyword in ["충분", "부족", "빈 질의", "URL", "점수", "상충", "승인 전", "승인 뒤", "실패", "재시도", "idempotency", "변조", "중복 승인", "반려"]:
        assert keyword in titles, keyword


def test_committed_eval_results_match_latest_run() -> None:
    assert RESULTS_JSON.exists(), "evals/results.json이 없습니다. python -m evals.run_evals를 실행하세요."
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    assert payload["summary"]["all_passed"] is True
    assert payload["summary"]["total"] == 14
    assert len(payload["cases"]) == 14
    assert payload["corpus_sha256"]
    assert payload["gate_config_hash"]
    assert payload["cases_sha256"]


def test_committed_results_match_fresh_run() -> None:
    committed = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    fresh = run_all(write=False)
    for key in ["corpus_sha256", "gate_config_hash", "cases_sha256"]:
        assert committed[key] == fresh[key], key

    def normalize(report):
        return [
            (
                case["id"],
                case["split"],
                case["passed"],
                case["failure"],
                tuple((check["label"], check["ok"], check["actual"]) for check in case["checks"]),
            )
            for case in report["cases"]
        ]

    assert normalize(committed) == normalize(fresh)
