"""Read-only portfolio view over the checked-in fixed evaluation results.

This module intentionally does not inspect the runtime database or execute an
evaluation.  It turns the committed regression artifact into a small,
reproducible report for the public demo without presenting it as production
telemetry or LLM-quality measurement.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = ROOT / "evals" / "results.json"
ABLATION_PATH = ROOT / "docs" / "retrieval-ablation.md"
VERIFICATION_PATH = ROOT / "docs" / "verification.md"
REQUIRED_CASE_IDS = frozenset(f"EG-{index:02d}" for index in range(1, 15))

METRIC_SPECS = (
    {
        "id": "gate_negative_paths",
        "label": "근거 부족·인용 오류·상충 차단",
        "description": "해당 고정 음성 케이스에서 계획을 만들지 않는 계약",
        "case_ids": ("EG-02", "EG-04", "EG-05", "EG-06"),
    },
    {
        "id": "approval_and_tamper_blocks",
        "label": "승인 전·반려 후·변조 실행 차단",
        "description": "승인 전, 반려 후, 계획 hash 불일치 실행을 서버가 409으로 거절하는 계약",
        "case_ids": ("EG-07", "EG-12", "EG-14"),
    },
    {
        "id": "execution_reliability",
        "label": "재시도·멱등 실행 계약",
        "description": "재시도 성공, 종료 실패 기록, 같은 키 replay를 확인하는 계약",
        "case_ids": ("EG-09", "EG-10", "EG-11"),
    },
)

NEGATIVE_CASE_SPECS = (
    {
        "id": "EG-06",
        "invariant": "상충 근거에서는 계획·승인·실행 레코드를 만들지 않는다.",
        "evidence": "gate_category=conflict, plans=0, approvals=0, executions=0",
    },
    {
        "id": "EG-07",
        "invariant": "사람 승인 전 실행은 서버가 409으로 거절하고 실행 레코드를 만들지 않는다.",
        "evidence": "E_STATE_CONFLICT(409), executions=0, DENIED_EXECUTION 감사 이벤트",
    },
    {
        "id": "EG-09",
        "invariant": "최대 1회 재시도 뒤에도 실패하면 terminal FAILED와 감사 이력을 보존한다.",
        "evidence": "attempts=2, FAILED, RETRY_SCHEDULED·EXECUTION_FAILED 감사 이벤트",
    },
)


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "report_available": False,
        "reason": reason,
        "scope": "체크인된 고정 회귀 평가 결과를 읽는 포트폴리오 리포트입니다.",
    }


def _ablation_summary(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"^\| (?P<variant>[^|]+) \| (?P<recall>\d+\.\d+) \| (?P<mrr>\d+\.\d+) \|$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            rows.append({key: value.strip() for key, value in match.groupdict().items()})
    return rows


def _pytest_summary(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    match = re.search(r"(?P<passed>\d+) passed \(약 (?P<seconds>\d+)초\)", path.read_text(encoding="utf-8"))
    if not match:
        return None
    return {
        "passed": match.group("passed"),
        "duration": f"약 {match.group('seconds')}초",
        "command": 'python -m pytest -o addopts="" -p no:cacheprovider',
        "source": "docs/verification.md",
    }


def build_evaluation_report(
    results_path: Path = RESULTS_PATH,
    ablation_path: Path = ABLATION_PATH,
    verification_path: Path = VERIFICATION_PATH,
) -> dict[str, Any]:
    """Return a presentation-safe aggregation of a committed eval artifact."""
    if not results_path.exists():
        return _unavailable("results_missing")
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _unavailable("results_invalid")

    summary = payload.get("summary")
    cases = payload.get("cases")
    if not isinstance(summary, dict) or not isinstance(cases, list):
        return _unavailable("results_schema_invalid")

    by_id = {case.get("id"): case for case in cases if isinstance(case, dict) and case.get("id")}
    total = summary.get("total")
    passed = summary.get("passed")
    failed = summary.get("failed")
    if (
        not by_id
        or len(by_id) != len(cases)
        or set(by_id) != REQUIRED_CASE_IDS
        or not all(isinstance(value, int) for value in (total, passed, failed))
        or total != len(cases)
        or passed != sum(1 for case in cases if case.get("passed") is True)
        or failed != total - passed
        or summary.get("all_passed") != (failed == 0)
    ):
        return _unavailable("results_schema_invalid")

    metrics = []
    for spec in METRIC_SPECS:
        selected = [by_id[case_id] for case_id in spec["case_ids"] if case_id in by_id]
        metrics.append(
            {
                **spec,
                "passed": sum(1 for case in selected if case.get("passed") is True),
                "total": len(selected),
                "case_ids": list(spec["case_ids"]),
            }
        )

    negative_cases = []
    for spec in NEGATIVE_CASE_SPECS:
        case = by_id.get(spec["id"])
        if case is None:
            continue
        negative_cases.append(
            {
                **spec,
                "title": case.get("title", spec["id"]),
                "split": case.get("split", "unknown"),
                "passed": case.get("passed") is True,
                "failure": case.get("failure"),
            }
        )

    return {
        "report_available": True,
        "scope": "체크인된 14개 고정 회귀 평가의 안전·상태 전이 계약 결과입니다. 운영 텔레메트리·LLM 정확도·실제 업무 성과가 아닙니다.",
        "generated_at": payload.get("generated_at"),
        "app_version": payload.get("app_version"),
        "summary": {
            "total": summary.get("total"),
            "passed": summary.get("passed"),
            "failed": summary.get("failed"),
            "all_passed": summary.get("all_passed"),
        },
        "splits": payload.get("splits", {}),
        "pytest": _pytest_summary(verification_path),
        "reproducibility": {
            "corpus_sha256": payload.get("corpus_sha256"),
            "gate_config_hash": payload.get("gate_config_hash"),
            "cases_sha256": payload.get("cases_sha256"),
            "environment": payload.get("environment", {}),
        },
        "metrics": metrics,
        "negative_cases": negative_cases,
        "retrieval_ablation": _ablation_summary(ablation_path),
        "limitations": [
            "고정 소형 코퍼스와 결정론적 mock 실행을 사용합니다.",
            "demo-reviewer는 실제 인증된 사용자 계정이 아닙니다.",
            "Render Free SQLite 이력은 재시작 시 소실될 수 있으며, hash chain은 보존된 이력 안의 변조 탐지 보조입니다.",
        ],
    }
