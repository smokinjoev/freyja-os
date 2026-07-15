"""Persistent SQLite-backed approval store for Agent Smith write-pilot actions."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from freyja.config import settings

from .models import ApprovalRecord, ApprovalRecordStatus, ApprovalStoreError

logger = logging.getLogger(__name__)


class SmithApprovalStore:
    """SQLite store for Agent Smith write-pilot approvals.

    The store is intentionally conservative: it records *hashes* of proposed
    content and commit messages, never the secrets, full payloads, or raw
    environment values.  Approvals are request-specific, action-specific,
    path-specific, and single-use.  Changing any guarded field invalidates the
    match.
    """

    _TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_path TEXT NOT NULL,
            content_hash TEXT,
            commit_message_hash TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT,
            denial_reason TEXT,
            consumed_at TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            UNIQUE(request_id, action)
        );

        CREATE INDEX IF NOT EXISTS idx_approvals_request_id
            ON approvals(request_id);
        CREATE INDEX IF NOT EXISTS idx_approvals_status
            ON approvals(status);
        CREATE INDEX IF NOT EXISTS idx_approvals_expires_at
            ON approvals(expires_at);
    """

    def __init__(self, database_path: str | None = None) -> None:
        self._database_path = (
            database_path
            if database_path is not None
            else getattr(settings, "agent_smith_approval_db_path", "/Users/freyja/freyja-os/data/smith-approvals.sqlite3")
        )
        self._initialized = False

    @property
    def database_path(self) -> str:
        return self._database_path

    def _ensure_parent_dir(self) -> None:
        parent = Path(self._database_path).parent
        if parent:
            parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent, 0o700)
            except (OSError, PermissionError):
                logger.warning("Could not restrict approval database parent directory permissions to 0o700")

    def _connect(self) -> sqlite3.Connection:
        self._ensure_parent_dir()
        conn = sqlite3.connect(self._database_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self, *, force: bool = False) -> None:
        if self._initialized and not force:
            return
        conn = self._connect()
        try:
            conn.executescript(self._TABLE_SQL)
            conn.commit()
            self._restrict_permissions()
            self._initialized = True
        finally:
            conn.close()

    def _restrict_permissions(self) -> None:
        try:
            os.chmod(self._database_path, 0o600)
        except (OSError, PermissionError):
            logger.warning("Could not restrict approval database permissions to 0o600")

    def create(
        self,
        *,
        request_id: str,
        action: str,
        target_path: str,
        content_hash: str | None = None,
        commit_message_hash: str | None = None,
        summary: str = "",
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        self.initialize()
        ttl = ttl_seconds or getattr(settings, "agent_smith_approval_ttl_seconds", 900)
        now = datetime.now(timezone.utc)
        expires_at = now.replace(second=0, microsecond=0) if ttl == 0 else now + timedelta(seconds=ttl)
        record = ApprovalRecord(
            id=self._generate_id(),
            request_id=request_id,
            action=action,
            target_path=target_path,
            content_hash=content_hash,
            commit_message_hash=commit_message_hash,
            status=ApprovalRecordStatus.PENDING,
            summary=summary,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO approvals (
                    id, request_id, action, target_path, content_hash,
                    commit_message_hash, status, summary, created_at, expires_at,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.request_id,
                    record.action,
                    record.target_path,
                    record.content_hash,
                    record.commit_message_hash,
                    record.status.value,
                    record.summary,
                    record.created_at.isoformat(),
                    record.expires_at.isoformat(),
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()
            return record
        except sqlite3.IntegrityError as exc:
            raise ApprovalStoreError(
                f"Approval already exists for request_id={request_id} action={action}"
            ) from exc
        finally:
            conn.close()

    def get(self, approval_id: str) -> ApprovalRecord | None:
        self.initialize()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def _list_by_request(self, request_id: str) -> list[ApprovalRecord]:
        self.initialize()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE request_id = ? ORDER BY created_at ASC",
                (request_id,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]
        finally:
            conn.close()

    def list_pending(self) -> list[ApprovalRecord]:
        self.initialize()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
                (ApprovalRecordStatus.PENDING.value,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]
        finally:
            conn.close()

    def approve(self, approval_id: str, *, actor: str = "operator") -> ApprovalRecord:
        self.initialize()
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                if row is None:
                    raise ApprovalStoreError(f"Unknown approval: {approval_id}", status_code=404)
                record = self._row_to_record(row)
                if record.status == ApprovalRecordStatus.PENDING:
                    if now > record.expires_at:
                        conn.execute(
                            "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                            (ApprovalRecordStatus.EXPIRED.value, now.isoformat(), approval_id),
                        )
                        raise ApprovalStoreError(
                            f"Approval {approval_id} has expired", status_code=410
                        )
                    conn.execute(
                        """
                        UPDATE approvals
                        SET status = ?, resolved_at = ?, resolved_by = ?
                        WHERE id = ? AND status = ?
                        """,
                        (
                            ApprovalRecordStatus.APPROVED.value,
                            now.isoformat(),
                            actor,
                            approval_id,
                            ApprovalRecordStatus.PENDING.value,
                        ),
                    )
                    if conn.total_changes == 0:
                        raise ApprovalStoreError(
                            f"Approval {approval_id} was resolved by another request",
                            status_code=409,
                        )
                else:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} is already {record.status.value}",
                        status_code=409,
                    )
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                return self._row_to_record(row)
        finally:
            conn.close()

    def deny(
        self,
        approval_id: str,
        *,
        actor: str = "operator",
        reason: str | None = None,
    ) -> ApprovalRecord:
        self.initialize()
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                if row is None:
                    raise ApprovalStoreError(f"Unknown approval: {approval_id}", status_code=404)
                record = self._row_to_record(row)
                if record.status != ApprovalRecordStatus.PENDING:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} is already {record.status.value}",
                        status_code=409,
                    )
                conn.execute(
                    """
                    UPDATE approvals
                    SET status = ?, resolved_at = ?, resolved_by = ?, denial_reason = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        ApprovalRecordStatus.DENIED.value,
                        now.isoformat(),
                        actor,
                        reason or "",
                        approval_id,
                        ApprovalRecordStatus.PENDING.value,
                    ),
                )
                if conn.total_changes == 0:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} was resolved by another request",
                        status_code=409,
                    )
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                return self._row_to_record(row)
        finally:
            conn.close()

    def consume(
        self,
        approval_id: str,
        *,
        request_id: str,
        action: str,
        target_path: str,
        content_hash: str | None = None,
        commit_message_hash: str | None = None,
        actor: str = "agent_smith",
    ) -> ApprovalRecord:
        """Consume an approved approval exactly once.

        All guarded fields must match; changing any of them invalidates the
        approval and raises a 409 conflict.
        """
        self.initialize()
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                if row is None:
                    raise ApprovalStoreError(f"Unknown approval: {approval_id}", status_code=404)
                record = self._row_to_record(row)
                if record.status == ApprovalRecordStatus.PENDING:
                    if now > record.expires_at:
                        conn.execute(
                            "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                            (ApprovalRecordStatus.EXPIRED.value, now.isoformat(), approval_id),
                        )
                        raise ApprovalStoreError(
                            f"Approval {approval_id} has expired", status_code=410
                        )
                    raise ApprovalStoreError(
                        f"Approval {approval_id} is still pending", status_code=409
                    )
                if record.status != ApprovalRecordStatus.APPROVED:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} is already {record.status.value}",
                        status_code=409,
                    )
                if not secrets.compare_digest(record.request_id, request_id):
                    raise ApprovalStoreError(
                        "Approval request_id mismatch", status_code=409
                    )
                if not secrets.compare_digest(record.action, action):
                    raise ApprovalStoreError(
                        "Approval action mismatch", status_code=409
                    )
                if not secrets.compare_digest(record.target_path, target_path):
                    raise ApprovalStoreError(
                        "Approval target_path mismatch", status_code=409
                    )
                if content_hash is not None and record.content_hash is not None:
                    if not secrets.compare_digest(record.content_hash, content_hash):
                        raise ApprovalStoreError(
                            "Approval content_hash mismatch", status_code=409
                        )
                if commit_message_hash is not None and record.commit_message_hash is not None:
                    if not secrets.compare_digest(record.commit_message_hash, commit_message_hash):
                        raise ApprovalStoreError(
                            "Approval commit_message_hash mismatch", status_code=409
                        )
                conn.execute(
                    """
                    UPDATE approvals
                    SET status = ?, consumed_at = ?, resolved_by = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        ApprovalRecordStatus.CONSUMED.value,
                        now.isoformat(),
                        actor,
                        approval_id,
                        ApprovalRecordStatus.APPROVED.value,
                    ),
                )
                if conn.total_changes == 0:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} was consumed by another request",
                        status_code=409,
                    )
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                return self._row_to_record(row)
        finally:
            conn.close()

    def cancel(self, approval_id: str, *, actor: str = "operator") -> ApprovalRecord:
        self.initialize()
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                if row is None:
                    raise ApprovalStoreError(f"Unknown approval: {approval_id}", status_code=404)
                record = self._row_to_record(row)
                if record.status != ApprovalRecordStatus.PENDING:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} is already {record.status.value}",
                        status_code=409,
                    )
                conn.execute(
                    """
                    UPDATE approvals
                    SET status = ?, resolved_at = ?, resolved_by = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        ApprovalRecordStatus.CANCELLED.value,
                        now.isoformat(),
                        actor,
                        approval_id,
                        ApprovalRecordStatus.PENDING.value,
                    ),
                )
                if conn.total_changes == 0:
                    raise ApprovalStoreError(
                        f"Approval {approval_id} was resolved by another request",
                        status_code=409,
                    )
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                return self._row_to_record(row)
        finally:
            conn.close()

    def cleanup_expired(self) -> int:
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE approvals
                    SET status = ?
                    WHERE status = ? AND expires_at < ?
                    """,
                    (
                        ApprovalRecordStatus.EXPIRED.value,
                        ApprovalRecordStatus.PENDING.value,
                        now,
                    ),
                )
                return cursor.rowcount
        finally:
            conn.close()

    def _generate_id(self) -> str:
        return secrets.token_urlsafe(24)

    def _row_to_record(self, row: sqlite3.Row) -> ApprovalRecord:
        metadata: dict[str, Any] = {}
        raw_metadata = row["metadata"]
        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}
        return ApprovalRecord(
            id=row["id"],
            request_id=row["request_id"],
            action=row["action"],
            target_path=row["target_path"],
            content_hash=row["content_hash"],
            commit_message_hash=row["commit_message_hash"],
            status=ApprovalRecordStatus(row["status"]),
            summary=row["summary"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolved_by=row["resolved_by"],
            denial_reason=row["denial_reason"],
            consumed_at=datetime.fromisoformat(row["consumed_at"]) if row["consumed_at"] else None,
            metadata=metadata,
        )
