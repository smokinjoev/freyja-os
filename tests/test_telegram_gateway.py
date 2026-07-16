from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from connectors.telegram.config import TelegramSettings
from connectors.telegram.gateway import RejectionReason, TelegramGateway
from connectors.telegram.models import TelegramInboundUpdate, TelegramMessage, TelegramUser, TelegramChat


def _make_request() -> httpx.Request:
    return httpx.Request("POST", "http://127.0.0.1:8000/route")


def _ok_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data, request=_make_request())


def _error_response(status: int, payload: dict | None = None, text: str = "") -> httpx.Response:
    body = payload or {}
    return httpx.Response(status, json=body, request=_make_request(), text=text)


def _make_update(
    update_id: int,
    user_id: int,
    chat_id: int,
    chat_type: str,
    text: str,
    *,
    username: str | None = None,
    is_bot: bool = False,
    channel_post: bool = False,
) -> TelegramInboundUpdate:
    message = TelegramMessage(
        message_id=update_id,
        from_user=TelegramUser(id=user_id, is_bot=is_bot, username=username),
        chat=TelegramChat(id=chat_id, type=chat_type),
        date=0,
        text=text,
    )
    if channel_post:
        return TelegramInboundUpdate(update_id=update_id, channel_post=message)
    return TelegramInboundUpdate(update_id=update_id, message=message)


@pytest.fixture
def settings(tmp_path) -> TelegramSettings:
    return TelegramSettings(
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_allowed_user_ids="123456",
        telegram_direct_messages_only=True,
        telegram_smith_read_only_enabled=True,
        telegram_state_dir=str(tmp_path / "telegram"),
        freyja_director_url="http://127.0.0.1:8000",
    )


@pytest.fixture
async def gateway(settings) -> AsyncIterator[TelegramGateway]:
    gw = TelegramGateway(settings=settings)
    yield gw
    await gw.close()


@pytest.mark.asyncio
async def test_authorized_user_accepted(gateway):
    update = _make_update(1, 123456, 123456, "private", "Hello Freyja")
    mock_response = _ok_response({
        "provider": "ollama",
        "model": "qwen2.5:1.5b",
        "response": "Local auto hello",
        "reason": "routine request defaults to local",
        "request_id": "req-001",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await gateway.handle(update)

    assert result is not None
    assert result.success is True
    assert result.text == "Local auto hello\n\n(agent: Freyja, provider: ollama, model: qwen2.5:1.5b)"
    assert result.chat_id == 123456
    mock_post.assert_awaited_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"prompt": "Hello Freyja", "provider": "auto"}


@pytest.mark.asyncio
async def test_unknown_user_rejected(gateway):
    update = _make_update(1, 999999, 999999, "private", "Hello Freyja")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()


@pytest.mark.asyncio
async def test_username_cannot_authorize(gateway):
    update = _make_update(1, 999999, 999999, "private", "Hello Freyja", username="operator")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()


@pytest.mark.asyncio
async def test_direct_message_accepted(gateway):
    update = _make_update(1, 123456, 123456, "private", "Hello Freyja")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "OK"})
        result = await gateway.handle(update)
    assert result is not None
    assert result.success is True


@pytest.mark.asyncio
async def test_group_rejected(gateway):
    update = _make_update(1, 123456, 1, "group", "Hello group")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()


@pytest.mark.asyncio
async def test_supergroup_rejected(gateway):
    update = _make_update(1, 123456, 1, "supergroup", "Hello supergroup")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()


@pytest.mark.asyncio
async def test_channel_rejected(gateway):
    update = _make_update(1, 123456, 1, "channel", "Hello channel", channel_post=True)
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()


