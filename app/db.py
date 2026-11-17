from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.version import SCHEMA_VERSION

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    user_request TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'DRAFT','RETRIEVING','EVIDENCE_INSUFFICIENT','PENDING_APPROVAL',
        'APPROVED','EXECUTING','EXECUTED','FAILED','RETRYING','REJECTED'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    as_of TEXT NOT NULL,
    demo_mode TEXT NOT NULL CHECK (demo_mode IN ('none','fail_once','fail_twice')),
    corpus_sha256 TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    gate_category TEXT,
    gate_reason TEXT,
    gate_json TEXT,
    evidence_fingerprint TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_tier TEXT NOT NULL,
    retrieval_score REAL NOT NULL,
    coverage REAL NOT NULL,
    bm25 REAL NOT NULL,
    matched_terms_json TEXT NOT NULL,
    citation_valid INTEGER NOT NULL CHECK (citation_valid IN (0,1)),
    invalid_reason TEXT,
    invalid_detail TEXT,
    policy_key TEXT,
    policy_scope TEXT,
    policy_value TEXT,
    effective_from TEXT,
    effective_to TEXT,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, document_id)
);

CREATE TABLE IF NOT EXISTS plans (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    plan_version TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    evidence_fingerprint TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    corpus_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id) ON DELETE CASCADE,
    approved_by TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve','reject')),
    plan_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 2),
    status TEXT NOT NULL CHECK (status IN ('EXECUTED','FAILED')),
    result_json TEXT,
    error_reason TEXT,
    executed_at TEXT NOT NULL,
    UNIQUE (run_id, idempotency_key, attempt)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_executions_run_key ON executions(run_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_audit_run_seq ON audit_events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
"""


class DatabaseError(RuntimeError):
    pass


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path),
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA_SQL)
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                    (SCHEMA_VERSION,),
                )
            elif str(row["value"]) != SCHEMA_VERSION:
                raise DatabaseError(
                    f"지원하지 않는 schema_version입니다: {row['value']} (기대 {SCHEMA_VERSION})"
                )
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
        finally:
            try:
                connection.execute("COMMIT")
            except sqlite3.Error:
                pass
            connection.close()

    def health(self) -> dict:
        try:
            connection = self.connect()
            try:
                connection.execute("SELECT 1").fetchone()
                schema = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                if schema is None or str(schema["value"]) != SCHEMA_VERSION:
                    return {
                        "ok": False,
                        "error": "schema_version_mismatch",
                        "schema_version": str(schema["value"]) if schema else None,
                        "expected": SCHEMA_VERSION,
                    }
                journal = connection.execute("PRAGMA journal_mode").fetchone()
            finally:
                connection.close()
            return {
                "ok": True,
                "schema_version": str(schema["value"]),
                "journal_mode": str(journal[0]).lower() if journal else None,
            }
        except sqlite3.Error as exc:
            return {"ok": False, "error": type(exc).__name__}

    def count_rows(self, run_id: str) -> dict[str, int]:
        with self.read() as connection:
            return {
                "plans": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM plans WHERE run_id = ?", (run_id,)
                    ).fetchone()[0]
                ),
                "approvals": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM approvals WHERE run_id = ?", (run_id,)
                    ).fetchone()[0]
                ),
                "executions": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM executions WHERE run_id = ?", (run_id,)
                    ).fetchone()[0]
                ),
                "evidence": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE run_id = ?", (run_id,)
                    ).fetchone()[0]
                ),
                "audit_events": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM audit_events WHERE run_id = ?", (run_id,)
                    ).fetchone()[0]
                ),
            }
