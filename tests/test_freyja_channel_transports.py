from __future__ import annotations

import pytest

from freyja.channel_transports import (
    ChannelTransportError,
    SignalCliRestConfig,
    SignalCliRestTransport,
    TelegramLongPollingTransport,
    TelegramPilotConfig,
    parse_signal_event,
    parse_telegram_update,
)
from freyja.channels import ChannelPolicyError


def test_parse_telegram_update_maps_sender_chat_text_and_attachments() -> None:
    message = parse_telegram_update(
        {
            "update_id": 1,
            "message": {
                "from": {"id": 1001},
                "chat": {"id": 2002},
                "caption": "see this",
                "photo": [
                    {"file_id": "small", "file_unique_id": "p1", "width": 10, "height": 10},
                    {"file_id": "large", "file_unique_id": "p2", "width": 100, "height": 100},
                ],
                "document": {"file_id": "doc", "file_unique_id": "d1", "file_name": "x.pdf", "mime_type": "application/pdf"},
            },
        }
    )

    assert message is not None
    assert message.channel == "telegram"
    assert message.sender == "1001"
    assert message.chat_id == "2002"
    assert message.text == "see this"
    assert [item["kind"] for item in message.attachments] == ["image", "image", "document"]


def test_parse_telegram_update_rejects_missing_sender_or_chat() -> None:
    with pytest.raises(ChannelPolicyError, match="sender or chat"):
        parse_telegram_update({"message": {"from": {"id": 1}, "text": "hello"}})


def test_parse_signal_event_maps_sender_text_and_attachments() -> None:
    message = parse_signal_event(
        {
            "envelope": {
                "sourceNumber": "+15550001002",
                "sourceUuid": "uuid-1",
                "dataMessage": {
                    "message": "review",
                    "attachments": [{"contentType": "application/pdf", "filename": "case.pdf", "id": "att-1"}],
                },
            }
        }
    )

    assert message is not None
    assert message.channel == "signal"
    assert message.sender == "+15550001002"
    assert message.chat_id == "uuid-1"
    assert message.text == "review"
    assert message.attachments == (
        {
            "kind": "attachment",
            "source": "signal",
            "content_type": "application/pdf",
            "filename": "case.pdf",
            "id": "att-1",
        },
    )


def test_parse_signal_event_ignores_non_data_messages() -> None:
    assert parse_signal_event({"envelope": {"syncMessage": {}}}) is None


def test_telegram_transport_fails_closed_without_token() -> None:
    transport = TelegramLongPollingTransport(TelegramPilotConfig(bot_token=""))

    with pytest.raises(ChannelTransportError, match="TELEGRAM_BOT_TOKEN"):
        transport.get_updates()


def test_signal_transport_fails_closed_without_registration() -> None:
    transport = SignalCliRestTransport(SignalCliRestConfig(account_number="", rest_api_url="http://signal.local"))

    with pytest.raises(ChannelTransportError, match="SIGNAL_ACCOUNT_NUMBER"):
        transport.receive()
