import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from freyja.config import settings
from freyja.memory.models import (
    AppendMessageRequest,
    ConversationMessagesResponse,
    ConversationSummary,
    CreateConversationRequest,
    CreateConversationResponse,
    ListConversationsResponse,
    MemoryMessage,
    MemoryPrincipal,
    MemoryProvenance,
    PutSharedMemoryRequest,
    PruneResponse,
    SharedMemory,
    SharedMemoryListResponse,
    utc_now,
)

logger = logging.getLogger(__name__)

PROVENANCE_METADATA_KEY = "provenance"
_LOCK = threading.Lock()
_SCHEMA_COMPONENT = "memory_store"
_SCHEMA_VERSION = 2


class MemoryAccessDeniedError(Exception):
    """Raised when a memory operation lacks a trusted principal."""


class MemoryStorageError(Exception):
    """Raised when durable memory storage is unavailable or unsafe."""


def _memory_provenance_for_request(
    principal: MemoryPrincipal,
    request: PutSharedMemoryRequest,
    metadata: dict[str, Any],
) -> MemoryProvenance:
    source = request.source or principal.client_type
    raw_metadata_provenance = metadata.get(PROVENANCE_METADATA_KEY)
    if request.provenance is not None:
        provenance = request.provenance
    elif isinstance(raw_metadata_provenance, dict):
        try:
            provenance = MemoryProvenance.model_validate(raw_metadata_provenance)
        except ValidationError:
            provenance = MemoryProvenance(source=source)
    else:
        provenance = MemoryProvenance(source=source)

    if provenance.trust_level == "untrusted_external_content" and provenance.authoritative:
        provenance = provenance.model_copy(update={"authoritative": False})
    if request.source and provenance.source != request.source:
        provenance = provenance.model_copy(update={"source": request.source})
    return provenance


def _memory_provenance_from_metadata(
    source: str,
    metadata: dict[str, Any],
) -> MemoryProvenance:
    raw_provenance = metadata.get(PROVENANCE_METADATA_KEY)
    if isinstance(raw_provenance, dict):
        try:
            provenance = MemoryProvenance.model_validate(raw_provenance)
        except ValidationError:
            return MemoryProvenance(source=source)
        if provenance.trust_level == "untrusted_external_content" and provenance.authoritative:
            return provenance.model_copy(update={"authoritative": False})
        return provenance
    return MemoryProvenance(source=source)


