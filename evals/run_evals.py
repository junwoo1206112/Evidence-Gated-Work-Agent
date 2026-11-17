from __future__ import annotations

import json
import hashlib
import platform
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.textutil import canonical_json
from app.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
RESULTS_JSON = ROOT / "evals" / "results.json"
RESULTS_MD = ROOT / "evals" / "results.md"
FIXED_CLOCK = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_clock() -> datetime:
    return FIXED_CLOCK


def _error_code(response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except Exception:
        return None


def _status(data: dict | None) -> str | None:
    if not data or not isinstance(data, dict):
        return None
    run = data.get("run")
    return run.get("status") if isinstance(run, dict) else None


def _attempts(data: dict | None) -> list[dict]:
    if not data or not isinstance(data, dict):
        return []
    executions = data.get("executions")
    return executions if isinstance(executions, list) else []


def check_expectation(
    label: str,
    expected: Any,
    *,
    response=None,
    data: dict | None = None,
    rows: dict | None = None,
    run_count: int | None = None,
) -> dict:
    actual: Any = None
    ok = False

    if label == "http":
        actual = response.status_code if response is not None else None
        ok = actual == expected
    elif label == "code":
        actual = _error_code(response) if response is not None else None
        ok = actual == expected
    elif label == "status":
        actual = _status(data)
        ok = actual == expected
    elif label == "plan":
        actual = bool(data and data.get("plan"))
        ok = actual == bool(expected)
    elif label == "public_valid_min":
        actual = (data or {}).get("gate", {}).get("public_valid_count") if data else None
        ok = actual is not None and actual >= expected
    elif label == "gate_category":
        actual = ((data or {}).get("run") or {}).get("gate_category") if data else None
        ok = actual == expected
    elif label == "gate_reason_contains":
        run = ((data or {}).get("run") or {}) if data else {}
        gate = (data or {}).get("gate") or {}
        haystack = " ".join(
            [str(run.get("gate_reason") or "")] + [str(reason) for reason in gate.get("reasons", [])]
        )
        actual = haystack
        ok = expected in haystack
    elif label == "replayed":
        actual = ((data or {}).get("meta") or {}).get("replayed") if data else None
        ok = actual == expected
    elif label == "attempts":
        actual = len(_attempts(data))
        ok = actual == expected
    elif label == "first_attempt_status":
        executions = _attempts(data)
        actual = executions[0]["status"] if executions else None
        ok = actual == expected
    elif label == "last_attempt_status":
        executions = _attempts(data)
        actual = executions[-1]["status"] if executions else None
        ok = actual == expected
    elif label == "all_attempts_failed":
        executions = _attempts(data)
        actual = bool(executions) and all(item["status"] == "FAILED" for item in executions)
        ok = actual == expected
    elif label == "rows":
        actual = {key: (rows or {}).get(key) for key in expected}
        ok = all((rows or {}).get(key) == value for key, value in expected.items())
    elif label in {"plans", "approvals", "executions", "evidence", "audit_events"} and rows is not None:
        actual = rows.get(label)
        ok = actual == expected
    elif label == "audit_has":
        events = {item["event_type"] for item in (data or {}).get("audit", [])} if data else set()
        actual = sorted(events)
        ok = all(item in events for item in expected)
    elif label == "no_run":
        actual = run_count
        ok = (run_count == 0) == bool(expected)
    else:
        actual = "UNKNOWN_EXPECTATION"
        ok = False

    return {"label": label, "expected": expected, "actual": actual, "ok": ok}


def run_case(case: dict) -> dict:
    started = time.perf_counter()
    checks: list[dict] = []
    failure: str | None = None
    with tempfile.TemporaryDirectory(prefix=f"egwa-eval-{case['id'].lower()}-") as tmp:
        settings = Settings(
            db_path=Path(tmp) / "eval.db",
            corpus_path=ROOT / "data" / "public_corpus" / "documents.json",
            rate_limit_per_minute=0,
        ).with_clock(_fixed_clock)
        app = create_app(settings)
        try:
            with TestClient(app) as client:
                run_id: str | None = None
                for index, step in enumerate(case["steps"]):
                    op = step["op"]
                    response = None
                    data = None
                    rows = None
                    run_count = None
                    if op == "create":
                        response = client.post(
                            "/api/runs",
                            json={
                                "request": step["request"],
                                "demo_mode": step.get("demo_mode", "none"),
                            },
                        )
                        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
                        if response.status_code == 201 and data:
                            run_id = data["run"]["run_id"]
                    elif op in {"approve", "reject"}:
                        if not run_id:
                            raise AssertionError("approve/reject 전에 create가 필요합니다.")
                        payload = {
                            "decision": "approve" if op == "approve" else "reject",
                            "reason": step.get("reason", "평가 시나리오"),
                        }
                        response = client.post(f"/api/runs/{run_id}/approval", json=payload)
                        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
                    elif op == "execute":
                        if not run_id:
                            raise AssertionError("execute 전에 create가 필요합니다.")
                        key = step.get("key", "eval-execute-key-0001")
                        response = client.post(
                            f"/api/runs/{run_id}/executions",
                            json={"idempotency_key": key},
                        )
                        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
                    elif op == "tamper_plan":
                        if not run_id:
                            raise AssertionError("tamper_plan 전에 create가 필요합니다.")
                        with app.state.db.transaction() as connection:
                            row = connection.execute(
                                "SELECT plan_json FROM plans WHERE run_id = ?", (run_id,)
                            ).fetchone()
                            if row is None:
                                raise AssertionError("변조할 계획이 없습니다.")
                            payload = json.loads(row["plan_json"])
                            payload["tampered_by_eval"] = True
                            connection.execute(
                                "UPDATE plans SET plan_json = ? WHERE run_id = ?",
                                (canonical_json(payload), run_id),
                            )
                    elif op == "rows":
                        if not run_id:
                            raise AssertionError("rows 전에 create가 필요합니다.")
                        rows = app.state.db.count_rows(run_id)
                    elif op == "detail":
                        if not run_id:
                            raise AssertionError("detail 전에 create가 필요합니다.")
                        response = client.get(f"/api/runs/{run_id}")
                        data = response.json()
                    else:
                        raise AssertionError(f"알 수 없는 op입니다: {op}")

                    if step.get("expect", {}).get("no_run"):
                        with app.state.db.read() as connection:
                            run_count = int(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
                    for label, expected in step.get("expect", {}).items():
                        if label == "no_run":
                            checks.append(
                                check_expectation(
                                    label,
                                    expected,
                                    response=response,
                                    data=data,
                                    rows=rows,
                                    run_count=run_count,
                                )
                            )
                            continue
                        checks.append(
                            check_expectation(
                                label,
                                expected,
                                response=response,
                                data=data,
                                rows=rows,
                            )
                        )
        except Exception as exc:  # noqa: BLE001 - eval runner must report the failure
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                app.state.db.health()
            except Exception:
                pass

    passed = failure is None and all(item["ok"] for item in checks)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "id": case["id"],
        "title": case["title"],
        "split": case.get("split", "dev"),
        "passed": passed,
        "duration_ms": duration_ms,
        "checks": checks,
        "failure": failure,
    }


def run_all(write: bool = False) -> dict:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    started = time.perf_counter()
    results = [run_case(case) for case in cases]
    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    settings = Settings(
        db_path=Path(tempfile.gettempdir()) / "egwa-eval-config.db",
        corpus_path=ROOT / "data" / "public_corpus" / "documents.json",
        rate_limit_per_minute=0,
    )
    corpus_app = create_app(settings)
    corpus_sha256 = corpus_app.state.corpus.sha256
    config_hash = corpus_app.state.settings.gate_config_hash()

    passed = sum(1 for result in results if result["passed"])
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "all_passed": passed == len(results),
    }
    splits = {}
    for split in sorted({result["split"] for result in results}):
        subset = [result for result in results if result["split"] == split]
        splits[split] = {
            "total": len(subset),
            "passed": sum(1 for result in subset if result["passed"]),
        }

    report = {
        "schema_version": "1.0",
        "app_version": APP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_ms": duration_ms,
        "corpus_sha256": corpus_sha256,
        "gate_config_hash": config_hash,
        "cases_sha256": hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "summary": summary,
        "splits": splits,
        "cases": results,
    }
    if write:
        RESULTS_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        RESULTS_MD.write_text(_to_markdown(report), encoding="utf-8")
    return report


