from __future__ import annotations

import pytest

from freyja.channel_transports import (
    ChannelTransportError,
    SignalCliRestConfig,
    SignalCliRestTransport,
    TelegramLongPollingTransport,
    TelegramPilotConfig,
    _env_int,
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


def test_parse_telegram_update_extracts_requested_agent_command() -> None:
    message = parse_telegram_update({"message": {"from": {"id": 1001}, "chat": {"id": 2002}, "text": "@cloyd check the repo"}})

    assert message is not None
    assert message.requested_agent == "cloyd"
    assert message.text == "check the repo"


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


def test_parse_signal_event_extracts_requested_agent_command() -> None:
    message = parse_signal_event(
        {
            "envelope": {
                "sourceNumber": "+15550001002",
                "sourceUuid": "uuid-1",
                "dataMessage": {"message": "/agent benedict review this"},
            }
        }
    )

    assert message is not None
    assert message.requested_agent == "benedict"
    assert message.text == "review this"


def test_parse_signal_event_ignores_non_data_messages() -> None:
    assert parse_signal_event({"envelope": {"syncMessage": {}}}) is None


def test_telegram_transport_fails_closed_without_token() -> None:
    transport = TelegramLongPollingTransport(TelegramPilotConfig(bot_token=""))

    with pytest.raises(ChannelTransportError, match="TELEGRAM_BOT_TOKEN"):
        transport.get_updates()


def test_telegram_transport_enriches_small_attachment_payloads() -> None:
    transport = TelegramLongPollingTransport(TelegramPilotConfig(bot_token="token", max_attachment_bytes=32))
    transport._request = lambda method, query=None, data=None: {  # type: ignore[method-assign]
        "ok": True,
        "result": {"file_path": "photos/file.jpg", "file_size": 5},
    }
    transport._download_file = lambda file_path: b"hello"  # type: ignore[method-assign]

    message = parse_telegram_update(
        {
            "message": {
                "from": {"id": 1001},
                "chat": {"id": 2002},
                "photo": [{"file_id": "photo", "file_unique_id": "p1", "width": 10, "height": 10}],
            }
        }
    )

    assert message is not None
    enriched = transport.enrich_attachments(message)

    assert enriched.attachments[0]["payload_status"] == "included_base64"
    assert enriched.attachments[0]["size_bytes"] == 5
    assert enriched.attachments[0]["data_base64"] == "aGVsbG8="


def test_telegram_transport_skips_oversized_attachment_payloads() -> None:
    transport = TelegramLongPollingTransport(TelegramPilotConfig(bot_token="token", max_attachment_bytes=4))
    transport._request = lambda method, query=None, data=None: {  # type: ignore[method-assign]
        "ok": True,
        "result": {"file_path": "documents/file.pdf", "file_size": 99},
    }

    message = parse_telegram_update(
        {
            "message": {
                "from": {"id": 1001},
                "chat": {"id": 2002},
                "document": {"file_id": "doc", "file_unique_id": "d1", "file_name": "x.pdf", "mime_type": "application/pdf"},
            }
        }
    )

    assert message is not None
    enriched = transport.enrich_attachments(message)

    assert enriched.attachments[0]["payload_status"] == "skipped_too_large"
    assert enriched.attachments[0]["size_bytes"] == 99
    assert enriched.attachments[0]["max_attachment_bytes"] == 4
    assert "data_base64" not in enriched.attachments[0]


def test_signal_transport_fails_closed_without_registration() -> None:
    transport = SignalCliRestTransport(SignalCliRestConfig(account_number="", rest_api_url="http://signal.local"))

    with pytest.raises(ChannelTransportError, match="SIGNAL_ACCOUNT_NUMBER"):
        transport.receive()


def test_telegram_timeout_env_parser_falls_back_on_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_LONG_POLL_TIMEOUT_SECONDS", "not-a-number")

    assert TelegramPilotConfig.from_env().timeout_seconds == 25


def test_telegram_timeout_env_parser_accepts_zero_for_one_shot_polling(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_LONG_POLL_TIMEOUT_SECONDS", "0")

    assert TelegramPilotConfig.from_env().timeout_seconds == 0


def test_env_int_rejects_non_positive_values(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_TEST_TIMEOUT", "0")
    assert _env_int("FREYJA_TEST_TIMEOUT", 25) == 25

    monkeypatch.setenv("FREYJA_TEST_TIMEOUT", "-3")
    assert _env_int("FREYJA_TEST_TIMEOUT", 25) == 25

    monkeypatch.setenv("FREYJA_TEST_TIMEOUT", "7")
    assert _env_int("FREYJA_TEST_TIMEOUT", 25) == 7