class MemoryStore:
    def __init__(
        self,
        database_path: str | None = None,
        max_messages_per_conversation: int | None = None,
        retention_days: int | None = None,
    ) -> None:
        self._database_path = (
            database_path
            if database_path is not None
            else settings.memory_database_path
        )
        self._max_messages = (
            max_messages_per_conversation
            if max_messages_per_conversation is not None
            else getattr(settings, "memory_max_messages_per_conversation", 1000)
        )
        self._retention_days = (
            retention_days
            if retention_days is not None
            else getattr(settings, "memory_retention_days", 90)
        )
        self._shared_item_limit = max(
            1, int(getattr(settings, "memory_shared_max_items_per_principal", 200))
        )
        self._shared_global_limit = max(
            self._shared_item_limit,
            int(getattr(settings, "memory_shared_max_global_items", 10000)),
        )
        self._shared_max_item_chars = max(
            1, int(getattr(settings, "memory_shared_max_item_chars", 2000))
        )
        self._initialized = False

    @property
    def database_path(self) -> str:
        return self._database_path

    def _ensure_parent_dir(self) -> None:
        path = Path(self._database_path).expanduser()
        parent = path.parent
        if _path_has_symlink(parent):
            raise MemoryStorageError("Memory database parent path contains a symlink")
        if parent:
            parent.mkdir(parents=True, exist_ok=True)
            _chmod_if_supported(parent, 0o700)
        if path.is_symlink():
            raise MemoryStorageError("Memory database path must not be a symlink")

    def _connect(self) -> sqlite3.Connection:
        self._ensure_parent_dir()
        conn = sqlite3.connect(self._database_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        _chmod_if_supported(Path(self._database_path), 0o600)
        return conn

    def initialize(self, *, force: bool = False) -> None:
        with _LOCK:
            if self._initialized and not force:
                return
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_versions (
                        component TEXT PRIMARY KEY,
                        version INTEGER NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS conversations (
                        conversation_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS messages (
                        message_id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        provider TEXT,
                        model TEXT,
                        request_id TEXT,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                            ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp
                        ON messages(conversation_id, timestamp);

                    CREATE INDEX IF NOT EXISTS idx_messages_request_id
                        ON messages(request_id);

                    CREATE TABLE IF NOT EXISTS shared_memories (
                        row_id TEXT PRIMARY KEY,
                        principal_scope TEXT NOT NULL,
                        client_type TEXT NOT NULL,
                        client_subject TEXT NOT NULL,
                        account_owner TEXT,
                        conversation_id TEXT,
                        memory_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        sensitivity TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        expires_at TEXT,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        UNIQUE(principal_scope, memory_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_shared_memories_scope_updated
                        ON shared_memories(principal_scope, updated_at DESC);

                    CREATE INDEX IF NOT EXISTS idx_shared_memories_scope_kind
                        ON shared_memories(principal_scope, kind);

                    CREATE INDEX IF NOT EXISTS idx_shared_memories_expiration
                        ON shared_memories(expires_at);
                    """
                )
                conn.execute(
                    """
                    INSERT INTO schema_versions (component, version, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(component) DO UPDATE SET
                        version=excluded.version,
                        updated_at=excluded.updated_at
                    """,
                    (_SCHEMA_COMPONENT, _SCHEMA_VERSION, utc_now().isoformat()),
                )
                conn.commit()
                self._initialized = True
            finally:
                conn.close()

    def _require_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def create_conversation(
        self, request: CreateConversationRequest
    ) -> CreateConversationResponse:
        self._require_initialized()
        conversation_id = request.conversation_id or str(uuid.uuid4())
        now = utc_now().isoformat()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO conversations (conversation_id, created_at, updated_at) VALUES (?, ?, ?)",
                    (conversation_id, now, now),
                )
                conn.commit()
                return CreateConversationResponse(conversation_id=conversation_id)
            finally:
                conn.close()

    def append_message(self, request: AppendMessageRequest) -> MemoryMessage:
        self._require_initialized()
        safe_request = request.model_copy(
            update={"content": redact_content(request.content)}
        )
        conversation_id = safe_request.conversation_id
        message_id = str(uuid.uuid4())
        timestamp = utc_now()
        metadata = safe_request.metadata or {}
        with _LOCK:
            conn = self._connect()
            try:
                now = timestamp.isoformat()
                conn.execute(
                    "INSERT INTO conversations (conversation_id, created_at, updated_at) VALUES (?, ?, ?) ON CONFLICT(conversation_id) DO UPDATE SET updated_at=excluded.updated_at",
                    (conversation_id, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO messages (
                        message_id, conversation_id, role, content, timestamp,
                        provider, model, request_id, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        conversation_id,
                        safe_request.role,
                        safe_request.content,
                        now,
                        safe_request.provider,
                        safe_request.model,
                        safe_request.request_id,
                        json.dumps(metadata),
                    ),
                )
                conn.commit()
                self._enforce_message_limit(conn, conversation_id)
                return MemoryMessage(
                    message_id=message_id,
                    conversation_id=conversation_id,
                    role=safe_request.role,
                    content=safe_request.content,
                    timestamp=timestamp,
                    provider=safe_request.provider,
                    model=safe_request.model,
                    request_id=safe_request.request_id,
                    metadata=metadata,
                )
            finally:
                conn.close()

    def _enforce_message_limit(self, conn: sqlite3.Connection, conversation_id: str) -> None:
        if self._max_messages <= 0:
            return
        cursor = conn.execute(
            """
            SELECT message_id FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC, rowid ASC
            """,
            (conversation_id,),
        )
        ids = [row["message_id"] for row in cursor.fetchall()]
        excess = len(ids) - self._max_messages
        if excess > 0:
            ids_to_remove = ids[:excess]
            placeholders = ",".join("?" * len(ids_to_remove))
            conn.execute(
                f"DELETE FROM messages WHERE message_id IN ({placeholders})",
                ids_to_remove,
            )
            conn.commit()

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int = 1000,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> ConversationMessagesResponse:
        self._require_initialized()
        with _LOCK:
            conn = self._connect()
            try:
                params: list[Any] = [conversation_id]
                clauses = ["conversation_id = ?"]
                if before is not None:
                    clauses.append("timestamp < ?")
                    params.append(before.isoformat())
                if after is not None:
                    clauses.append("timestamp > ?")
                    params.append(after.isoformat())
                where = " AND ".join(clauses)
                cursor = conn.execute(
                    f"""
                    SELECT * FROM messages
                    WHERE {where}
                    ORDER BY timestamp ASC, rowid ASC
                    LIMIT ?
                    """,
                    (*params, limit),
                )
                messages = [self._row_to_message(row) for row in cursor.fetchall()]
                return ConversationMessagesResponse(
                    conversation_id=conversation_id, messages=messages
                )
            finally:
                conn.close()

    def list_conversations(self) -> ListConversationsResponse:
        self._require_initialized()
        with _LOCK:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    """
                    SELECT c.conversation_id, c.created_at, c.updated_at, COUNT(m.message_id) AS message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.conversation_id
                    GROUP BY c.conversation_id
                    ORDER BY c.updated_at DESC
                    """
                )
                conversations = []
                for row in cursor.fetchall():
                    conversations.append(
                        ConversationSummary(
                            conversation_id=row["conversation_id"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            updated_at=datetime.fromisoformat(row["updated_at"]),
                            message_count=row["message_count"],
                        )
                    )
                return ListConversationsResponse(conversations=conversations)
            finally:
                conn.close()

    def delete_conversation(self, conversation_id: str) -> bool:
        self._require_initialized()
        with _LOCK:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def prune(self, *, older_than_days: int | None = None) -> PruneResponse:
        self._require_initialized()
        days = older_than_days if older_than_days is not None else self._retention_days
        cutoff = utc_now() - timedelta(days=days)
        with _LOCK:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM messages WHERE timestamp < ?",
                    (cutoff.isoformat(),),
                )
                messages_deleted = cursor.rowcount
                conn.execute(
                    """
                    DELETE FROM conversations
                    WHERE conversation_id NOT IN (
                        SELECT DISTINCT conversation_id FROM messages
                    )
                    """
                )
                empty_deleted = cursor.rowcount
                conn.commit()
                return PruneResponse(deleted_records=messages_deleted + empty_deleted)
            finally:
                conn.close()

    def put_shared_memory(
        self,
        principal: MemoryPrincipal,
        request: PutSharedMemoryRequest,
    ) -> SharedMemory:
        self._require_initialized()
        if not getattr(settings, "memory_shared_enabled", True):
            raise MemoryAccessDeniedError("Shared memory is disabled")
        memory_id = _safe_memory_id(request.memory_id)
        now = utc_now()
        safe_content = redact_content(request.content)[: self._shared_max_item_chars]
        metadata = dict(request.metadata or {})
        provenance = _memory_provenance_for_request(principal, request, metadata)
        metadata[PROVENANCE_METADATA_KEY] = provenance.model_dump(mode="json", exclude_none=True)
        scope = principal.scope_key
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._cleanup_expired_shared_memories(conn, now)
                existing = conn.execute(
                    """
                    SELECT row_id, created_at FROM shared_memories
                    WHERE principal_scope = ? AND memory_id = ?
                    """,
                    (scope, memory_id),
                ).fetchone()
                row_id = existing["row_id"] if existing else str(uuid.uuid4())
                created_at = (
                    datetime.fromisoformat(existing["created_at"]) if existing else now
                )
                conn.execute(
                    """
                    INSERT INTO shared_memories (
                        row_id, principal_scope, client_type, client_subject,
                        account_owner, conversation_id, memory_id, kind, content,
                        source, confidence, sensitivity, created_at, updated_at,
                        expires_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(principal_scope, memory_id) DO UPDATE SET
                        kind=excluded.kind,
                        content=excluded.content,
                        source=excluded.source,
                        confidence=excluded.confidence,
                        sensitivity=excluded.sensitivity,
                        updated_at=excluded.updated_at,
                        expires_at=excluded.expires_at,
                        metadata=excluded.metadata
                    """,
                    (
                        row_id,
                        scope,
                        provenance.source,
                        principal.client_subject,
                        principal.account_owner,
                        principal.conversation_id,
                        memory_id,
                        request.kind,
                        safe_content,
                        principal.client_type,
                        request.confidence,
                        request.sensitivity,
                        created_at.isoformat(),
                        now.isoformat(),
                        request.expires_at.isoformat() if request.expires_at else None,
                        json.dumps(metadata),
                    ),
                )
                self._enforce_shared_quotas(conn, scope)
                conn.commit()
                return SharedMemory(
                    memory_id=memory_id,
                    client_type=principal.client_type,
                    client_subject=principal.client_subject,
                    account_owner=principal.account_owner,
                    conversation_id=principal.conversation_id,
                    kind=request.kind,
                    content=safe_content,
                    source=provenance.source,
                    confidence=request.confidence,
                    sensitivity=request.sensitivity,
                    created_at=created_at,
                    updated_at=now,
                    expires_at=request.expires_at,
                    provenance=provenance,
                    metadata=metadata,
                )
            except sqlite3.Error as exc:
                conn.rollback()
                raise MemoryStorageError("Shared memory storage failed") from exc
            finally:
                conn.close()

    def list_shared_memories(
        self,
        principal: MemoryPrincipal,
        *,
        kinds: list[str] | None = None,
        limit: int = 50,
    ) -> SharedMemoryListResponse:
        self._require_initialized()
        if not getattr(settings, "memory_shared_enabled", True):
            return SharedMemoryListResponse(memories=[])
        bounded_limit = min(max(1, int(limit)), 200)
        clauses = [
            "principal_scope = ?",
            "(expires_at IS NULL OR expires_at > ?)",
        ]
        params: list[Any] = [principal.scope_key, utc_now().isoformat()]
        if kinds:
            placeholders = ",".join("?" * len(kinds))
            clauses.append(f"kind IN ({placeholders})")
            params.extend(kinds)
        params.append(bounded_limit)
        with _LOCK:
            conn = self._connect()
            try:
                rows = conn.execute(
                    f"""
                    SELECT * FROM shared_memories
                    WHERE {' AND '.join(clauses)}
                    ORDER BY updated_at DESC, rowid DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
                memories: list[SharedMemory] = []
                for row in rows:
                    memory = self._row_to_shared_memory(row)
                    if memory is not None:
                        memories.append(memory)
                return SharedMemoryListResponse(memories=memories)
            except sqlite3.Error as exc:
                raise MemoryStorageError("Shared memory storage failed") from exc
            finally:
                conn.close()

    def get_shared_memory(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
    ) -> SharedMemory | None:
        self._require_initialized()
        with _LOCK:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM shared_memories
                    WHERE principal_scope = ?
                      AND memory_id = ?
                      AND (expires_at IS NULL OR expires_at > ?)
                    """,
                    (principal.scope_key, _safe_memory_id(memory_id), utc_now().isoformat()),
                ).fetchone()
                return self._row_to_shared_memory(row) if row else None
            except sqlite3.Error as exc:
                raise MemoryStorageError("Shared memory storage failed") from exc
            finally:
                conn.close()

    def delete_shared_memory(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
    ) -> bool:
        self._require_initialized()
        with _LOCK:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM shared_memories WHERE principal_scope = ? AND memory_id = ?",
                    (principal.scope_key, _safe_memory_id(memory_id)),
                )
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as exc:
                raise MemoryStorageError("Shared memory storage failed") from exc
            finally:
                conn.close()

    def prune_shared_memories(self) -> int:
        self._require_initialized()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                deleted = self._cleanup_expired_shared_memories(conn, utc_now())
                self._enforce_global_shared_quota(conn)
                conn.commit()
                return deleted
            except sqlite3.Error as exc:
                conn.rollback()
                raise MemoryStorageError("Shared memory storage failed") from exc
            finally:
                conn.close()

    def _cleanup_expired_shared_memories(
        self, conn: sqlite3.Connection, now: datetime
    ) -> int:
        cursor = conn.execute(
            "DELETE FROM shared_memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now.isoformat(),),
        )
        return cursor.rowcount

    def _enforce_shared_quotas(self, conn: sqlite3.Connection, scope: str) -> None:
        self._enforce_principal_shared_quota(conn, scope)
        self._enforce_global_shared_quota(conn)

    def _enforce_principal_shared_quota(
        self, conn: sqlite3.Connection, scope: str
    ) -> None:
        cursor = conn.execute(
            """
            SELECT row_id FROM shared_memories
            WHERE principal_scope = ?
            ORDER BY updated_at DESC, rowid DESC
            """,
            (scope,),
        )
        rows = [row["row_id"] for row in cursor.fetchall()]
        excess = len(rows) - self._shared_item_limit
        if excess > 0:
            self._delete_shared_rows(conn, rows[-excess:])

    def _enforce_global_shared_quota(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute(
            """
            SELECT row_id FROM shared_memories
            ORDER BY updated_at DESC, rowid DESC
            """
        )
        rows = [row["row_id"] for row in cursor.fetchall()]
        excess = len(rows) - self._shared_global_limit
        if excess > 0:
            self._delete_shared_rows(conn, rows[-excess:])

    def _delete_shared_rows(self, conn: sqlite3.Connection, row_ids: list[str]) -> None:
        if not row_ids:
            return
        placeholders = ",".join("?" * len(row_ids))
        conn.execute(f"DELETE FROM shared_memories WHERE row_id IN ({placeholders})", row_ids)

    def _row_to_shared_memory(self, row: sqlite3.Row) -> SharedMemory | None:
        try:
            metadata = json.loads(row["metadata"])
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        provenance = _memory_provenance_from_metadata(row["source"], metadata)
        try:
            return SharedMemory(
                memory_id=row["memory_id"],
                client_type=row["client_type"],
                client_subject=row["client_subject"],
                account_owner=row["account_owner"],
                conversation_id=row["conversation_id"],
                kind=row["kind"],
                content=row["content"],
                source=row["source"],
                confidence=float(row["confidence"]),
                sensitivity=row["sensitivity"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                expires_at=(
                    datetime.fromisoformat(row["expires_at"])
                    if row["expires_at"]
                    else None
                ),
                provenance=provenance,
                metadata=metadata,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed shared memory row: %s", exc)
            return None

    def _row_to_message(self, row: sqlite3.Row) -> MemoryMessage:
        try:
            metadata = json.loads(row["metadata"])
        except json.JSONDecodeError:
            metadata = {}
        try:
            return MemoryMessage(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                provider=row["provider"],
                model=row["model"],
                request_id=row["request_id"],
                metadata=metadata,
            )
        except ValidationError as exc:
            logger.warning("Skipping malformed memory row %s: %s", row["message_id"], exc)
            raise


# Module-level shared store instance. Tests may replace this directly.
_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
        _store.initialize()
    return _store


def set_store(store: MemoryStore | None) -> None:
    global _store
    _store = store


_SECRET_PATTERNS = (
    re.compile(r"(?i)api[_\-]?key\s*[:=]\s*[^\s&]+"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[a-z0-9_\-\.+/=]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9_\-\.+/=]+"),
    re.compile(r"(?i)sk-[a-z0-9]+"),
    re.compile(r"(?i)token\s*[:=]\s*[^\s&]+"),
)


def _has_provider_error_prefix(content: str) -> bool:
    lowered = content.lower()
    return lowered.startswith("error:") or lowered.startswith("provider error:")


def redact_content(content: str) -> str:
    """Remove API keys, authorization headers, bearer tokens, and raw provider errors."""
    if not content:
        return content
    if _has_provider_error_prefix(content):
        return "<provider error redacted>"
    for pattern in _SECRET_PATTERNS:
        content = pattern.sub(lambda m: _redact_match(m.group(0)), content)
    return content


def _redact_match(match: str) -> str:
    if "=" in match:
        key, _ = match.split("=", 1)
        return f"{key}=<redacted>"
    if ":" in match:
        key, _ = match.split(":", 1)
        return f"{key}: <redacted>"
    return "<redacted>"


def create_conversation(
    request: CreateConversationRequest | None = None,
    store: MemoryStore | None = None,
) -> CreateConversationResponse:
    s = store or get_store()
    return s.create_conversation(request or CreateConversationRequest())


def append_message(
    request: AppendMessageRequest,
    store: MemoryStore | None = None,
) -> MemoryMessage:
    s = store or get_store()
    safe_request = request.model_copy(update={"content": redact_content(request.content)})
    return s.append_message(safe_request)


def get_messages(
    conversation_id: str,
    *,
    limit: int = 1000,
    before: datetime | None = None,
    after: datetime | None = None,
    store: MemoryStore | None = None,
) -> ConversationMessagesResponse:
    s = store or get_store()
    return s.get_messages(conversation_id, limit=limit, before=before, after=after)


def list_conversations(store: MemoryStore | None = None) -> ListConversationsResponse:
    s = store or get_store()
    return s.list_conversations()


def delete_conversation(
    conversation_id: str,
    store: MemoryStore | None = None,
) -> bool:
    s = store or get_store()
    return s.delete_conversation(conversation_id)


def prune(
    *,
    older_than_days: int | None = None,
    store: MemoryStore | None = None,
) -> PruneResponse:
    s = store or get_store()
    return s.prune(older_than_days=older_than_days)


def put_shared_memory(
    principal: MemoryPrincipal,
    request: PutSharedMemoryRequest,
    store: MemoryStore | None = None,
) -> SharedMemory:
    return (store or get_store()).put_shared_memory(principal, request)


def list_shared_memories(
    principal: MemoryPrincipal,
    *,
    kinds: list[str] | None = None,
    limit: int = 50,
    store: MemoryStore | None = None,
) -> SharedMemoryListResponse:
    return (store or get_store()).list_shared_memories(
        principal, kinds=kinds, limit=limit
    )


def get_shared_memory(
    principal: MemoryPrincipal,
    memory_id: str,
    store: MemoryStore | None = None,
) -> SharedMemory | None:
    return (store or get_store()).get_shared_memory(principal, memory_id)


def delete_shared_memory(
    principal: MemoryPrincipal,
    memory_id: str,
    store: MemoryStore | None = None,
) -> bool:
    return (store or get_store()).delete_shared_memory(principal, memory_id)


class MemoryDisabledStore:
    """No-op store used when memory is disabled. Returns empty/success defaults."""

    def create_conversation(
        self, request: CreateConversationRequest | None = None
    ) -> CreateConversationResponse:
        return CreateConversationResponse(
            conversation_id=request.conversation_id if request else str(uuid.uuid4())
        )

    def append_message(self, request: AppendMessageRequest) -> MemoryMessage:
        return MemoryMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=request.conversation_id,
            role=request.role,
            content=redact_content(request.content),
            timestamp=utc_now(),
            provider=request.provider,
            model=request.model,
            request_id=request.request_id,
            metadata=request.metadata or {},
        )

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int = 1000,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> ConversationMessagesResponse:
        return ConversationMessagesResponse(conversation_id=conversation_id, messages=[])

    def list_conversations(self) -> ListConversationsResponse:
        return ListConversationsResponse(conversations=[])

    def delete_conversation(self, conversation_id: str) -> bool:
        return True

    def prune(self, *, older_than_days: int | None = None) -> PruneResponse:
        return PruneResponse(deleted_records=0)

    def put_shared_memory(
        self,
        principal: MemoryPrincipal,
        request: PutSharedMemoryRequest,
    ) -> SharedMemory:
        now = utc_now()
        content = redact_content(request.content)[
            : max(1, int(getattr(settings, "memory_shared_max_item_chars", 2000)))
        ]
        metadata = dict(request.metadata or {})
        provenance = _memory_provenance_for_request(principal, request, metadata)
        metadata[PROVENANCE_METADATA_KEY] = provenance.model_dump(mode="json", exclude_none=True)
        return SharedMemory(
            memory_id=_safe_memory_id(request.memory_id),
            client_type=principal.client_type,
            client_subject=principal.client_subject,
            account_owner=principal.account_owner,
            conversation_id=principal.conversation_id,
            kind=request.kind,
            content=content,
            source=provenance.source,
            confidence=request.confidence,
            sensitivity=request.sensitivity,
            created_at=now,
            updated_at=now,
            expires_at=request.expires_at,
            provenance=provenance,
            metadata=metadata,
        )

    def list_shared_memories(
        self,
        principal: MemoryPrincipal,
        *,
        kinds: list[str] | None = None,
        limit: int = 50,
    ) -> SharedMemoryListResponse:
        return SharedMemoryListResponse(memories=[])

    def get_shared_memory(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
    ) -> SharedMemory | None:
        return None

    def delete_shared_memory(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
    ) -> bool:
        return False


def is_memory_enabled() -> bool:
    return bool(getattr(settings, "memory_enabled", True))


def get_active_store() -> MemoryStore | MemoryDisabledStore:
    if is_memory_enabled():
        return get_store()
    return MemoryDisabledStore()


def _safe_memory_id(memory_id: str | None) -> str:
    value = memory_id or str(uuid.uuid4())
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError("memory_id contains invalid characters")
    return value


def _path_has_symlink(path: Path) -> bool:
    path = path.expanduser()
    parts = path.parts
    if not parts:
        return False
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            return True
    return False


def _chmod_if_supported(path: Path, mode: int) -> None:
    try:
        if path.exists():
            os.chmod(path, mode)
    except OSError:
        logger.debug("Unable to chmod memory path %s", path)