@pytest.mark.asyncio
async def test_ordinary_text_routes_to_freyja(gateway):
    update = _make_update(1, 123456, 123456, "private", "What is 2+2?")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({
            "response": "The sum is 4.",
            "provider": "ollama",
            "model": "qwen2.5:1.5b",
        })
        result = await gateway.handle(update)

    assert result is not None
    assert "Freyja" in result.text
    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_smith_routes_only_to_smith(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.agent_smith_enabled", True)
    monkeypatch.setattr("freyja.config.settings.agent_smith_read_only_enabled", True)
    update = _make_update(1, 123456, 123456, "private", "/smith status")

    mock_response = _ok_response({
        "message": "Repository is clean on main.",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await gateway.handle(update)

    assert result is not None
    assert "read-only" in result.text.lower()
    assert "Repository is clean on main." in result.text
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["objective"] == "repository status"


@pytest.mark.asyncio
async def test_smith_remains_read_only(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.agent_smith_enabled", True)
    monkeypatch.setattr("freyja.config.settings.agent_smith_read_only_enabled", True)
    update = _make_update(1, 123456, 123456, "private", "/smith write a file")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({
            "message": "Read-only write request refused.",
            "status": "needs_attention",
        })
        result = await gateway.handle(update)

    assert result is not None
    assert result.success is True
    args, kwargs = mock_post.call_args
    url = args[0] if args else kwargs.get("url", "")
    assert url.endswith("/agents/smith/read-only")
    assert "objective" in kwargs["json"]


@pytest.mark.asyncio
async def test_write_requests_through_smith_denied_by_policy(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.agent_smith_enabled", True)
    monkeypatch.setattr("freyja.config.settings.agent_smith_read_only_enabled", True)
    update = _make_update(1, 123456, 123456, "private", "/smith commit changes")

    def _mock_post(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        assert url.endswith("/agents/smith/read-only")
        return _ok_response({
            "message": "Objective classified as prohibited_write; read-only execution refused.",
            "status": "needs_attention",
        })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_mock_post) as mock_post:
        result = await gateway.handle(update)

    assert result is not None
    assert "read-only" in result.text.lower()
    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_smith_disabled_returns_safe_error(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.agent_smith_enabled", False)
    update = _make_update(1, 123456, 123456, "private", "/smith status")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "disabled" in result.text.lower()


@pytest.mark.asyncio
async def test_whoami(gateway):
    update = _make_update(1, 123456, 123456, "private", "/whoami")
    result = await gateway.handle(update)
    assert result is not None
    assert "123456" in result.text
    assert "private" in result.text


@pytest.mark.asyncio
async def test_status_command(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.agent_smith_enabled", False)
    monkeypatch.setattr("freyja.config.settings.agent_smith_read_only_enabled", False)
    monkeypatch.setattr("freyja.config.settings.agent_smith_write_pilot_enabled", False)

    responses = {
        "http://127.0.0.1:8000/health": _ok_response({"status": "healthy"}),
        "http://127.0.0.1:8000/ollama/health": _ok_response({"ollama_reachable": True}),
        "http://127.0.0.1:8000/openrouter/health": _ok_response({"key_configured": True}),
    }

    async def _mock_get(url: str, *args, **kwargs):
        return responses.get(url, _ok_response({}))

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=_mock_get):
        result = await gateway.handle(_make_update(1, 123456, 123456, "private", "/status"))

    assert result is not None
    assert "Freyja status" in result.text
    assert "Director: reachable" in result.text
    assert "Ollama: healthy" in result.text
    assert "OpenRouter: configured" in result.text


@pytest.mark.asyncio
async def test_health_command(gateway):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_ok_response({"status": "healthy"})):
        result = await gateway.handle(_make_update(1, 123456, 123456, "private", "/health"))
    assert result is not None
    assert "healthy" in result.text.lower()


@pytest.mark.asyncio
async def test_models_command(gateway):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_ok_response({"models": ["qwen2.5:1.5b"]})):
        result = await gateway.handle(_make_update(1, 123456, 123456, "private", "/models"))
    assert result is not None
    assert "qwen2.5:1.5b" in result.text or "Configured models:" in result.text


@pytest.mark.asyncio
async def test_unknown_command_returns_help(gateway):
    update = _make_update(1, 123456, 123456, "private", "/unknown")
    result = await gateway.handle(update)
    assert result is not None
    assert "Unknown command" in result.text
    assert "/help" in result.text


@pytest.mark.asyncio
async def test_help_command(gateway):
    update = _make_update(1, 123456, 123456, "private", "/help")
    result = await gateway.handle(update)
    assert result is not None
    assert "/status" in result.text
    assert "/whoami" in result.text
    assert "/smith" in result.text


@pytest.mark.asyncio
async def test_rejection_logs_do_not_contain_message_bodies(gateway, caplog):
    caplog.set_level(logging.INFO)
    update = _make_update(1, 999999, 999999, "private", "secret plan details")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    for record in caplog.records:
        assert "secret plan details" not in record.message


@pytest.mark.asyncio
async def test_token_absent_from_logs_and_error_responses(gateway, caplog):
    caplog.set_level(logging.INFO)
    update = _make_update(1, 999999, 999999, "private", "hi")
    result = await gateway.handle(update)
    assert result is not None
    assert "test-token" not in result.text
    for record in caplog.records:
        assert "test-token" not in record.message


@pytest.mark.asyncio
async def test_offset_persistence(gateway, tmp_path):
    update = _make_update(1, 123456, 123456, "private", "Hello")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok_response({"response": "Hi"})):
        await gateway.handle(update)

    offset_file = Path(gateway._offset_file)
    assert offset_file.exists()
    data = json.loads(offset_file.read_text(encoding="utf-8"))
    assert data["offset"] == 1

    new_gateway = TelegramGateway(settings=gateway._settings)
    assert new_gateway._last_offset == 1
    await new_gateway.close()


@pytest.mark.asyncio
async def test_duplicate_update_handling(gateway):
    update = _make_update(1, 123456, 123456, "private", "Hello")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok_response({"response": "Hi"})) as mock_post:
        first = await gateway.handle(update)
        second = await gateway.handle(update)

    assert first is not None
    assert first.success is True
    assert second is None
    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_restart_recovery_loads_offset(gateway, tmp_path):
    update = _make_update(42, 123456, 123456, "private", "Hello")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok_response({"response": "Hi"})):
        await gateway.handle(update)

    new_gateway = TelegramGateway(settings=gateway._settings)
    assert new_gateway._last_offset == 42
    await new_gateway.close()


@pytest.mark.asyncio
async def test_telegram_failure_does_not_stop_director(gateway):
    # The gateway uses separate httpx calls; a Telegram poll failure should not crash Director.
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
        replies = await gateway.poll_updates()
    assert replies == []


@pytest.mark.asyncio
async def test_retry_backoff_on_poll_failure(gateway):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("failed")):
        replies = await gateway.poll_updates()
    assert replies == []


@pytest.mark.asyncio
async def test_disabled_gateway_rejects_all():
    disabled = TelegramGateway(settings=TelegramSettings(telegram_enabled=False))
    update = _make_update(1, 123456, 123456, "private", "Hello")
    result = await disabled.handle(update)
    assert result is None
    await disabled.close()


@pytest.mark.asyncio
async def test_anonymous_sender_rejected(gateway):
    message = TelegramMessage(
        message_id=1,
        from_user=None,
        chat=TelegramChat(id=123456, type="private"),
        date=0,
        text="Hello",
    )
    update = TelegramInboundUpdate(update_id=1, message=message)
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()


def test_settings_allowed_user_id_set():
    s = TelegramSettings(telegram_allowed_user_ids="111, 222 , 333, bad, 444")
    assert s.allowed_user_id_set == {111, 222, 333, 444}


def test_settings_allowed_user_id_set_empty():
    s = TelegramSettings()
    assert s.allowed_user_id_set == set()
