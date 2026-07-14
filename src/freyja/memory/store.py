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
    PruneResponse,
    utc_now,
)

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


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
            else getattr(settings, "memory_database_path", "/Users/freyja/freyja-os/data/freyja.db")
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
        self._initialized = False

    @property
    def database_path(self) -> str:
        return self._database_path

    def _ensure_parent_dir(self) -> None:
        parent = Path(self._database_path).parent
        if parent:
            parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        self._ensure_parent_dir()
        conn = sqlite3.connect(self._database_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self, *, force: bool = False) -> None:
        with _LOCK:
            if self._initialized and not force:
                return
            conn = self._connect()
            try:
                conn.executescript(
                    """
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
                    """
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


def is_memory_enabled() -> bool:
    return bool(getattr(settings, "memory_enabled", True))


def get_active_store() -> MemoryStore | MemoryDisabledStore:
    if is_memory_enabled():
        return get_store()
    return MemoryDisabledStore()
