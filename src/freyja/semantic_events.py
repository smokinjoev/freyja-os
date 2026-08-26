from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from freyja.config import settings
from freyja.foundation_models import SecurityDomainId, SemanticEvent


class SemanticEventPermissionError(PermissionError):
    pass


class SemanticEventQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str | None = None
    room: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class SemanticEventStore:
    """Durable semantic event bus substrate for Hera -> Atlas events."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.freyja3_event_database_path).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def publish(self, event: SemanticEvent, *, publisher_domain_id: SecurityDomainId) -> SemanticEvent:
        if publisher_domain_id != SecurityDomainId.SYSTEM or event.source_machine_id != "hera":
            raise SemanticEventPermissionError("only Hera system publishers may publish semantic perception events")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_events (
                    event_id, source_machine_id, event_type, room, subject,
                    confidence, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, json(?), ?)
                """,
                (
                    event.event_id,
                    event.source_machine_id,
                    event.event_type,
                    event.room,
                    event.subject,
                    event.confidence,
                    json.dumps(event.metadata),
                    event.created_at.isoformat(),
                ),
            )
        return event

    def list_events(self, query: SemanticEventQuery | None = None, *, reader_domain_id: SecurityDomainId) -> list[SemanticEvent]:
        if reader_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise SemanticEventPermissionError("semantic household events require household or system read access")
        query = query or SemanticEventQuery()
        clauses: list[str] = []
        params: list[object] = []
        if query.event_type:
            clauses.append("event_type = ?")
            params.append(query.event_type)
        if query.room:
            clauses.append("room = ?")
            params.append(query.room)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(query.limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT event_id, source_machine_id, event_type, room, subject, confidence,
                       metadata_json, created_at
                FROM semantic_events
                {where}
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            SemanticEvent(
                event_id=row["event_id"],
                source_machine_id=row["source_machine_id"],
                event_type=row["event_type"],
                room=row["room"],
                subject=row["subject"],
                confidence=row["confidence"],
                metadata=_decode_metadata(row["metadata_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_events (
                    event_id TEXT PRIMARY KEY,
                    source_machine_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    room TEXT,
                    subject TEXT,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_events_type_created ON semantic_events(event_type, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_events_room_created ON semantic_events(room, created_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _decode_metadata(value: str | None) -> dict:
    if not value:
        return {}
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}
