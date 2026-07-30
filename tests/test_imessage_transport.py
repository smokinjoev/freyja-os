from __future__ import annotations

from datetime import timezone

import pytest

from connectors.imessage.config import IMessageSettings
from connectors.imessage.models import IMessageReply
from connectors.imessage.transport import IMessageTransport, UnsupportedIMessageEvent


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
