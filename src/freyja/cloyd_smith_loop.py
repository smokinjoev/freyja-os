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
    STALE = "stale"


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
    metadata: dict[str, Any] | None = None
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


class AgentRunHeartbeat(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    agent: str
    alias: str
    session_id: str | None = None
    state: str
    phase: str
    last_action: str
    last_message: str = ""
    last_error: str = ""
    working_directory: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    stale_after_seconds: int = Field(default=300, ge=1)
    stop_reason: str | None = None


def default_cloyd_smith_database_path() -> Path:
    configured = getattr(settings, "cloyd_smith_loop_database_path", "")
    if configured:
        return Path(configured).expanduser()
    return Path(settings.freyja3_worker_database_path).expanduser().with_name("cloyd_smith_loop.db")


def default_cloyd_smith_supervisor_heartbeat_path(database_path: str | Path | None = None) -> Path:
    if database_path is None:
        database_path = default_cloyd_smith_database_path()
    path = Path(database_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.with_suffix(path.suffix + ".supervisor.json")


def read_supervisor_heartbeat(
    database_path: str | Path | None = None,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 90,
) -> dict[str, Any]:
    path = default_cloyd_smith_supervisor_heartbeat_path(database_path)
    if not path.exists():
        return {
            "ok": False,
            "status": "missing",
            "path": str(path),
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "error": "Supervisor heartbeat has not been written yet.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "unreadable",
            "path": str(path),
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "error": str(exc),
        }
    checked_at = now or datetime.now(UTC)
    updated_at_text = str(payload.get("updated_at") or "")
    try:
        updated_at = _dt(updated_at_text)
    except ValueError:
        return {
            "ok": False,
            "status": "invalid",
            "path": str(path),
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "error": f"Invalid supervisor heartbeat timestamp: {updated_at_text}",
            "payload": payload,
        }
    age_seconds = max(0, int((checked_at - updated_at).total_seconds()))
    stale = age_seconds > stale_after_seconds
    return {
        "ok": not stale and bool(payload.get("ok", True)),
        "status": "stale" if stale else str(payload.get("status") or "ok"),
        "path": str(path),
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "payload": payload,
    }


class CloydSmithJobStore:
    """Durable Freyja 5.2 ledger for the Cloyd supervisor and Smith worker loop."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or default_cloyd_smith_database_path()).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create(self, request: CloydSmithJobCreate) -> CloydSmithJob:
        now = datetime.now(UTC)
        job = CloydSmithJob(
            job_id=f"freyja52-{uuid.uuid4().hex[:12]}",
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
                WHERE status IN (?, ?, ?, ?)
                ORDER BY created_at ASC, job_id ASC
                LIMIT ?
                """,
                (
                    CloydSmithJobStatus.QUEUED.value,
                    CloydSmithJobStatus.RUNNING.value,
                    CloydSmithJobStatus.NEEDS_REVIEW.value,
                    CloydSmithJobStatus.STALE.value,
                    max(1, min(limit, 500)),
                ),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def list_recent_terminal(self, *, limit: int = 10) -> list[CloydSmithJob]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cloyd_smith_jobs
                WHERE status IN (?, ?, ?)
                ORDER BY completed_at DESC, updated_at DESC
                LIMIT ?
                """,
                (
                    CloydSmithJobStatus.DONE.value,
                    CloydSmithJobStatus.BLOCKED.value,
                    CloydSmithJobStatus.STOPPED.value,
                    max(1, min(limit, 100)),
                ),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def update(self, job_id: str, update: CloydSmithJobUpdate) -> CloydSmithJob:
        current = self.get(job_id)
        status = update.status or current.status
        completed_at = current.completed_at
        if status in {
            CloydSmithJobStatus.BLOCKED,
            CloydSmithJobStatus.DONE,
            CloydSmithJobStatus.STOPPED,
            CloydSmithJobStatus.STALE,
        }:
            completed_at = datetime.now(UTC)
        elif current.status in {
            CloydSmithJobStatus.BLOCKED,
            CloydSmithJobStatus.DONE,
            CloydSmithJobStatus.STOPPED,
            CloydSmithJobStatus.STALE,
        }:
            completed_at = None
        updated = current.model_copy(
            update={
                "status": status,
                "current_prompt": update.current_prompt if update.current_prompt is not None else current.current_prompt,
                "next_action": update.next_action if update.next_action is not None else current.next_action,
                "last_evidence": update.last_evidence if update.last_evidence is not None else current.last_evidence,
                "metadata": update.metadata if update.metadata is not None else current.metadata,
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
                    last_evidence_json = json(?), metadata_json = json(?),
                    error = ?, updated_at = ?,
                    completed_at = ?
                WHERE job_id = ?
                """,
                (
                    updated.current_prompt,
                    updated.status.value,
                    updated.next_action,
                    json.dumps(updated.last_evidence or {}),
                    json.dumps(updated.metadata),
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

    def record_heartbeat(self, heartbeat: AgentRunHeartbeat) -> AgentRunHeartbeat:
        existing = self.get_heartbeat(heartbeat.job_id)
        started_at = heartbeat.started_at or (existing.started_at if existing else heartbeat.updated_at)
        stored = heartbeat.model_copy(update={"started_at": started_at})
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cloyd_smith_run_heartbeats (
                    job_id, agent, alias, session_id, state, phase, last_action,
                    last_message, last_error, working_directory, started_at,
                    updated_at, stale_after_seconds, stop_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    agent = excluded.agent,
                    alias = excluded.alias,
                    session_id = excluded.session_id,
                    state = excluded.state,
                    phase = excluded.phase,
                    last_action = excluded.last_action,
                    last_message = excluded.last_message,
                    last_error = excluded.last_error,
                    working_directory = excluded.working_directory,
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at,
                    stale_after_seconds = excluded.stale_after_seconds,
                    stop_reason = excluded.stop_reason
                """,
                _heartbeat_values(stored),
            )
        return stored

    def get_heartbeat(self, job_id: str) -> AgentRunHeartbeat | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cloyd_smith_run_heartbeats WHERE job_id = ?", (job_id,)).fetchone()
        return _heartbeat_from_row(row) if row else None

    def heartbeat_is_stale(self, heartbeat: AgentRunHeartbeat, *, now: datetime | None = None) -> bool:
        checked_at = now or datetime.now(UTC)
        return (checked_at - heartbeat.updated_at).total_seconds() > heartbeat.stale_after_seconds

    def mark_stale_runs(self, *, now: datetime | None = None) -> list[AgentRunHeartbeat]:
        stale: list[AgentRunHeartbeat] = []
        for job in self.list_active():
            heartbeat = self.get_heartbeat(job.job_id)
            if not heartbeat or job.status != CloydSmithJobStatus.RUNNING:
                continue
            if not self.heartbeat_is_stale(heartbeat, now=now):
                continue
            updated = heartbeat.model_copy(
                update={
                    "state": CloydSmithJobStatus.STALE.value,
                    "phase": "stale",
                    "last_action": "operator_review",
                    "last_error": f"No meaningful progress for {heartbeat.stale_after_seconds} seconds",
                    "updated_at": now or datetime.now(UTC),
                    "stop_reason": "stale_timeout",
                }
            )
            self.record_heartbeat(updated)
            self.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.STALE,
                    next_action="inspect_opencode_output_or_restart",
                    error=updated.last_error,
                    last_evidence={"heartbeat": heartbeat_summary(updated, now=now)},
                ),
            )
            self.add_event(job.job_id, "run_stale", {"heartbeat": heartbeat_summary(updated, now=now)})
            stale.append(updated)
        return stale

    def status_rows(self, *, active_limit: int = 50, recent_limit: int = 10, now: datetime | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for job in [*self.list_active(limit=active_limit), *self.list_recent_terminal(limit=recent_limit)]:
            heartbeat = self.get_heartbeat(job.job_id)
            rows.append(job_status_summary(job, heartbeat=heartbeat, now=now))
        return rows

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cloyd_smith_run_heartbeats (
                    job_id TEXT PRIMARY KEY,
                    agent TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    session_id TEXT,
                    state TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    last_action TEXT NOT NULL,
                    last_message TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    working_directory TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    stale_after_seconds INTEGER NOT NULL DEFAULT 300,
                    stop_reason TEXT,
                    FOREIGN KEY(job_id) REFERENCES cloyd_smith_jobs(job_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cloyd_smith_jobs_status ON cloyd_smith_jobs(status, updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cloyd_smith_job_events_job ON cloyd_smith_job_events(job_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cloyd_smith_run_heartbeats_state ON cloyd_smith_run_heartbeats(state, updated_at)")

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


def _heartbeat_values(heartbeat: AgentRunHeartbeat) -> tuple[object, ...]:
    return (
        heartbeat.job_id,
        heartbeat.agent,
        heartbeat.alias,
        heartbeat.session_id,
        heartbeat.state,
        heartbeat.phase,
        heartbeat.last_action,
        heartbeat.last_message,
        heartbeat.last_error,
        heartbeat.working_directory,
        _iso(heartbeat.started_at or heartbeat.updated_at),
        _iso(heartbeat.updated_at),
        heartbeat.stale_after_seconds,
        heartbeat.stop_reason,
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


def _heartbeat_from_row(row: sqlite3.Row) -> AgentRunHeartbeat:
    return AgentRunHeartbeat(
        job_id=row["job_id"],
        agent=row["agent"],
        alias=row["alias"],
        session_id=row["session_id"],
        state=row["state"],
        phase=row["phase"],
        last_action=row["last_action"],
        last_message=row["last_message"],
        last_error=row["last_error"],
        working_directory=row["working_directory"],
        started_at=_dt(row["started_at"]),
        updated_at=_dt(row["updated_at"]),
        stale_after_seconds=row["stale_after_seconds"],
        stop_reason=row["stop_reason"],
    )


def heartbeat_summary(heartbeat: AgentRunHeartbeat, *, now: datetime | None = None) -> dict[str, Any]:
    checked_at = now or datetime.now(UTC)
    elapsed = int((checked_at - (heartbeat.started_at or heartbeat.updated_at)).total_seconds())
    age = int((checked_at - heartbeat.updated_at).total_seconds())
    stale = heartbeat.state == CloydSmithJobStatus.RUNNING.value and age > heartbeat.stale_after_seconds
    return {
        "job_id": heartbeat.job_id,
        "agent": heartbeat.agent,
        "alias": heartbeat.alias,
        "session_id": heartbeat.session_id,
        "state": "stale" if stale and heartbeat.state == "running" else heartbeat.state,
        "phase": heartbeat.phase,
        "last_action": heartbeat.last_action,
        "last_message": heartbeat.last_message,
        "last_error": heartbeat.last_error,
        "working_directory": heartbeat.working_directory,
        "updated_at": heartbeat.updated_at.isoformat(),
        "elapsed_seconds": max(elapsed, 0),
        "heartbeat_age_seconds": max(age, 0),
        "stale_after_seconds": heartbeat.stale_after_seconds,
        "is_stale": stale,
        "stop_reason": heartbeat.stop_reason,
    }


def expected_smith_alias(job: CloydSmithJob) -> str | None:
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    explicit_alias = metadata.get("alias")
    if isinstance(explicit_alias, str) and explicit_alias.strip() in {"atlas-dashboard", "freyja-code"}:
        return explicit_alias.strip()
    haystack = "\n".join(
        str(item or "")
        for item in (
            job.objective,
            job.current_prompt,
            metadata.get("source_directory"),
            metadata.get("url"),
            metadata.get("repository"),
        )
    ).lower()
    if "/home/joe/cloyd-services" in haystack or "atlas dashboard" in haystack or "atlas.tail" in haystack:
        return "atlas-dashboard"
    return None


def job_status_summary(
    job: CloydSmithJob,
    *,
    heartbeat: AgentRunHeartbeat | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    hb = heartbeat_summary(heartbeat, now=now) if heartbeat else None
    state = hb["state"] if hb else job.status.value
    last_action = hb["last_action"] if hb else (job.next_action or "")
    last_message = hb["last_message"] if hb else ""
    error = (hb["last_error"] if hb else "") or job.error
    elapsed_seconds = hb["elapsed_seconds"] if hb else int(((now or datetime.now(UTC)) - job.created_at).total_seconds())
    next_action = job.next_action or "inspect_recent_events"
    if state == "stale":
        next_action = "inspect OpenCode output, then restart or stop the job"
    elif job.status == CloydSmithJobStatus.QUEUED:
        next_action = (
            "ensure the local cloyd-smith loop daemon is running"
            if elapsed_seconds > 60
            else (job.next_action or "waiting for daemon pickup")
        )
    elif job.status == CloydSmithJobStatus.NEEDS_REVIEW:
        next_action = job.next_action or "review Smith evidence and mark done or queue follow-up"
        if "INFERENCE_QUEUE_TIMEOUT" in last_message:
            next_action = "do not mark done; evidence is timeout-only, so send one bounded follow-up or mark blocked"
    elif job.status in {CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.STOPPED}:
        next_action = job.next_action or "operator review required"
        if job.status == CloydSmithJobStatus.BLOCKED and job.next_action == "blocked_pending_new_prompt_or_runtime_fix":
            next_action = "draft a sharper replacement job with verifiable acceptance criteria, or leave blocked with this reason visible"
        if job.status == CloydSmithJobStatus.BLOCKED and job.next_action == "inspect_or_queue_suggested_replacement_after_busy_timeout":
            next_action = "Smith busy timeout stopped the runtime; inspect evidence before retrying or queue a smaller replacement"
        if (
            job.status == CloydSmithJobStatus.BLOCKED
            and "timed out" in (error or "").lower()
            and job.next_action != "inspect_or_stop_opencode_session_before_retry"
            and job.next_action != "blocked_pending_new_prompt_or_runtime_fix"
            and job.next_action != "inspect_or_queue_suggested_replacement_after_busy_timeout"
        ):
            next_action = "OpenCode health is separate; if healthy, use one bounded Retry, otherwise inspect runtime logs"
    retry = job.metadata.get("retry") if isinstance(job.metadata, dict) else {}
    retry_attempts = retry.get("attempts", 0) if isinstance(retry, dict) else 0
    follow_up = job.metadata.get("follow_up") if isinstance(job.metadata, dict) else {}
    follow_up_attempts = follow_up.get("attempts", 0) if isinstance(follow_up, dict) else 0
    runtime_reset = job.metadata.get("runtime_reset") if isinstance(job.metadata, dict) else {}
    runtime_reset_attempts = runtime_reset.get("attempts", 0) if isinstance(runtime_reset, dict) else 0
    expected_alias = expected_smith_alias(job)
    alias_mismatch = bool(expected_alias and expected_alias != job.smith_alias)
    if retry_attempts >= 3:
        next_action = "retry limit reached; inspect error/output and change prompt or runtime before requeueing"
    if follow_up_attempts >= 1 and job.status in {CloydSmithJobStatus.NEEDS_REVIEW, CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.STALE}:
        next_action = "bounded follow-up already used; mark done only with evidence or mark blocked with reason"
    if alias_mismatch and job.status not in {CloydSmithJobStatus.DONE, CloydSmithJobStatus.STOPPED}:
        next_action = f"wrong Smith alias for target; reroute or create a new job with smith_alias={expected_alias}"
    suggested_prompt = ""
    replacement_prompt = ""
    replacement_depth = replacement_chain_depth(job.metadata)
    repeated_busy_timeout = (
        job.status == CloydSmithJobStatus.BLOCKED
        and job.next_action == "inspect_or_queue_suggested_replacement_after_busy_timeout"
        and replacement_depth >= 2
    )
    if repeated_busy_timeout:
        next_action = "repeated Smith busy timeouts; inspect or reset OpenCode runtime before queueing more replacements"
    if repeated_busy_timeout and runtime_reset_attempts >= 1:
        next_action = "runtime reset completed; use one bounded Retry only if the prompt is still worth running"
    if next_action == "draft a sharper replacement job with verifiable acceptance criteria, or leave blocked with this reason visible":
        suggested_prompt = replacement_job_prompt(job, heartbeat=heartbeat, error=error)
        replacement_prompt = bounded_replacement_prompt(job, heartbeat=heartbeat, error=error)
    elif next_action == "Smith busy timeout stopped the runtime; inspect evidence before retrying or queue a smaller replacement" and not repeated_busy_timeout:
        suggested_prompt = replacement_job_prompt(job, heartbeat=heartbeat, error=error)
        replacement_prompt = bounded_replacement_prompt(job, heartbeat=heartbeat, error=error, mode="smaller_after_busy_timeout")
    return {
        "job_id": job.job_id,
        "agent": heartbeat.agent if heartbeat else "smith",
        "alias": heartbeat.alias if heartbeat else job.smith_alias,
        "state": state,
        "job_status": job.status.value,
        "phase": hb["phase"] if hb else job.status.value,
        "last_action": last_action,
        "last_message": last_message,
        "last_error": error,
        "working_directory": hb["working_directory"] if hb else "",
        "updated_at": (heartbeat.updated_at if heartbeat else job.updated_at).isoformat(),
        "elapsed_seconds": elapsed_seconds,
        "stale_after_seconds": hb["stale_after_seconds"] if hb else None,
        "is_stale": bool(hb and hb["is_stale"]),
        "stop_reason": hb["stop_reason"] if hb else None,
        "objective": job.objective,
        "metadata": job.metadata,
        "retry_attempts": retry_attempts,
        "follow_up_attempts": follow_up_attempts,
        "runtime_reset_attempts": runtime_reset_attempts,
        "expected_alias": expected_alias,
        "alias_mismatch": alias_mismatch,
        "next_action": next_action,
        "suggested_prompt": suggested_prompt,
        "replacement_prompt": replacement_prompt,
    }


def loop_status_payload(store: CloydSmithJobStore | None = None) -> dict[str, Any]:
    """Return the canonical operator status for the Cloyd-Smith loop."""
    store = store or CloydSmithJobStore()
    store.mark_stale_runs()
    all_runs = store.status_rows(active_limit=50, recent_limit=10)
    hidden_terminal_count = sum(1 for run in all_runs if agent_run_is_hidden_terminal(run))
    runs = [run for run in all_runs if not agent_run_is_hidden_terminal(run)]
    supervisor = read_supervisor_heartbeat(store.database_path)
    visible_statuses = [_visible_run_status(run) for run in runs]
    queue = {
        "queued": sum(1 for status in visible_statuses if status == "queued"),
        "running": sum(1 for status in visible_statuses if status == "running"),
        "needs_review": sum(1 for status in visible_statuses if status == "needs_review"),
        "blocked": sum(1 for status in visible_statuses if status == "blocked"),
        "stale": sum(1 for run, status in zip(runs, visible_statuses) if status == "stale" or run.get("is_stale")),
        "done": sum(1 for status in visible_statuses if status == "done"),
        "stopped": sum(1 for status in visible_statuses if status == "stopped"),
    }
    active_count = queue["queued"] + queue["running"] + queue["needs_review"] + queue["stale"]
    attention_count = queue["needs_review"] + queue["blocked"] + queue["stale"]
    terminal_count = queue["done"] + queue["blocked"] + queue["stopped"]
    cycle = simple_loop_cycle(queue, supervisor=supervisor)
    return {
        "ok": True,
        "canonical_ledger": str(store.database_path),
        "supervisor": supervisor,
        "cycle": cycle,
        "active_count": active_count,
        "attention_count": attention_count,
        "terminal_count": terminal_count,
        "hidden_terminal_count": hidden_terminal_count,
        "queue": queue,
        "diagnostics": agent_runs_diagnostics(runs, supervisor=supervisor),
        "runs": runs,
    }


def simple_loop_cycle(queue: dict[str, int], *, supervisor: dict[str, Any] | None = None) -> dict[str, Any]:
    model = ["check_for_work", "do_bounded_work", "finish_or_block", "report_result", "repeat"]
    if supervisor and not supervisor.get("ok"):
        current_step = "report_result"
        summary = "Supervisor heartbeat is not healthy; report that the loop cannot be trusted until it is restarted or inspected."
    elif int(queue.get("blocked") or 0) or int(queue.get("stale") or 0) or int(queue.get("needs_review") or 0):
        current_step = "report_result"
        summary = "Work reached a review, stale, or blocked outcome; report it clearly before doing more."
    elif int(queue.get("running") or 0):
        current_step = "do_bounded_work"
        summary = "Smith/OpenCode is working a bounded unit; the supervisor will poll, harvest output, or stop it on timeout."
    elif int(queue.get("queued") or 0):
        current_step = "check_for_work"
        summary = "Queued work is waiting; the next supervisor tick should pick up one bounded unit."
    else:
        current_step = "check_for_work"
        summary = "No queued or active work; the supervisor should keep checking quietly."
    return {
        "model": model,
        "current_step": current_step,
        "summary": summary,
        "independent": bool(supervisor and supervisor.get("ok")),
    }


def enrich_loop_status_with_runtime(payload: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    """Attach OpenCode runtime health and flag work not represented in the ledger."""
    enriched = dict(payload)
    diagnostics = list(enriched.get("diagnostics") or [])
    enriched["runtime"] = runtime
    queue = enriched.get("queue") if isinstance(enriched.get("queue"), dict) else {}
    running_jobs = int(queue.get("running") or 0)
    runtime_active = int(runtime.get("session_count") or 0) if runtime.get("ok") else 0
    if not runtime.get("ok"):
        diagnostics.insert(
            0,
            {
                "level": "blocked",
                "title": "OpenCode runtime unhealthy",
                "detail": f"OpenCode health check failed: {runtime.get('error') or runtime}. The loop can queue work, but Smith cannot execute until runtime is healthy.",
            },
        )
    elif runtime_active > running_jobs:
        cycle = dict(enriched.get("cycle") or {})
        cycle["current_step"] = "report_result"
        cycle["summary"] = "OpenCode is busy outside the durable ledger; report the exception before trusting the quiet queue."
        cycle["runtime_exception"] = "opencode_busy_outside_ledger"
        enriched["cycle"] = cycle
        diagnostics.insert(
            0,
            {
                "level": "review",
                "title": "OpenCode busy outside ledger",
                "detail": f"OpenCode reports {runtime_active} active session(s), but the Cloyd-Smith ledger has {running_jobs} running job(s). Inspect or stop the orphan session, or requeue the work through the durable loop.",
            },
        )
    elif running_jobs > 0 and runtime_active == 0:
        diagnostics.insert(
            0,
            {
                "level": "review",
                "title": "Ledger running but runtime idle",
                "detail": "The ledger has running job(s), but OpenCode reports no active session. The supervisor should harvest output or mark the job for review on its next pass.",
            },
        )
    enriched["diagnostics"] = diagnostics
    return enriched


def _visible_run_status(run: dict[str, Any]) -> str:
    state = str(run.get("state") or "")
    if state in {"running", "needs_review", "blocked", "stale", "done", "stopped", "queued"}:
        return state
    return str(run["job_status"])


def agent_run_is_hidden_terminal(run: dict[str, Any]) -> bool:
    if run.get("job_status") != "stopped":
        return False
    if run.get("phase") == "cleared" or run.get("stop_reason") == "cleared_from_monitor":
        return True
    if run.get("phase") == "superseded" or run.get("stop_reason") == "superseded":
        return True
    return str(run.get("next_action") or "").startswith("superseded_by:")


def agent_runs_diagnostics(runs: list[dict[str, Any]], *, supervisor: dict[str, Any] | None = None) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    if supervisor and not supervisor.get("ok"):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Supervisor heartbeat stale",
                "detail": f"Cloyd-Smith loop heartbeat is {supervisor.get('status')}; restart or inspect the LaunchAgent before trusting idle queue state.",
            }
        )
    alias_mismatches = [
        run
        for run in runs
        if run.get("alias_mismatch") and run.get("job_status") not in {"done", "stopped"}
    ]
    if alias_mismatches:
        expected = ", ".join(f"{run.get('job_id')} -> {run.get('expected_alias')}" for run in alias_mismatches[:3])
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Wrong Smith alias",
                "detail": f"Jobs are assigned to the wrong worker for their target: {expected}. Reroute or create a new job with the expected alias before retrying.",
            }
        )
    retrying = [
        run
        for run in runs
        if int(run.get("retry_attempts") or 0) >= 2 and run.get("job_status") not in {"done", "stopped"}
    ]
    if retrying:
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Retry attempts accumulating",
                "detail": "One or more jobs have been retried at least twice. Stop blind retries; inspect the OpenCode error/output and tighten the next prompt or runtime before trying again.",
            }
        )
    followed_up = [run for run in runs if int(run.get("follow_up_attempts") or 0) >= 1 and run.get("job_status") in {"needs_review", "blocked", "stale"}]
    if followed_up:
        diagnostics.append(
            {
                "level": "review",
                "title": "Follow-up already used",
                "detail": "One or more jobs already consumed their bounded follow-up. Mark done only with evidence, otherwise mark blocked with a concrete reason.",
            }
        )
    if any(run["job_status"] == "blocked" and run.get("phase") == "send_failed" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "OpenCode send failed",
                "detail": "At least one job could not be handed to Smith. Use Retry after confirming the OpenCode runtime is healthy, or leave it blocked with the error visible.",
            }
        )
    if any(run["job_status"] == "blocked" and run.get("phase") == "smith_busy_timeout" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Smith busy timeout",
                "detail": "A bounded Smith job stayed busy past the max window and the loop stopped the OpenCode runtime. Inspect the visible error before retrying or queueing a smaller replacement.",
            }
        )
    if any("repeated Smith busy timeouts" in str(run.get("next_action") or "") and int(run.get("runtime_reset_attempts") or 0) == 0 for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "OpenCode runtime inspection needed",
                "detail": "Repeated smaller replacements are timing out before producing output. Stop queueing replacements and inspect or reset the OpenCode runtime/session.",
            }
        )
    if any(int(run.get("runtime_reset_attempts") or 0) >= 1 and run.get("job_status") == "blocked" for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Runtime reset completed",
                "detail": "OpenCode was reset after busy timeouts. A single bounded Retry is available if the job is still worth running; otherwise leave it blocked with the visible reason.",
            }
        )
    if any("INFERENCE_QUEUE_TIMEOUT" in str(run.get("last_message") or "") for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Inference queue timeout evidence",
                "detail": "Review jobs include timeout evidence. Do not mark them done unless the output also proves the requested objective, diff, and verification.",
            }
        )
    if any(run["job_status"] == "blocked" and run.get("next_action") == "draft a sharper replacement job with verifiable acceptance criteria, or leave blocked with this reason visible" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Sharper replacement needed",
                "detail": "A blocked job has insufficient evidence for its broad objective. Do not retry blindly; draft a smaller replacement with explicit files, expected evidence, and verification steps.",
            }
        )
    if any(run["job_status"] == "needs_review" for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Human or Cloyd review required",
                "detail": "Needs-review jobs are idle and waiting for evidence review. Mark Done only after evidence matches the objective; otherwise send one bounded follow-up or mark blocked.",
            }
        )
    if any(run["job_status"] == "blocked" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Blocked jobs need review",
                "detail": "At least one job is blocked without an automatic queue-clearing action. Inspect the reason, then create a sharper replacement job or leave it blocked with the reason visible.",
            }
        )
    if not diagnostics and any(run["job_status"] in {"queued", "running"} for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Work in progress",
                "detail": "A job is queued or running. Wait for output_ready, needs_review, blocked, or stale before taking a queue-clearing action.",
            }
        )
    if not diagnostics:
        diagnostics.append(
            {
                "level": "ok",
                "title": "Loop quiet",
                "detail": "No blocked, stale, or review jobs are visible in the canonical ledger.",
            }
        )
    return diagnostics


def replacement_chain_depth(metadata: dict[str, Any] | None) -> int:
    depth = 0
    current: Any = metadata
    while isinstance(current, dict):
        if current.get("source") in {"agent-runs-suggested-replacement", "cloyd_smith_replace", "agent-runs-replacement"}:
            depth += 1
        current = current.get("parent_metadata")
    return depth


def replacement_job_prompt(
    job: CloydSmithJob,
    *,
    heartbeat: AgentRunHeartbeat | None = None,
    error: str | None = None,
) -> str:
    metadata = json.dumps(job.metadata or {}, sort_keys=True)
    working_directory = heartbeat.working_directory if heartbeat else ""
    return "\n".join(
        [
            "Cloyd, use the canonical Agent Runs monitor as source of truth and do not start a fresh OpenCode session just to inspect this old job.",
            "This job is blocked because its evidence is too weak or timeout-only for the original broad objective.",
            f"blocked_job_id: {job.job_id}",
            f"blocked_objective: {job.objective}",
            f"blocked_reason: {error or job.error or ''}",
            f"working_directory: {working_directory}",
            f"metadata: {metadata}",
            "Use http://100.115.228.56:8000/agent-runs/api/status as the source of truth.",
            "Draft a smaller replacement job that can clear the queue without blind retrying.",
            "The replacement must include:",
            "- exact target files or service URL",
            "- at most one small reversible change or one read-only inspection",
            "- expected evidence: diff or explicit no-change reason",
            "- verification steps and served-page/test evidence",
            "- the Smith/OpenCode alias to use if known",
            "Tell me the replacement prompt to submit, or say this should remain blocked and why.",
        ]
    )


def bounded_replacement_prompt(
    job: CloydSmithJob,
    *,
    heartbeat: AgentRunHeartbeat | None = None,
    error: str | None = None,
    mode: str = "default",
) -> str:
    metadata = json.dumps(job.metadata or {}, sort_keys=True)
    working_directory = heartbeat.working_directory if heartbeat else ""
    lines = [
            "Smith, this is a bounded replacement for a blocked Cloyd-Smith job. Do not retry the old session and do not broaden the task.",
            f"blocked_job_id: {job.job_id}",
            f"blocked_objective: {job.objective}",
            f"blocked_reason: {error or job.error or ''}",
            f"working_directory: {working_directory}",
            f"metadata: {metadata}",
            "Task:",
    ]
    if mode == "smaller_after_busy_timeout":
        lines.extend(
            [
                "- The previous bounded job hit a Smith busy timeout. Make this replacement smaller than the timed-out job.",
                "- Perform only one read-only check against the most specific file or URL named in the blocked reason.",
                "- Do not run broad searches, dependency installs, dev servers, or multi-file inspections.",
            ]
        )
    lines.extend(
        [
            "- Perform one read-only inventory of the exact files, service URL, or narrow surface named above.",
            "- If the blocked reason names files, inspect only those files unless one adjacent route/module file is required to understand them.",
            "- Use .venv/bin/python or python3 for Python checks; do not call bare python.",
            "- Do not edit files, start broad implementation work, or create a new unrelated session.",
            "Acceptance criteria:",
            "- Report the files or URL inspected.",
            "- State whether any existing change is present.",
            "- Name the smallest safe next task, or say no action is needed.",
            "- Include verification evidence or the exact reason verification was not possible.",
        ]
    )
    return "\n".join(lines)


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
