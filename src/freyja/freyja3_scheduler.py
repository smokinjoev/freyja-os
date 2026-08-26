from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freyja.config import settings
from freyja.foundation_models import SecurityDomainId


class Freyja3ScheduleAccessError(PermissionError):
    pass


class Freyja3ScheduleCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    schedule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    due_at: datetime
    target_agent_id: str = Field(min_length=1)
    resolved_user_id: str | None = None
    conversation_id: str = Field(min_length=1)
    channel: str = "scheduler"
    text: str = Field(min_length=1)
    created_by_domain_id: SecurityDomainId = SecurityDomainId.SYSTEM
    metadata: dict[str, Any] = Field(default_factory=dict)


class Freyja3ScheduledEnvelope(Freyja3ScheduleCreate):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dispatched_at: datetime | None = None


class Freyja3ScheduleQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    due_before: datetime | None = None
    include_dispatched: bool = False
    limit: int = Field(default=50, ge=1, le=500)


class Freyja3SchedulerStore:
    """Durable Atlas scheduler for deterministic agent trigger envelopes."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.freyja3_scheduler_database_path).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create(self, schedule: Freyja3ScheduleCreate, *, writer_domain_id: SecurityDomainId) -> Freyja3ScheduledEnvelope:
        if writer_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise Freyja3ScheduleAccessError("scheduled agent triggers require household or system write access")
        envelope = Freyja3ScheduledEnvelope(**schedule.model_dump())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO freyja3_schedules (
                    schedule_id, due_at, target_agent_id, resolved_user_id,
                    conversation_id, channel, text, created_by_domain_id,
                    metadata_json, created_at, dispatched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, json(?), ?, ?)
                """,
                _row_values(envelope),
            )
        return envelope

    def list(self, query: Freyja3ScheduleQuery | None = None, *, reader_domain_id: SecurityDomainId) -> list[Freyja3ScheduledEnvelope]:
        if reader_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise Freyja3ScheduleAccessError("scheduled agent triggers require household or system read access")
        query = query or Freyja3ScheduleQuery()
        clauses: list[str] = []
        params: list[object] = []
        if query.due_before is not None:
            clauses.append("due_at <= ?")
            params.append(_iso(query.due_before))
        if not query.include_dispatched:
            clauses.append("dispatched_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(query.limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT schedule_id, due_at, target_agent_id, resolved_user_id,
                       conversation_id, channel, text, created_by_domain_id,
                       metadata_json, created_at, dispatched_at
                FROM freyja3_schedules
                {where}
                ORDER BY due_at ASC, created_at ASC, schedule_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_envelope_from_row(row) for row in rows]

    def mark_dispatched(self, schedule_id: str, *, dispatcher_domain_id: SecurityDomainId) -> Freyja3ScheduledEnvelope:
        if dispatcher_domain_id != SecurityDomainId.SYSTEM:
            raise Freyja3ScheduleAccessError("only system dispatchers may mark scheduled agent triggers dispatched")
        dispatched_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE freyja3_schedules
                SET dispatched_at = ?
                WHERE schedule_id = ? AND dispatched_at IS NULL
                RETURNING schedule_id, due_at, target_agent_id, resolved_user_id,
                          conversation_id, channel, text, created_by_domain_id,
                          metadata_json, created_at, dispatched_at
                """,
                (dispatched_at, schedule_id),
            ).fetchone()
        if row is None:
            raise KeyError(schedule_id)
        return _envelope_from_row(row)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS freyja3_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    due_at TEXT NOT NULL,
                    target_agent_id TEXT NOT NULL,
                    resolved_user_id TEXT,
                    conversation_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_by_domain_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    dispatched_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_schedules_due ON freyja3_schedules(due_at, dispatched_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _row_values(envelope: Freyja3ScheduledEnvelope) -> tuple[object, ...]:
    return (
        envelope.schedule_id,
        _iso(envelope.due_at),
        envelope.target_agent_id,
        envelope.resolved_user_id,
        envelope.conversation_id,
        envelope.channel,
        envelope.text,
        envelope.created_by_domain_id.value,
        json.dumps(envelope.metadata),
        _iso(envelope.created_at),
        _iso(envelope.dispatched_at) if envelope.dispatched_at else None,
    )


def _envelope_from_row(row: sqlite3.Row) -> Freyja3ScheduledEnvelope:
    return Freyja3ScheduledEnvelope(
        schedule_id=row["schedule_id"],
        due_at=row["due_at"],
        target_agent_id=row["target_agent_id"],
        resolved_user_id=row["resolved_user_id"],
        conversation_id=row["conversation_id"],
        channel=row["channel"],
        text=row["text"],
        created_by_domain_id=SecurityDomainId(row["created_by_domain_id"]),
        metadata=_decode_metadata(row["metadata_json"]),
        created_at=row["created_at"],
        dispatched_at=row["dispatched_at"],
    )


def _decode_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
