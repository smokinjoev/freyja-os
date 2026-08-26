from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freyja.config import settings
from freyja.foundation_models import AuditEvent, AuditEventType, SecurityDomainId


class Freyja3AuditAccessError(PermissionError):
    pass


class Freyja3AuditQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: AuditEventType | None = None
    actor_id: str | None = None
    target_id: str | None = None
    trace_id: str | None = None
    conversation_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class Freyja3AuditStore:
    """Durable Freyja 3 audit event store for Atlas observability."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.freyja3_audit_database_path).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def record_many(
        self,
        events: list[AuditEvent],
        *,
        writer_domain_id: SecurityDomainId,
        trace_id: str | None = None,
        conversation_id: str | None = None,
    ) -> int:
        if writer_domain_id != SecurityDomainId.SYSTEM:
            raise Freyja3AuditAccessError("audit writes require system access")
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO freyja3_audit_events (
                    event_id, event_type, actor_id, domain_id, target_id,
                    allowed, reason, metadata_json, trace_id, conversation_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, json(?), ?, ?, ?)
                """,
                [_row_values(event, trace_id=trace_id, conversation_id=conversation_id) for event in events],
            )
        return len(events)

    def list(self, query: Freyja3AuditQuery | None = None, *, reader_domain_id: SecurityDomainId) -> list[AuditEvent]:
        if reader_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise Freyja3AuditAccessError("audit reads require household or system access")
        query = query or Freyja3AuditQuery()
        clauses: list[str] = []
        params: list[object] = []
        if query.event_type is not None:
            clauses.append("event_type = ?")
            params.append(query.event_type.value)
        if query.actor_id:
            clauses.append("actor_id = ?")
            params.append(query.actor_id)
        if query.target_id:
            clauses.append("target_id = ?")
            params.append(query.target_id)
        if query.trace_id:
            clauses.append("trace_id = ?")
            params.append(query.trace_id)
        if query.conversation_id:
            clauses.append("conversation_id = ?")
            params.append(query.conversation_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(query.limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT event_id, event_type, actor_id, domain_id, target_id,
                       allowed, reason, metadata_json, created_at
                FROM freyja3_audit_events
                {where}
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS freyja3_audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    domain_id TEXT NOT NULL,
                    target_id TEXT,
                    allowed INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    trace_id TEXT,
                    conversation_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_audit_trace ON freyja3_audit_events(trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_audit_conversation ON freyja3_audit_events(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_audit_type_created ON freyja3_audit_events(event_type, created_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _row_values(event: AuditEvent, *, trace_id: str | None, conversation_id: str | None) -> tuple[object, ...]:
    return (
        event.event_id,
        event.event_type.value,
        event.actor_id,
        event.domain_id.value,
        event.target_id,
        1 if event.allowed else 0,
        event.reason,
        json.dumps(event.metadata),
        trace_id,
        conversation_id,
        event.created_at.isoformat(),
    )


def _event_from_row(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        event_id=row["event_id"],
        event_type=AuditEventType(row["event_type"]),
        actor_id=row["actor_id"],
        domain_id=SecurityDomainId(row["domain_id"]),
        target_id=row["target_id"],
        allowed=bool(row["allowed"]),
        reason=row["reason"],
        metadata=_decode_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def _decode_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}
