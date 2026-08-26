from __future__ import annotations

from datetime import UTC, datetime, timezone
import sqlite3
import subprocess
from unittest.mock import patch

import asyncio
import pytest

from connectors.imessage.config import IMessageSettings
from connectors.imessage.models import IMessageReply
from connectors.imessage.transport import (
    IMessageTransport,
    IMessageTransportError,
    UnsupportedIMessageEvent,
)


def settings() -> IMessageSettings:
    return IMessageSettings(
        _env_file=None,
        imessage_imsg_path="/opt/homebrew/bin/imsg",
        imessage_database_path="/Users/freyja/Library/Messages/chat.db",
        imessage_poll_database_enabled=False,
    )


def event(**overrides):
    payload = {
        "guid": "13832F24-23A6-4734-A062-E84F5F813EB5",
        "text": "Just checking",
        "sender": "+15551234567",
        "chat_id": 4,
        "chat_identifier": "+15551234567",
        "created_at": "2026-07-30T04:09:38.511Z",
        "is_group": False,
        "is_from_me": False,
    }
    payload.update(overrides)
    return payload


def test_parse_imsg_event():
    message = IMessageTransport.parse_event(event())

    assert message.sender == "+15551234567"
    assert message.text == "Just checking"
    assert message.message_id == "13832F24-23A6-4734-A062-E84F5F813EB5"
    assert message.chat_id == 4
    assert message.timestamp.tzinfo == timezone.utc
    assert message.is_group is False
    assert message.is_from_me is False


def test_parse_photo_only_imsg_event():
    message = IMessageTransport.parse_event(
        event(
            text=None,
            attachments=[
                {
                    "filename": "/Users/freyja/Library/Messages/Attachments/photo.jpg",
                    "mime_type": "image/jpeg",
                }
            ],
        )
    )

    assert message.text == ""
    assert len(message.attachments) == 1
    assert message.attachments[0].filename == "photo.jpg"
    assert message.attachments[0].mime_type == "image/jpeg"


@pytest.mark.parametrize(
    "payload",
    [
        "not-an-object",
        event(sender=""),
        event(text=""),
        event(guid=None),
        event(chat_id="4"),
        event(chat_identifier=""),
        event(created_at="not-a-date"),
    ],
)
def test_reject_invalid_events(payload):
    with pytest.raises(UnsupportedIMessageEvent):
        IMessageTransport.parse_event(payload)


def test_watch_command_is_argument_safe():
    transport = IMessageTransport(settings())

    command = transport.watch_command(since_rowid=42)

    assert command == [
        "/opt/homebrew/bin/imsg",
        "watch",
        "--db",
        "/Users/freyja/Library/Messages/chat.db",
        "--json",
        "--since-rowid",
        "42",
    ]


def test_send_command_uses_chat_id_without_a_shell():
    transport = IMessageTransport(settings())
    reply = IMessageReply(chat_id=4, text='hello; $(touch /tmp/nope)')

    command = transport.send_command(reply)

    assert command == [
        "/opt/homebrew/bin/imsg",
        "send",
        "--db",
        "/Users/freyja/Library/Messages/chat.db",
        "--chat-id",
        "4",
        "--text",
        'hello; $(touch /tmp/nope)',
        "--service",
        "imessage",
        "--json",
    ]


def test_send_command_uses_recipient_for_direct_reply_without_a_shell():
    transport = IMessageTransport(settings())
    reply = IMessageReply(
        chat_id=4,
        text='hello; $(touch /tmp/nope)',
        recipient="+15551234567",
        is_group=False,
    )

    command = transport.send_command(reply)

    assert command == [
        "/opt/homebrew/bin/imsg",
        "send",
        "--db",
        "/Users/freyja/Library/Messages/chat.db",
        "--to",
        "+15551234567",
        "--text",
        'hello; $(touch /tmp/nope)',
        "--service",
        "imessage",
        "--json",
    ]


def test_send_command_keeps_chat_id_for_group_reply():
    transport = IMessageTransport(settings())
    reply = IMessageReply(
        chat_id=4,
        text="hello",
        recipient="+15551234567",
        is_group=True,
    )

    command = transport.send_command(reply)

    assert "--chat-id" in command
    assert "4" in command
    assert "--to" not in command


def test_chats_command_is_argument_safe():
    transport = IMessageTransport(settings())

    assert transport.chats_command(limit=5) == [
        "/opt/homebrew/bin/imsg",
        "chats",
        "--limit",
        "5",
        "--json",
    ]


def test_history_command_is_argument_safe():
    transport = IMessageTransport(settings())

    assert transport.history_command(chat_id=4, limit=2) == [
        "/opt/homebrew/bin/imsg",
        "history",
        "--chat-id",
        "4",
        "--limit",
        "2",
        "--json",
    ]


@pytest.mark.asyncio
async def test_recent_messages_reads_recent_chat_history(monkeypatch):
    transport = IMessageTransport(settings())
    requests: list[list[str]] = []

    async def _fake_subprocess(*args, **kwargs):
        command = list(args)
        requests.append(command)
        if "chats" in command:
            return _CompletedProcess(
                b'{"id":4,"identifier":"+15551234567"}\n'
                b'{"id":"skip-me","identifier":"+15557654321"}\n'
            )
        return _CompletedProcess(
            (
                '{"guid":"msg-2","text":"second","sender":"+15551234567",'
                '"chat_id":4,"chat_identifier":"+15551234567",'
                '"created_at":"2026-07-30T04:09:39.511Z",'
                '"is_group":false,"is_from_me":false}\n'
                '{"guid":"msg-1","text":"first","sender":"+15551234567",'
                '"chat_id":4,"chat_identifier":"+15551234567",'
                '"created_at":"2026-07-30T04:09:38.511Z",'
                '"is_group":false,"is_from_me":false}\n'
            ).encode()
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess)

    messages = await transport.recent_messages()

    assert [message.message_id for message in messages] == ["msg-1", "msg-2"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_recent_messages_reads_messages_database(tmp_path):
    database_path = tmp_path / "chat.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            guid TEXT,
            text TEXT,
            handle_id INTEGER,
            date INTEGER,
            is_from_me INTEGER,
            is_system_message INTEGER DEFAULT 0
        );
        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY,
            chat_identifier TEXT,
            style INTEGER
        );
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT
        );
        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER
        );
        """
    )
    connection.execute("INSERT INTO handle VALUES (1, '+15551234567')")
    connection.execute("INSERT INTO chat VALUES (4, '+15551234567', 45)")
    connection.execute(
        "INSERT INTO message VALUES (1, 'msg-1', 'first', 1, ?, 0, 0)",
        (1_000_000_000,),
    )
    connection.execute(
        "INSERT INTO message VALUES (2, 'msg-2', 'second', 1, ?, 0, 0)",
        (2_000_000_000,),
    )
    connection.execute("INSERT INTO chat_message_join VALUES (4, 1)")
    connection.execute("INSERT INTO chat_message_join VALUES (4, 2)")
    connection.commit()
    connection.close()

    transport = IMessageTransport(
        IMessageSettings(
            _env_file=None,
            imessage_database_path=str(database_path),
            imessage_poll_database_enabled=True,
            imessage_poll_chat_limit=1,
            imessage_poll_history_limit=2,
        )
    )

    messages = await transport.recent_messages()

    assert [message.message_id for message in messages] == ["msg-1", "msg-2"]
    assert messages[0].sender == "+15551234567"
    assert messages[0].timestamp == datetime(2001, 1, 1, 0, 0, 1, tzinfo=UTC)
    assert messages[0].is_group is False


@pytest.mark.asyncio
async def test_recent_messages_reads_photo_only_database_messages(tmp_path):
    database_path = tmp_path / "chat.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            guid TEXT,
            text TEXT,
            handle_id INTEGER,
            date INTEGER,
            is_from_me INTEGER,
            is_system_message INTEGER DEFAULT 0
        );
        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY,
            chat_identifier TEXT,
            style INTEGER
        );
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT
        );
        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER
        );
        CREATE TABLE attachment (
            ROWID INTEGER PRIMARY KEY,
            filename TEXT,
            mime_type TEXT
        );
        CREATE TABLE message_attachment_join (
            message_id INTEGER,
            attachment_id INTEGER
        );
        """
    )
    connection.execute("INSERT INTO handle VALUES (1, '+15551234567')")
    connection.execute("INSERT INTO chat VALUES (4, '+15551234567', 45)")
    connection.execute(
        "INSERT INTO message VALUES (1, 'photo-1', NULL, 1, ?, 0, 0)",
        (1_000_000_000,),
    )
    connection.execute(
        "INSERT INTO attachment VALUES (10, '/tmp/photo.jpg', 'image/jpeg')"
    )
    connection.execute("INSERT INTO chat_message_join VALUES (4, 1)")
    connection.execute("INSERT INTO message_attachment_join VALUES (1, 10)")
    connection.commit()
    connection.close()

    transport = IMessageTransport(
        IMessageSettings(
            _env_file=None,
            imessage_database_path=str(database_path),
            imessage_poll_database_enabled=True,
            imessage_poll_chat_limit=1,
            imessage_poll_history_limit=2,
        )
    )

    messages = await transport.recent_messages()

    assert [message.message_id for message in messages] == ["photo-1"]
    assert messages[0].text == ""
    assert messages[0].attachments[0].filename == "photo.jpg"
    assert messages[0].attachments[0].mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_send_times_out_when_imsg_does_not_exit(monkeypatch):
    transport = IMessageTransport(
        IMessageSettings(
            _env_file=None,
            imessage_send_timeout_seconds=0.01,
        )
    )
    def _fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr("connectors.imessage.transport.subprocess.run", _fake_run)

    with pytest.raises(IMessageTransportError, match="imsg send timed out after 0.01s"):
        await transport.send(IMessageReply(chat_id=4, text="hello"))


@pytest.mark.asyncio
async def test_send_failure_includes_stdout_when_stderr_is_empty(monkeypatch):
    transport = IMessageTransport(settings())

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout='{"status":"failed"}\n', stderr="")

    monkeypatch.setattr("connectors.imessage.transport.subprocess.run", _fake_run)

    with pytest.raises(IMessageTransportError, match='stdout=\\{"status":"failed"\\}'):
        await transport.send(IMessageReply(chat_id=4, text="hello"))


@pytest.mark.asyncio
async def test_recent_messages_times_out_stuck_imsg_command(monkeypatch):
    transport = IMessageTransport(
        IMessageSettings(
            _env_file=None,
            imessage_command_timeout_seconds=0.01,
            imessage_poll_database_enabled=False,
        )
    )
    process = _HangingProcess()

    async def _fake_subprocess(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess)

    with pytest.raises(IMessageTransportError, match="imsg command timed out"):
        await transport.recent_messages()

    assert process.killed is True


@pytest.mark.asyncio
async def test_watch_failure_includes_stderr(monkeypatch):
    transport = IMessageTransport(settings())

    async def _fake_subprocess(*args, **kwargs):
        return _FailedWatchProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess)

    with pytest.raises(IMessageTransportError, match="permission denied"):
        async for _ in transport.watch():
            pass


def test_imsg_path_is_discovered_from_path_when_unconfigured():
    configured = IMessageSettings(_env_file=None, imessage_imsg_path="")

    with patch("connectors.imessage.config.which", return_value="/usr/local/bin/imsg"):
        assert configured.resolved_imsg_path == "/usr/local/bin/imsg"


def test_explicit_imsg_path_takes_precedence():
    configured = IMessageSettings(
        _env_file=None,
        imessage_imsg_path="/custom/bin/imsg",
    )

    assert configured.resolved_imsg_path == "/custom/bin/imsg"


class _HangingProcess:
    returncode = None

    def __init__(self) -> None:
        self.killed = False

    async def communicate(self):
        await asyncio.sleep(60)

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


class _AsyncLineReader:
    def __init__(self, lines: list[bytes] | None = None, data: bytes = b"") -> None:
        self._lines = lines or []
        self._data = data

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)

    async def read(self):
        return self._data


class _FailedWatchProcess:
    stdout = _AsyncLineReader()
    stderr = _AsyncLineReader(data=b"permission denied")

    async def wait(self):
        return 1


class _CompletedProcess:
    returncode = 0

    def __init__(self, stdout: bytes) -> None:
        self._stdout = stdout

    async def communicate(self):
        return self._stdout, b""
