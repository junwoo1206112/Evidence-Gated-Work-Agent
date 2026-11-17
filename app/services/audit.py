from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.db import Database
from app.domain.models import AuditEventRecord
from app.textutil import canonical_json, sha256_text

GENESIS_HASH = "0" * 64
MAX_DENIED_EVENTS = 20


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    events: int
    broken_at_seq: int | None = None


class AuditLog:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _compute_hash(
        *,
        prev_hash: str,
        run_id: str,
        seq: int,
        event_type: str,
        payload_json: str,
        occurred_at: str,
    ) -> str:
        material = "|".join(
            [prev_hash, run_id, str(seq), event_type, payload_json, occurred_at]
        )
        return sha256_text(material)

    def append(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        event_type: str,
        payload: dict,
        occurred_at: str,
    ) -> AuditEventRecord:
        last = connection.execute(
            "SELECT seq, event_hash FROM audit_events WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        seq = int(last["seq"]) + 1 if last else 1
        prev_hash = str(last["event_hash"]) if last else GENESIS_HASH
        payload_json = canonical_json(payload)
        event_hash = self._compute_hash(
            prev_hash=prev_hash,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            payload_json=payload_json,
            occurred_at=occurred_at,
        )
        cursor = connection.execute(
            """
            INSERT INTO audit_events
                (run_id, seq, event_type, payload_json, occurred_at, prev_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, seq, event_type, payload_json, occurred_at, prev_hash, event_hash),
        )
        return AuditEventRecord(
            event_id=int(cursor.lastrowid),
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            payload_json=payload_json,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )

    def record_denied(
        self,
        *,
        run_id: str,
        action: str,
        code: str,
        server_state: str,
        details: dict | None = None,
        occurred_at: str,
    ) -> None:
        # Denied attempts do not change run state, but they are still audited.
        # The cap prevents an unauthenticated caller from growing the audit log
        # without bound.
        with self.db.transaction() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM audit_events WHERE run_id = ? AND event_type LIKE 'DENIED_%'",
                (run_id,),
            ).fetchone()[0]
            if int(count) >= MAX_DENIED_EVENTS:
                return
            self.append(
                connection,
                run_id=run_id,
                event_type=f"DENIED_{action}",
                payload={
                    "code": code,
                    "server_state": server_state,
                    "details": details or {},
                },
                occurred_at=occurred_at,
            )

    def list(self, run_id: str) -> list[AuditEventRecord]:
        with self.db.read() as connection:
            return self.list_with_connection(connection, run_id)

    def list_with_connection(self, connection, run_id: str) -> list[AuditEventRecord]:
        rows = connection.execute(
            "SELECT * FROM audit_events WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    @classmethod
    def verify_chain_events(cls, events: list[AuditEventRecord]) -> ChainVerification:
        prev = GENESIS_HASH
        for event in events:
            expected = cls._compute_hash(
                prev_hash=prev,
                run_id=event.run_id,
                seq=event.seq,
                event_type=event.event_type,
                payload_json=event.payload_json,
                occurred_at=event.occurred_at,
            )
            if event.prev_hash != prev or event.event_hash != expected:
                return ChainVerification(False, len(events), event.seq)
            prev = event.event_hash
        return ChainVerification(True, len(events))

    def verify_chain(self, run_id: str) -> ChainVerification:
        events = self.list(run_id)
        return self.verify_chain_events(events)

    def verify_chain_with_connection(self, connection, run_id: str) -> ChainVerification:
        return self.verify_chain_events(self.list_with_connection(connection, run_id))

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> AuditEventRecord:
        return AuditEventRecord(
            event_id=int(row["event_id"]),
            run_id=str(row["run_id"]),
            seq=int(row["seq"]),
            event_type=str(row["event_type"]),
            payload_json=str(row["payload_json"]),
            occurred_at=str(row["occurred_at"]),
            prev_hash=str(row["prev_hash"]),
            event_hash=str(row["event_hash"]),
        )

    @staticmethod
    def payload(record: AuditEventRecord) -> dict:
        try:
            return json.loads(record.payload_json)
        except (TypeError, ValueError):
            return {}
