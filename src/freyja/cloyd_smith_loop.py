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


class CloydSmithJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    DONE = "done"
    STOPPED = "stopped"


class CloydSmithJobCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective: str = Field(min_length=1)
    smith_alias: str = "freyja-code"
    acceptance_criteria: list[str] = Field(default_factory=list)
    current_prompt: str = Field(min_length=1)
    created_by: str = "joe"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloydSmithJobUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: CloydSmithJobStatus | None = None
    current_prompt: str | None = None
    next_action: str | None = None
    last_evidence: dict[str, Any] | None = None
    error: str | None = None


class CloydSmithJob(BaseModel):
    job_id: str
    objective: str
    smith_alias: str
    acceptance_criteria: list[str]
    current_prompt: str
    status: CloydSmithJobStatus
    created_by: str
    metadata: dict[str, Any]
    next_action: str | None = None
    last_evidence: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


def default_cloyd_smith_database_path() -> Path:
    configured = getattr(settings, "cloyd_smith_loop_database_path", "")
    if configured:
        return Path(configured).expanduser()
    return Path(settings.freyja3_worker_database_path).expanduser().with_name("cloyd_smith_loop.db")


class CloydSmithJobStore:
    """Durable Pratt 5.2 ledger for the Cloyd supervisor and Smith worker loop."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or default_cloyd_smith_database_path()).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create(self, request: CloydSmithJobCreate) -> CloydSmithJob:
        now = datetime.now(UTC)
        job = CloydSmithJob(
            job_id=f"pratt52-{uuid.uuid4().hex[:12]}",
            objective=request.objective,
            smith_alias=request.smith_alias,
            acceptance_criteria=request.acceptance_criteria,
            current_prompt=request.current_prompt,
            status=CloydSmithJobStatus.QUEUED,
            created_by=request.created_by,
            metadata=request.metadata,
            next_action="send_to_smith",
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cloyd_smith_jobs (
                    job_id, objective, smith_alias, acceptance_criteria_json,
                    current_prompt, status, created_by, metadata_json,
                    next_action, last_evidence_json, error,
                    created_at, updated_at, completed_at
                )
                VALUES (?, ?, ?, json(?), ?, ?, ?, json(?), ?, json(?), ?, ?, ?, ?)
                """,
                _row_values(job),
            )
        return job

    def get(self, job_id: str) -> CloydSmithJob:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cloyd_smith_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _job_from_row(row)

    def list_active(self, *, limit: int = 50) -> list[CloydSmithJob]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cloyd_smith_jobs
                WHERE status IN (?, ?, ?)
                ORDER BY created_at ASC, job_id ASC
                LIMIT ?
                """,
                (
                    CloydSmithJobStatus.QUEUED.value,
                    CloydSmithJobStatus.RUNNING.value,
                    CloydSmithJobStatus.NEEDS_REVIEW.value,
                    max(1, min(limit, 500)),
                ),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def update(self, job_id: str, update: CloydSmithJobUpdate) -> CloydSmithJob:
        current = self.get(job_id)
        status = update.status or current.status
        completed_at = current.completed_at
        if status in {CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.DONE, CloydSmithJobStatus.STOPPED}:
            completed_at = datetime.now(UTC)
        updated = current.model_copy(
            update={
                "status": status,
                "current_prompt": update.current_prompt if update.current_prompt is not None else current.current_prompt,
                "next_action": update.next_action if update.next_action is not None else current.next_action,
                "last_evidence": update.last_evidence if update.last_evidence is not None else current.last_evidence,
                "error": update.error if update.error is not None else current.error,
                "updated_at": datetime.now(UTC),
                "completed_at": completed_at,
            }
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE cloyd_smith_jobs
                SET current_prompt = ?, status = ?, next_action = ?,
                    last_evidence_json = json(?), error = ?, updated_at = ?,
                    completed_at = ?
                WHERE job_id = ?
                """,
                (
                    updated.current_prompt,
                    updated.status.value,
                    updated.next_action,
                    json.dumps(updated.last_evidence or {}),
                    updated.error,
                    _iso(updated.updated_at),
                    _iso(updated.completed_at) if updated.completed_at else None,
                    job_id,
                ),
            )
        return updated

    def add_event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cloyd_smith_job_events (event_id, job_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, json(?), ?)
                """,
                (str(uuid.uuid4()), job_id, event_type, json.dumps(payload), _iso(datetime.now(UTC))),
            )

    def events(self, job_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM cloyd_smith_job_events
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_id, max(1, min(limit, 200))),
            ).fetchall()
        return [
            {"event_type": row["event_type"], "payload": _decode(row["payload_json"], {}), "created_at": row["created_at"]}
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cloyd_smith_jobs (
                    job_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    smith_alias TEXT NOT NULL,
                    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
                    current_prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    next_action TEXT,
                    last_evidence_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cloyd_smith_job_events (
                    event_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES cloyd_smith_jobs(job_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cloyd_smith_jobs_status ON cloyd_smith_jobs(status, updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cloyd_smith_job_events_job ON cloyd_smith_job_events(job_id, created_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _row_values(job: CloydSmithJob) -> tuple[object, ...]:
    return (
        job.job_id,
        job.objective,
        job.smith_alias,
        json.dumps(job.acceptance_criteria),
        job.current_prompt,
        job.status.value,
        job.created_by,
        json.dumps(job.metadata),
        job.next_action,
        json.dumps(job.last_evidence or {}),
        job.error,
        _iso(job.created_at),
        _iso(job.updated_at),
        _iso(job.completed_at) if job.completed_at else None,
    )


def _job_from_row(row: sqlite3.Row) -> CloydSmithJob:
    return CloydSmithJob(
        job_id=row["job_id"],
        objective=row["objective"],
        smith_alias=row["smith_alias"],
        acceptance_criteria=_decode(row["acceptance_criteria_json"], []),
        current_prompt=row["current_prompt"],
        status=CloydSmithJobStatus(row["status"]),
        created_by=row["created_by"],
        metadata=_decode(row["metadata_json"], {}),
        next_action=row["next_action"],
        last_evidence=_decode(row["last_evidence_json"], {}) if row["last_evidence_json"] else None,
        error=row["error"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
        completed_at=_dt(row["completed_at"]) if row["completed_at"] else None,
    )


def _decode(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    decoded = json.loads(value)
    return decoded if isinstance(decoded, type(fallback)) else fallback


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
