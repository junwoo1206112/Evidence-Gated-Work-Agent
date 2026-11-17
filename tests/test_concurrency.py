from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.conftest import approve, create_run, run_id_of


def _execute_in_new_client(app, run_id: str, key: str) -> tuple[int, str | None]:
    with TestClient(app) as client:
        response = client.post(
            f"/api/runs/{run_id}/executions",
            json={"idempotency_key": key},
        )
        code = None
        if response.headers.get("content-type", "").startswith("application/json"):
            code = (response.json().get("error") or {}).get("code")
        return response.status_code, code


def test_concurrent_same_key_executes_once(app, client, service, monkeypatch) -> None:
    run_id = run_id_of(create_run(client))
    assert approve(client, run_id).status_code == 200

    original = service.executor.run

    def slow_run(*args, **kwargs):
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.executor, "run", slow_run)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _execute_in_new_client(app, run_id, "concurrent-key-0001"), range(4)))

    statuses = [status for status, _ in results]
    assert 200 in statuses
    assert all(status in {200, 409} for status in statuses), results
    assert service.db.count_rows(run_id)["executions"] == 1
    detail = service.get_run(run_id)
    assert detail["run"]["status"] == "EXECUTED"
    assert service.audit.verify_chain(run_id).valid


def test_concurrent_different_keys_executes_once(app, client, service, monkeypatch) -> None:
    run_id = run_id_of(create_run(client))
    assert approve(client, run_id).status_code == 200

    original = service.executor.run

    def slow_run(*args, **kwargs):
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.executor, "run", slow_run)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda index: _execute_in_new_client(app, run_id, f"concurrent-key-{index:04d}"),
                range(4),
            )
        )
    statuses = [status for status, _ in results]
    assert statuses.count(200) == 1, results
    assert all(status in {200, 409} for status in statuses), results
    assert service.db.count_rows(run_id)["executions"] == 1


def test_concurrent_approval_creates_one_approval(app, client, service) -> None:
    run_id = run_id_of(create_run(client))

    def approve_once(_):
        with TestClient(app) as local:
            return local.post(
                f"/api/runs/{run_id}/approval",
                json={"decision": "approve", "reason": "concurrent"},
            ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(approve_once, range(4)))
    assert statuses.count(200) == 1, statuses
    assert all(status in {200, 409} for status in statuses), statuses
    assert service.db.count_rows(run_id)["approvals"] == 1
    assert service.audit.verify_chain(run_id).valid


def test_audit_seq_is_contiguous_after_denials(client, service) -> None:
    run_id = run_id_of(create_run(client))
    for index in range(5):
        response = client.post(
            f"/api/runs/{run_id}/executions",
            json={"idempotency_key": f"denied-key-{index:04d}"},
        )
        assert response.status_code == 409
    events = service.audit.list(run_id)
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert service.audit.verify_chain(run_id).valid
