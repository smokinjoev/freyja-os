from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freyja.config import settings
from freyja.foundation_models import SecurityDomainId


class Freyja3WorkerAccessError(PermissionError):
    pass


class Freyja3WorkerJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Freyja3WorkerJobCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    worker_class: str = Field(min_length=1)
    target_machine_id: str | None = None
    objective: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_by_domain_id: SecurityDomainId = SecurityDomainId.SYSTEM
    metadata: dict[str, Any] = Field(default_factory=dict)


class Freyja3WorkerJob(Freyja3WorkerJobCreate):
    status: Freyja3WorkerJobStatus = Freyja3WorkerJobStatus.PENDING
    claimed_by_machine_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claimed_at: datetime | None = None
    completed_at: datetime | None = None


class Freyja3WorkerJobQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Freyja3WorkerJobStatus | None = None
    worker_class: str | None = None
    target_machine_id: str | None = None
    include_completed: bool = False
    limit: int = Field(default=50, ge=1, le=500)


class Freyja3WorkerJobComplete(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Freyja3WorkerJobStatus = Field(pattern="^(completed|failed)$")
    result: dict[str, Any] | None = None
    error: str | None = None


class Freyja3WorkerJobStore:
    """Durable Atlas-owned work queue for Mars/Freyja workers."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.freyja3_worker_database_path).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create(self, job: Freyja3WorkerJobCreate, *, writer_domain_id: SecurityDomainId) -> Freyja3WorkerJob:
        if writer_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise Freyja3WorkerAccessError("worker jobs require household or system write access")
        created = Freyja3WorkerJob(**job.model_dump(), created_at=datetime.now(UTC))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO freyja3_worker_jobs (
                    job_id, worker_class, target_machine_id, objective, payload_json,
                    created_by_domain_id, metadata_json, status, claimed_by_machine_id,
                    result_json, error, created_at, claimed_at, completed_at
                )
                VALUES (?, ?, ?, ?, json(?), ?, json(?), ?, ?, json(?), ?, ?, ?, ?)
                """,
                _row_values(created),
            )
        return created

    def list(self, query: Freyja3WorkerJobQuery | None = None, *, reader_domain_id: SecurityDomainId) -> list[Freyja3WorkerJob]:
        if reader_domain_id not in {SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}:
            raise Freyja3WorkerAccessError("worker jobs require household or system read access")
        query = query or Freyja3WorkerJobQuery()
        clauses: list[str] = []
        params: list[object] = []
        if query.status is not None:
            clauses.append("status = ?")
            params.append(query.status.value)
        elif not query.include_completed:
            clauses.append("status IN (?, ?)")
            params.extend([Freyja3WorkerJobStatus.PENDING.value, Freyja3WorkerJobStatus.RUNNING.value])
        if query.worker_class:
            clauses.append("worker_class = ?")
            params.append(query.worker_class)
        if query.target_machine_id:
            clauses.append("(target_machine_id IS NULL OR target_machine_id = ?)")
            params.append(query.target_machine_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(query.limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM freyja3_worker_jobs
                {where}
                ORDER BY created_at ASC, job_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def claim_next(
        self,
        *,
        machine_id: str,
        worker_class: str | None,
        claimer_domain_id: SecurityDomainId,
    ) -> Freyja3WorkerJob | None:
        if claimer_domain_id != SecurityDomainId.SYSTEM:
            raise Freyja3WorkerAccessError("worker job claims require system access")
        clauses = ["status = ?", "(target_machine_id IS NULL OR target_machine_id = ?)"]
        params: list[object] = [Freyja3WorkerJobStatus.PENDING.value, machine_id]
        if worker_class:
            clauses.append("worker_class = ?")
            params.append(worker_class)
        claimed_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                f"""
                UPDATE freyja3_worker_jobs
                SET status = ?, claimed_by_machine_id = ?, claimed_at = ?
                WHERE job_id = (
                    SELECT job_id FROM freyja3_worker_jobs
                    WHERE {' AND '.join(clauses)}
                    ORDER BY created_at ASC, job_id ASC
                    LIMIT 1
                )
                RETURNING *
                """,
                [Freyja3WorkerJobStatus.RUNNING.value, machine_id, claimed_at, *params],
            ).fetchone()
        return _job_from_row(row) if row else None

    def complete(
        self,
        job_id: str,
        completion: Freyja3WorkerJobComplete,
        *,
        machine_id: str,
        completer_domain_id: SecurityDomainId,
    ) -> Freyja3WorkerJob:
        if completer_domain_id != SecurityDomainId.SYSTEM:
            raise Freyja3WorkerAccessError("worker job completion requires system access")
        completed_at = datetime.now(UTC).isoformat()
        status = Freyja3WorkerJobStatus(completion.status)
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE freyja3_worker_jobs
                SET status = ?, result_json = json(?), error = ?, completed_at = ?
                WHERE job_id = ? AND status = ? AND claimed_by_machine_id = ?
                RETURNING *
                """,
                (
                    status.value,
                    json.dumps(completion.result or {}),
                    completion.error,
                    completed_at,
                    job_id,
                    Freyja3WorkerJobStatus.RUNNING.value,
                    machine_id,
                ),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _job_from_row(row)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS freyja3_worker_jobs (
                    job_id TEXT PRIMARY KEY,
                    worker_class TEXT NOT NULL,
                    target_machine_id TEXT,
                    objective TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_by_domain_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    claimed_by_machine_id TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    claimed_at TEXT,
                    completed_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_worker_jobs_claim ON freyja3_worker_jobs(status, target_machine_id, worker_class, created_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _row_values(job: Freyja3WorkerJob) -> tuple[object, ...]:
    return (
        job.job_id,
        job.worker_class,
        job.target_machine_id,
        job.objective,
        json.dumps(job.payload),
        job.created_by_domain_id.value,
        json.dumps(job.metadata),
        job.status.value,
        job.claimed_by_machine_id,
        json.dumps(job.result or {}),
        job.error,
        _iso(job.created_at),
        _iso(job.claimed_at) if job.claimed_at else None,
        _iso(job.completed_at) if job.completed_at else None,
    )


def _job_from_row(row: sqlite3.Row) -> Freyja3WorkerJob:
    return Freyja3WorkerJob(
        job_id=row["job_id"],
        worker_class=row["worker_class"],
        target_machine_id=row["target_machine_id"],
        objective=row["objective"],
        payload=_decode_metadata(row["payload_json"]),
        created_by_domain_id=SecurityDomainId(row["created_by_domain_id"]),
        metadata=_decode_metadata(row["metadata_json"]),
        status=Freyja3WorkerJobStatus(row["status"]),
        claimed_by_machine_id=row["claimed_by_machine_id"],
        result=_decode_metadata(row["result_json"]) if row["result_json"] else None,
        error=row["error"],
        created_at=row["created_at"],
        claimed_at=row["claimed_at"],
        completed_at=row["completed_at"],
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