def _to_markdown(report: dict) -> str:
    lines = [
        "# 고정 평가 결과",
        "",
        f"- 앱 버전: `{report['app_version']}`",
        f"- 코퍼스 SHA-256: `{report['corpus_sha256']}`",
        f"- 게이트 설정 hash: `{report['gate_config_hash']}`",
        f"- 케이스 파일 SHA-256: `{report['cases_sha256']}`",
        f"- 환경: Python {report['environment']['python']} / {report['environment']['platform']}",
        f"- 실행 시간: {report['duration_ms']} ms",
        "",
        f"## 요약: {report['summary']['passed']}/{report['summary']['total']} 통과",
        "",
        "| ID | 구분 | 결과 | 제목 | 실패 항목 |",
        "|---|---|---|---|---|",
    ]
    for case in report["cases"]:
        failed = [item["label"] for item in case["checks"] if not item["ok"]]
        note = case["failure"] or ", ".join(failed)
        lines.append(
            f"| {case['id']} | {case['split']} | {'PASS' if case['passed'] else 'FAIL'} | "
            f"{case['title']} | {note or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 해석 한계",
            "",
            "- 이 평가는 LLM 생성 품질이나 실제 조달 정확도를 측정하지 않는다.",
            "- 검색·게이트·상태 전이·멱등 실행 계약의 회귀 여부만 검증한다.",
            "- 공개 문서 본문은 검토용 요약이며, 합성 fixture는 실제 기준이 아니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    report = run_all(write=True)
    print(
        f"{report['summary']['passed']}/{report['summary']['total']} passed "
        f"({report['duration_ms']} ms)"
    )
    for case in report["cases"]:
        if not case["passed"]:
            print(f"FAIL {case['id']}: {case['failure'] or [item for item in case['checks'] if not item['ok']]}")
    print(f"results: {RESULTS_JSON}")
    return 0 if report["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
