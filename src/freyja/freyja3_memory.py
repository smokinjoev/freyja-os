from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freyja.config import settings
from freyja.foundation_models import MemoryClassification, MemoryScope, SecurityDomainId


class Freyja3MemoryAccessError(PermissionError):
    pass


class Freyja3MemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_domain_id: SecurityDomainId
    scope: MemoryScope
    source_agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification: MemoryClassification = MemoryClassification.PRIVATE
    allowed_reader_domain_ids: frozenset[SecurityDomainId] = Field(default_factory=frozenset)
    allowed_writer_domain_ids: frozenset[SecurityDomainId] = Field(default_factory=frozenset)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None


class Freyja3MemoryWrite(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_domain_id: SecurityDomainId
    scope: MemoryScope
    source_agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification: MemoryClassification = MemoryClassification.PRIVATE
    allowed_reader_domain_ids: frozenset[SecurityDomainId] = Field(default_factory=frozenset)
    allowed_writer_domain_ids: frozenset[SecurityDomainId] = Field(default_factory=frozenset)
    metadata: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class Freyja3MemoryQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_domain_id: SecurityDomainId | None = None
    scope: MemoryScope | None = None
    source_agent_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class Freyja3MemoryStore:
    """Freyja 3 scoped memory with explicit trust boundaries."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.freyja3_memory_database_path).expanduser()
        if not self.database_path.is_absolute():
            self.database_path = Path.cwd() / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def put(self, write: Freyja3MemoryWrite, *, writer_domain_id: SecurityDomainId) -> Freyja3MemoryRecord:
        self._assert_write_allowed(write, writer_domain_id)
        now = datetime.now(timezone.utc)
        readers = frozenset({write.owner_domain_id, *write.allowed_reader_domain_ids})
        writers = frozenset({write.owner_domain_id, *write.allowed_writer_domain_ids})
        record = Freyja3MemoryRecord(
            owner_domain_id=write.owner_domain_id,
            scope=write.scope,
            source_agent_id=write.source_agent_id,
            content=write.content,
            provenance=write.provenance,
            confidence=write.confidence,
            classification=write.classification,
            allowed_reader_domain_ids=readers,
            allowed_writer_domain_ids=writers,
            metadata=write.metadata,
            created_at=now,
            updated_at=now,
            expires_at=write.expires_at,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO freyja3_memories (
                    memory_id, owner_domain_id, scope, source_agent_id, content,
                    provenance, confidence, classification, allowed_readers_json,
                    allowed_writers_json, metadata_json, created_at, updated_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, json(?), json(?), json(?), ?, ?, ?)
                """,
                _record_row(record),
            )
        return record

    def list(self, query: Freyja3MemoryQuery | None = None, *, reader_domain_id: SecurityDomainId) -> list[Freyja3MemoryRecord]:
        query = query or Freyja3MemoryQuery()
        clauses = ["(expires_at IS NULL OR expires_at > ?)"]
        params: list[Any] = [datetime.now(timezone.utc).isoformat()]
        if query.owner_domain_id is not None:
            clauses.append("owner_domain_id = ?")
            params.append(query.owner_domain_id.value)
        if query.scope is not None:
            clauses.append("scope = ?")
            params.append(query.scope.value)
        if query.source_agent_id is not None:
            clauses.append("source_agent_id = ?")
            params.append(query.source_agent_id)
        params.append(query.limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM freyja3_memories
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC, memory_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        records = [_row_to_record(row) for row in rows]
        return [record for record in records if _can_read(record, reader_domain_id)]

    def get(self, memory_id: str, *, reader_domain_id: SecurityDomainId) -> Freyja3MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM freyja3_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            return None
        record = _row_to_record(row)
        if not _can_read(record, reader_domain_id):
            raise Freyja3MemoryAccessError("memory read denied")
        return record

    def _assert_write_allowed(self, write: Freyja3MemoryWrite, writer_domain_id: SecurityDomainId) -> None:
        if write.owner_domain_id == SecurityDomainId.PARALEGAL and writer_domain_id != SecurityDomainId.PARALEGAL:
            raise Freyja3MemoryAccessError("paralegal memory is outside Freyja trust")
        if writer_domain_id == SecurityDomainId.PARALEGAL and write.owner_domain_id != SecurityDomainId.PARALEGAL:
            raise Freyja3MemoryAccessError("paralegal enclave cannot write Freyja memory")
        if writer_domain_id == write.owner_domain_id or writer_domain_id in write.allowed_writer_domain_ids:
            return
        if write.scope in {MemoryScope.HOUSEHOLD, MemoryScope.SYSTEM} and writer_domain_id == SecurityDomainId.SYSTEM:
            return
        raise Freyja3MemoryAccessError("memory write denied")

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS freyja3_memories (
                    memory_id TEXT PRIMARY KEY,
                    owner_domain_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    source_agent_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    classification TEXT NOT NULL,
                    allowed_readers_json TEXT NOT NULL,
                    allowed_writers_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_memory_owner_scope ON freyja3_memories(owner_domain_id, scope)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_freyja3_memory_updated ON freyja3_memories(updated_at DESC)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def _can_read(record: Freyja3MemoryRecord, reader_domain_id: SecurityDomainId) -> bool:
    if record.owner_domain_id == SecurityDomainId.PARALEGAL and reader_domain_id != SecurityDomainId.PARALEGAL:
        return False
    if reader_domain_id == SecurityDomainId.PARALEGAL and record.owner_domain_id != SecurityDomainId.PARALEGAL:
        return False
    return reader_domain_id == record.owner_domain_id or reader_domain_id in record.allowed_reader_domain_ids


def _record_row(record: Freyja3MemoryRecord) -> tuple[Any, ...]:
    return (
        record.memory_id,
        record.owner_domain_id.value,
        record.scope.value,
        record.source_agent_id,
        record.content,
        record.provenance,
        record.confidence,
        record.classification.value,
        json.dumps(sorted(domain.value for domain in record.allowed_reader_domain_ids)),
        json.dumps(sorted(domain.value for domain in record.allowed_writer_domain_ids)),
        json.dumps(record.metadata),
        record.created_at.isoformat(),
        record.updated_at.isoformat(),
        record.expires_at.isoformat() if record.expires_at else None,
    )


def _row_to_record(row: sqlite3.Row) -> Freyja3MemoryRecord:
    return Freyja3MemoryRecord(
        memory_id=row["memory_id"],
        owner_domain_id=SecurityDomainId(row["owner_domain_id"]),
        scope=MemoryScope(row["scope"]),
        source_agent_id=row["source_agent_id"],
        content=row["content"],
        provenance=row["provenance"],
        confidence=row["confidence"],
        classification=MemoryClassification(row["classification"]),
        allowed_reader_domain_ids=frozenset(SecurityDomainId(value) for value in json.loads(row["allowed_readers_json"])),
        allowed_writer_domain_ids=frozenset(SecurityDomainId(value) for value in json.loads(row["allowed_writers_json"])),
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )
