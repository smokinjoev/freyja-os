from __future__ import annotations

from datetime import timezone
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


@pytest.mark.asyncio
async def test_send_times_out_when_imsg_does_not_exit(monkeypatch):
    transport = IMessageTransport(
        IMessageSettings(
            _env_file=None,
            imessage_send_timeout_seconds=0.01,
        )
    )
    process = _HangingProcess()

    async def _fake_subprocess(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess)

    with pytest.raises(IMessageTransportError, match="imsg send timed out"):
        await transport.send(IMessageReply(chat_id=4, text="hello"))

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
