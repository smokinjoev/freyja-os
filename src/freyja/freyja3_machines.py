from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freyja.config import settings
from freyja.foundation_models import SecurityDomainId


class Freyja3MachineAccessError(PermissionError):
    pass


class Freyja3MachineHeartbeat(BaseModel):
    model_config = ConfigDict(frozen=True)

    machine_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    status: str = Field(default="ok", min_length=1)
    commit_sha: str | None = None
    service: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Freyja3MachineStatus(Freyja3MachineHeartbeat):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Freyja3MachineStatusStore:
    """Durable machine-role heartbeat store for Freyja infrastructure."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.freyja3_machine_database_path).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def heartbeat(self, heartbeat: Freyja3MachineHeartbeat, *, writer_domain_id: SecurityDomainId) -> Freyja3MachineStatus:
        if writer_domain_id != SecurityDomainId.SYSTEM:
            raise Freyja3MachineAccessError("machine heartbeats require system write access")
        status = Freyja3MachineStatus(**heartbeat.model_dump(), updated_at=datetime.now(UTC))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO freyja3_machine_status (
                    machine_id, role, status, commit_sha, service,
                    metadata_json, observed_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, json(?), ?, ?)
                ON CONFLICT(machine_id) DO UPDATE SET
                    role = excluded.role,
                    status = excluded.status,
                    commit_sha = excluded.commit_sha,
                    service = excluded.service,
                    metadata_json = excluded.metadata_json,
                    observed_at = excluded.observed_at,
                    updated_at = excluded.updated_at
                """,
                (
                    status.machine_id,
                    status.role,
                    status.status,
                    status.commit_sha,
                    status.service,
                    json.dumps(status.metadata),
                    _iso(status.observed_at),
                    _iso(status.updated_at),
                ),
            )
        return status

    def list(self, *, reader_domain_id: SecurityDomainId) -> list[Freyja3MachineStatus]:
        if reader_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise Freyja3MachineAccessError("machine status requires household or system read access")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT machine_id, role, status, commit_sha, service,
                       metadata_json, observed_at, updated_at
                FROM freyja3_machine_status
                ORDER BY machine_id ASC
                """
            ).fetchall()
        return [_status_from_row(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS freyja3_machine_status (
                    machine_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    commit_sha TEXT,
                    service TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    observed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _status_from_row(row: sqlite3.Row) -> Freyja3MachineStatus:
    return Freyja3MachineStatus(
        machine_id=row["machine_id"],
        role=row["role"],
        status=row["status"],
        commit_sha=row["commit_sha"],
        service=row["service"],
        metadata=_decode_metadata(row["metadata_json"]),
        observed_at=row["observed_at"],
        updated_at=row["updated_at"],
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
