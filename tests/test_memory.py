import json
import os
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from freyja.config import settings
from freyja.memory.models import AppendMessageRequest, CreateConversationRequest
from freyja.memory.store import (
    MemoryDisabledStore,
    MemoryStore,
    get_active_store,
    get_store,
    is_memory_enabled,
    redact_content,
    set_store,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    return str(tmp_path / "test_memory.db")


@pytest.fixture
def store(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    monkeypatch.setattr(settings, "memory_database_path", temp_db)
    s = MemoryStore(database_path=temp_db, max_messages_per_conversation=5, retention_days=7)
    s.initialize()
    yield s
    s.delete_conversation("conv-1")
    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_schema_initialization_creates_tables_and_indexes(temp_db: str) -> None:
    s = MemoryStore(database_path=temp_db)
    s.initialize()

    conn = sqlite3.connect(temp_db)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY name"
        )
        names = {row[0] for row in cursor.fetchall()}
        assert "conversations" in names
        assert "messages" in names
        assert "idx_messages_conversation_timestamp" in names
        assert "idx_messages_request_id" in names
    finally:
        conn.close()
    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_schema_initialization_is_idempotent(temp_db: str) -> None:
    s = MemoryStore(database_path=temp_db)
    s.initialize()
    s.initialize()
    assert s._initialized is True
    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_create_conversation_generates_uuid(temp_db: str) -> None:
    s = MemoryStore(database_path=temp_db)
    response = s.create_conversation(CreateConversationRequest())
    assert response.conversation_id
    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_create_conversation_with_explicit_id(temp_db: str) -> None:
    s = MemoryStore(database_path=temp_db)
    response = s.create_conversation(CreateConversationRequest(conversation_id="explicit"))
    assert response.conversation_id == "explicit"
    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_append_and_retrieve_messages(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    store.append_message(
        AppendMessageRequest(conversation_id="conv-1", role="user", content="hello")
    )
    response = store.get_messages("conv-1")
    assert len(response.messages) == 1
    assert response.messages[0].role == "user"
    assert response.messages[0].content == "hello"


def test_conversation_ordering_by_updated_at(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-a"))
    store.create_conversation(CreateConversationRequest(conversation_id="conv-b"))
    store.append_message(
        AppendMessageRequest(conversation_id="conv-b", role="user", content="second")
    )
    store.append_message(
        AppendMessageRequest(conversation_id="conv-a", role="user", content="first")
    )
    response = store.list_conversations()
    ids = [c.conversation_id for c in response.conversations]
    assert ids[0] == "conv-a"
    assert ids[1] == "conv-b"


def test_delete_conversation_removes_messages(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    store.append_message(
        AppendMessageRequest(conversation_id="conv-1", role="user", content="hello")
    )
    assert store.delete_conversation("conv-1") is True
    assert store.get_messages("conv-1").messages == []
    assert store.delete_conversation("conv-1") is False


def test_prune_removes_old_messages(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    old_message = AppendMessageRequest(
        conversation_id="conv-1",
        role="user",
        content="old",
        metadata={"manual_timestamp": "2020-01-01T00:00:00+00:00"},
    )
    store.append_message(old_message)

    conn = sqlite3.connect(store.database_path)
    try:
        conn.execute(
            "UPDATE messages SET timestamp = '2020-01-01T00:00:00+00:00' WHERE conversation_id = ?",
            ("conv-1",),
        )
        conn.commit()
    finally:
        conn.close()

    store.append_message(
        AppendMessageRequest(conversation_id="conv-1", role="user", content="new")
    )
    result = store.prune(older_than_days=365)
    assert result.deleted_records >= 1
    messages = store.get_messages("conv-1").messages
    assert all(m.content != "old" for m in messages)


def test_message_limit_enforced(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    for i in range(10):
        store.append_message(
            AppendMessageRequest(
                conversation_id="conv-1",
                role="user",
                content=f"msg-{i}",
            )
        )
    messages = store.get_messages("conv-1").messages
    assert len(messages) == 5
    assert messages[0].content == "msg-5"


def test_concurrent_appends_do_not_corrupt_database(temp_db: str) -> None:
    s = MemoryStore(database_path=temp_db, max_messages_per_conversation=1000)
    s.create_conversation(CreateConversationRequest(conversation_id="conv-1"))

    def append(index: int) -> None:
        s.append_message(
            AppendMessageRequest(
                conversation_id="conv-1",
                role="user",
                content=f"thread-{index}",
            )
        )

    threads = [threading.Thread(target=append, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    messages = s.get_messages("conv-1").messages
    assert len(messages) == 20
    if os.path.exists(temp_db):
        os.remove(temp_db)


def test_redact_content_strips_secrets() -> None:
    assert redact_content("api_key=secret123") == "api_key=<redacted>"
    assert redact_content("Authorization: Bearer token123") == "Authorization: <redacted>"
    assert redact_content("Bearer abc.def.ghi") == "<redacted>"
    assert redact_content("sk-12345abcdef") == "<redacted>"
    assert redact_content("token=shhh") == "token=<redacted>"


def test_redact_content_strips_provider_errors() -> None:
    assert redact_content("error: something bad happened") == "<provider error redacted>"
    assert redact_content("Provider Error: timeout") == "<provider error redacted>"


def test_metadata_round_trip(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    store.append_message(
        AppendMessageRequest(
            conversation_id="conv-1",
            role="assistant",
            content="hi",
            provider="ollama",
            model="qwen2.5:1.5b",
            request_id="req-123",
            metadata={"foo": "bar", "count": 1},
        )
    )
    message = store.get_messages("conv-1").messages[0]
    assert message.provider == "ollama"
    assert message.model == "qwen2.5:1.5b"
    assert message.request_id == "req-123"
    assert message.metadata == {"foo": "bar", "count": 1}


def test_active_store_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    assert isinstance(get_active_store(), MemoryDisabledStore)


def test_disabled_store_returns_empty_defaults() -> None:
    disabled = MemoryDisabledStore()
    assert disabled.create_conversation(CreateConversationRequest(conversation_id="c")).conversation_id == "c"
    msg = disabled.append_message(
        AppendMessageRequest(conversation_id="c", role="user", content="api_key=secret")
    )
    assert "<redacted>" in msg.content
    assert disabled.get_messages("c").messages == []
    assert disabled.list_conversations().conversations == []
    assert disabled.delete_conversation("c") is True
    assert disabled.prune().deleted_records == 0


def test_database_failure_isolated_in_router(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenStore:
        def create_conversation(self, request):
            raise RuntimeError("disk full")

        def append_message(self, request):
            raise RuntimeError("disk full")

    monkeypatch.setattr("freyja.memory.store.get_active_store", lambda: BrokenStore())
    monkeypatch.setattr("freyja.memory.store.get_store", lambda: BrokenStore())
    from freyja.memory.store import append_message as unsafe_append

    with pytest.raises(RuntimeError):
        unsafe_append(
            AppendMessageRequest(conversation_id="c", role="user", content="hello")
        )


def test_get_messages_with_before_and_after(store: MemoryStore) -> None:
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    store.append_message(
        AppendMessageRequest(conversation_id="conv-1", role="user", content="first")
    )
    store.append_message(
        AppendMessageRequest(conversation_id="conv-1", role="user", content="middle")
    )
    store.append_message(
        AppendMessageRequest(conversation_id="conv-1", role="user", content="last")
    )

    all_messages = store.get_messages("conv-1").messages
    assert len(all_messages) == 3
    first_ts = all_messages[0].timestamp
    middle_ts = all_messages[1].timestamp
    last_ts = all_messages[2].timestamp

    assert all_messages[0].content == "first"
    assert all_messages[1].content == "middle"
    assert all_messages[2].content == "last"

    # Strictly after the first message excludes the first message.
    after_first = store.get_messages("conv-1", after=first_ts).messages
    assert len(after_first) == 2
    assert after_first[0].content == "middle"

    # Strictly before the last message excludes the last message.
    before_last = store.get_messages("conv-1", before=last_ts).messages
    assert len(before_last) == 2
    assert before_last[-1].content == "middle"

    # Open interval between first and last returns only the middle message.
    window = store.get_messages("conv-1", after=first_ts, before=last_ts).messages
    assert len(window) == 1
    assert window[0].content == "middle"

    # Boundaries at the exact middle timestamp exclude everything.
    assert store.get_messages("conv-1", after=middle_ts, before=middle_ts).messages == []
