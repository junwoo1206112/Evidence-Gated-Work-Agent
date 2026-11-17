from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from app.db import Database, DatabaseError
from tests.conftest import SUFFICIENT_REQUEST, create_run, approve, run_id_of


def test_schema_init_is_idempotent(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()
    db.initialize()
    health = db.health()
    assert health["ok"] is True
    assert health["schema_version"] == "1"


def test_wal_mode_is_enabled(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()
    assert db.health()["journal_mode"] == "wal"


def test_schema_version_mismatch_fails_fast(tmp_path) -> None:
    db = Database(tmp_path / "version.db")
    db.initialize()
    with db.transaction() as connection:
        connection.execute("UPDATE schema_meta SET value = '999' WHERE key = 'schema_version'")
    with pytest.raises(DatabaseError):
        db.initialize()


def test_audit_events_are_append_only(client, service) -> None:
    response = create_run(client)
    run_id = run_id_of(response)
    with pytest.raises(sqlite3.IntegrityError):
        with service.db.transaction() as connection:
            connection.execute(
                "UPDATE audit_events SET payload_json = '{}' WHERE run_id = ? AND seq = 1",
                (run_id,),
            )
    with pytest.raises(sqlite3.IntegrityError):
        with service.db.transaction() as connection:
            connection.execute("DELETE FROM audit_events WHERE run_id = ? AND seq = 1", (run_id,))
    assert service.audit.verify_chain(run_id).valid


def test_audit_hash_chain_detects_tampering(client, service) -> None:
    run_id = run_id_of(create_run(client))
    assert service.audit.verify_chain(run_id).valid
    with service.db.transaction() as connection:
        connection.execute("DROP TRIGGER audit_events_no_update")
        connection.execute(
            "UPDATE audit_events SET payload_json = '{}' WHERE run_id = ? AND seq = 1",
            (run_id,),
        )
    result = service.audit.verify_chain(run_id)
    assert not result.valid
    assert result.broken_at_seq == 1


def test_state_and_audit_roll_back_together(client, service) -> None:
    run_id = run_id_of(create_run(client))
    before = service.db.count_rows(run_id)
    now = service._iso(service.settings.now())
    with pytest.raises(RuntimeError):
        with service.db.transaction() as connection:
            service._transition(
                connection,
                run_id,
                "PENDING_APPROVAL",
                "APPROVED",
                now,
                reason="rollback_test",
            )
            raise RuntimeError("force rollback")
    after = service.db.count_rows(run_id)
    assert after == before
    assert service.get_run(run_id)["run"]["status"] == "PENDING_APPROVAL"


def test_data_persists_across_database_reopen(client, service, settings) -> None:
    run_id = run_id_of(create_run(client))
    reopened = Database(settings.db_path)
    reopened.initialize()
    with reopened.read() as connection:
        count = connection.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0]
    assert count == 1
    assert reopened.count_rows(run_id)["plans"] == 1


def test_count_rows_reports_all_tables(client, service) -> None:
    run_id = run_id_of(create_run(client))
    rows = service.db.count_rows(run_id)
    assert rows["plans"] == 1
    assert rows["approvals"] == 0
    assert rows["executions"] == 0
    assert rows["evidence"] > 0
    assert rows["audit_events"] > 0


def test_reconcile_interrupted_execution(client, service) -> None:
    run_id = run_id_of(create_run(client))
    assert approve(client, run_id).status_code == 200
    old = service._iso(service.settings.now() - timedelta(hours=1))
    with service.db.transaction() as connection:
        connection.execute(
            "UPDATE runs SET status = 'EXECUTING', updated_at = ? WHERE run_id = ?",
            (old, run_id),
        )
    assert service.reconcile_stale_runs(older_than_seconds=60) == 1
    detail = service.get_run(run_id)
    assert detail["run"]["status"] == "FAILED"
    assert any(event["event_type"] == "RECONCILED_INTERRUPTED" for event in detail["audit"])
    assert service.audit.verify_chain(run_id).valid
