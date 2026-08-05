from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from connectors.telegram.config import TelegramSettings, configured_telegram_settings
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
        telegram_person_user_id=123456,
        telegram_direct_messages_only=True,
        telegram_smith_read_only_enabled=True,
        telegram_state_dir=str(tmp_path / "telegram"),
        freyja_director_url="http://127.0.0.1:8000",
    )


@pytest.fixture
async def gateway(settings) -> AsyncIterator[TelegramGateway]:
    gw = TelegramGateway(settings=settings)
    gw._record_heartbeat()
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
    assert result.text == "Local auto hello"
    assert "(agent: Freyja, provider:" not in result.text
    assert result.chat_id == 123456
    mock_post.assert_awaited_once()
    _, kwargs = mock_post.call_args
    assert "Your name is Freyja" in kwargs["json"]["prompt"]
    assert kwargs["json"]["prompt"].endswith("Hello Freyja")
    assert kwargs["json"]["provider"] == "auto"
    assert kwargs["json"]["tools_required"] is False
    assert kwargs["json"]["conversation_id"].startswith("telegram:freyja:")
    assert "123456" not in kwargs["json"]["conversation_id"]
    assert kwargs["headers"]["x-freyja-client-subject"] == "agent:freyja"
    assert kwargs["headers"]["x-freyja-account-owner"] == "person:joe"


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
    assert result.text == "The sum is 4."
    assert "(agent: Freyja, provider:" not in result.text
    mock_post.assert_awaited_once()
    _, kwargs = mock_post.call_args
    assert "Your name is Freyja" in kwargs["json"]["prompt"]
    assert kwargs["json"]["prompt"].endswith("What is 2+2?")
    assert kwargs["json"]["provider"] == "auto"
    assert kwargs["json"]["tools_required"] is False
    assert kwargs["json"]["conversation_id"].startswith("telegram:freyja:")


@pytest.mark.asyncio
async def test_benedict_routes_with_isolated_identity_and_model(tmp_path):
    benedict = TelegramGateway(settings=TelegramSettings(
        telegram_enabled=True,
        telegram_bot_token="benedict-test-token",
        telegram_allowed_user_ids="654321",
        telegram_person_user_id=654321,
        telegram_state_dir=str(tmp_path / "benedict"),
        telegram_agent_name="benedict",
        telegram_person_name="beth",
        telegram_agent_display_name="Benedict",
        telegram_model="benedict-qwen2.5:7b",
    ))
    update = _make_update(1, 654321, 654321, "private", "Hello Benedict")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hello Beth."})
        result = await benedict.handle(update)
    assert result is not None
    assert result.text == "Hello Beth."
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["model"] == "benedict-qwen2.5:7b"
    assert "Your name is Benedict" in kwargs["json"]["prompt"]
    assert "Beth's persistent personal agent" in kwargs["json"]["prompt"]
    assert "Iris is infrastructure" in kwargs["json"]["prompt"]
    assert "Never address the person as Iris" in kwargs["json"]["prompt"]
    assert kwargs["json"]["prompt"].endswith("Hello Benedict")
    assert kwargs["json"]["conversation_id"].startswith("telegram:benedict:")
    assert "654321" not in kwargs["json"]["conversation_id"]
    assert kwargs["headers"]["x-freyja-client-subject"] == "agent:benedict"
    assert kwargs["headers"]["x-freyja-account-owner"] == "person:beth"
    assert kwargs["headers"]["x-freyja-person-id"] == "beth"
    await benedict.close()


def test_benedict_environment_creates_separate_bot_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "freyja-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "111")
    monkeypatch.setenv("TELEGRAM_STATE_DIR", str(tmp_path / "freyja"))
    monkeypatch.setenv("TELEGRAM_BENEDICT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BENEDICT_BOT_TOKEN", "benedict-token")
    monkeypatch.setenv("TELEGRAM_BENEDICT_ALLOWED_USER_IDS", "222")
    monkeypatch.setenv("TELEGRAM_BENEDICT_PERSON_USER_ID", "222")
    settings = configured_telegram_settings()
    assert [item.telegram_agent_name for item in settings] == ["freyja", "benedict"]
    assert settings[0].allowed_user_id_set == {111}
    assert settings[1].allowed_user_id_set == {222}
    assert settings[1].telegram_person_name == "beth"
    assert settings[1].telegram_person_user_id == 222
    assert settings[0].telegram_bot_token != settings[1].telegram_bot_token


@pytest.mark.asyncio
async def test_allowlisted_tester_cannot_impersonate_agent_owner(tmp_path):
    benedict = TelegramGateway(settings=TelegramSettings(
        telegram_enabled=True,
        telegram_bot_token="benedict-test-token",
        telegram_allowed_user_ids="111,222",
        telegram_person_user_id=222,
        telegram_state_dir=str(tmp_path / "benedict"),
        telegram_agent_name="benedict",
        telegram_person_name="beth",
        telegram_agent_display_name="Benedict",
    ))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        result = await benedict.handle(_make_update(1, 111, 111, "private", "Hello Benedict"))

    assert result is not None
    assert result.success is False
    assert "not authorized" in result.text.lower()
    mock_post.assert_not_awaited()

    whoami = await benedict.handle(_make_update(2, 111, 111, "private", "/whoami"))
    assert whoami is not None
    assert "111" in whoami.text
    await benedict.close()


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
async def test_weather_query_returns_safe_fallback_when_unconfigured(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.weather_tool_enabled", False)
    update = _make_update(1, 123456, 123456, "private", "What is the weather tomorrow in Aiken, South Carolina?")
    result = await gateway.handle(update)
    assert result is not None
    assert "live" in result.text.lower() or "configured" in result.text.lower()
    assert "weather" in result.text.lower()


@pytest.mark.asyncio
async def test_weather_now_invokes_current_conditions(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.weather_tool_enabled", True)

    captured_request = {}
    async def _capture(request):
        captured_request["request"] = request
        return "Current weather for Aiken: sunny, 76°F."

    with patch("connectors.telegram.gateway.weather_response_text", new_callable=AsyncMock, side_effect=_capture):
        update = _make_update(1, 123456, 123456, "private", "What is the weather now in Aiken, South Carolina?")
        result = await gateway.handle(update)

    assert result is not None
    assert captured_request["request"].request_type.value == "current"
    assert captured_request["request"].target_label == "now"


@pytest.mark.asyncio
async def test_weather_tomorrow_invokes_forecast(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.weather_tool_enabled", True)

    captured_request = {}
    async def _capture(request):
        captured_request["request"] = request
        return "Forecast for Aiken tomorrow: sunny."

    with patch("connectors.telegram.gateway.weather_response_text", new_callable=AsyncMock, side_effect=_capture):
        update = _make_update(1, 123456, 123456, "private", "What is the weather tomorrow in Aiken, South Carolina?")
        result = await gateway.handle(update)

    assert result is not None
    assert captured_request["request"].request_type.value == "forecast"
    assert captured_request["request"].target_label == "tomorrow"


@pytest.mark.asyncio
async def test_weather_unsupported_future_date_returns_limitation(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.weather_tool_enabled", True)

    update = _make_update(1, 123456, 123456, "private", "What is the weather in 10 days in Aiken, South Carolina?")
    result = await gateway.handle(update)
    assert result is not None
    assert "outside" in result.text.lower() or "range" in result.text.lower()


@pytest.mark.asyncio
async def test_weather_query_invokes_tool_when_enabled(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.weather_tool_enabled", True)

    with patch("connectors.telegram.gateway.weather_response_text", new_callable=AsyncMock, return_value="Weather for Aiken: sunny, 75°F."):
        update = _make_update(1, 123456, 123456, "private", "What is the weather in Aiken, South Carolina?")
        result = await gateway.handle(update)

    assert result is not None
    assert ("75°F" in result.text or "Aiken" in result.text)


@pytest.mark.asyncio
async def test_time_sensitive_non_weather_returns_unavailable(gateway, monkeypatch):
    monkeypatch.setattr("freyja.config.settings.weather_tool_enabled", False)
    update = _make_update(1, 123456, 123456, "private", "What is the current stock price of Apple?")
    result = await gateway.handle(update)
    assert result is not None
    assert result.success is False
    assert "live data" in result.text.lower()


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
async def test_disabled_gateway_rejects_all(tmp_path):
    disabled = TelegramGateway(
        settings=TelegramSettings(
            telegram_enabled=False,
            telegram_state_dir=str(tmp_path / "telegram"),
        )
    )
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


def test_settings_allowed_user_id_set_empty(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "")
    s = TelegramSettings()
    assert s.allowed_user_id_set == set()


def _read_heartbeat(gateway: TelegramGateway) -> dict:
    return json.loads(gateway._heartbeat_file.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_heartbeat_updates_during_empty_poll(gateway, monkeypatch):
    monkeypatch.setattr(gateway, "_HEARTBEAT_INTERVAL_SECONDS", 0.0)
    before = _read_heartbeat(gateway)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_ok_response({"ok": True, "result": []})):
        replies = await gateway.poll_updates()

    assert replies == []
    after = _read_heartbeat(gateway)
    assert after["last_poll_status"] == "ok"
    assert after["last_poll_timestamp"] >= before.get("timestamp", 0)
    assert after["timestamp"] >= before.get("timestamp", 0)


@pytest.mark.asyncio
async def test_heartbeat_reflects_polling_error(gateway, monkeypatch):
    monkeypatch.setattr(gateway, "_HEARTBEAT_INTERVAL_SECONDS", 0.0)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("failed")):
        replies = await gateway.poll_updates()

    assert replies == []
    hb = _read_heartbeat(gateway)
    assert hb["last_poll_status"] != "ok"


@pytest.mark.asyncio
async def test_heartbeat_file_permissions(gateway, monkeypatch):
    monkeypatch.setattr(gateway, "_HEARTBEAT_INTERVAL_SECONDS", 0.0)
    gateway._record_heartbeat(poll_status="ok")
    mode = gateway._heartbeat_file.stat().st_mode & 0o777
    assert mode == 0o600


@pytest.mark.asyncio
async def test_heartbeat_contains_no_secrets(gateway):
    hb = _read_heartbeat(gateway)
    hb_text = json.dumps(hb)
    assert "test-token" not in hb_text
    assert "user_id" not in hb_text.lower()
    assert "hello" not in hb_text.lower()
    assert "update_id" not in hb_text.lower()


def test_stale_heartbeat_detection(gateway, tmp_path):
    old_timestamp = time.time() - 120
    stale_data = {
        "timestamp": old_timestamp,
        "enabled": True,
        "direct_messages_only": True,
        "allowed_user_count": 1,
        "token_configured": True,
        "last_poll_status": "ok",
        "last_poll_timestamp": old_timestamp,
    }
    gateway._heartbeat_file.write_text(json.dumps(stale_data), encoding="utf-8")

    def is_stale(path: Path, threshold: float = 90.0) -> bool:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (time.time() - data["timestamp"]) > threshold

    assert is_stale(gateway._heartbeat_file)


class TestTelegramToolLoop:
    @pytest.fixture
    def tool_settings(self, tmp_path) -> TelegramSettings:
        return TelegramSettings(
            telegram_enabled=True,
            telegram_bot_token="test-token",
            telegram_allowed_user_ids="123456",
            telegram_person_user_id=123456,
            telegram_direct_messages_only=True,
            telegram_smith_read_only_enabled=False,
            telegram_tools_enabled=True,
            telegram_state_dir=str(tmp_path / "telegram"),
            freyja_director_url="http://127.0.0.1:8000",
        )

    @pytest.fixture
    async def tool_gateway(self, tool_settings) -> AsyncIterator[TelegramGateway]:
        gw = TelegramGateway(settings=tool_settings)
        gw._record_heartbeat()
        yield gw
        await gw.close()

    @pytest.mark.asyncio
    async def test_telegram_tool_use_enabled(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "What host am I on?")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": "You are on Iris.",
            "reason": "tool request",
            "tool_results": [{"tool_name": "hostname", "success": True, "hostname": "iris"}],
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert result.text == "You are on Iris."
        assert "<freyja_tool_call>" not in result.text
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["tools_required"] is True

    @pytest.mark.asyncio
    async def test_telegram_tool_use_disabled(self, tool_gateway, monkeypatch):
        monkeypatch.setattr(tool_gateway._settings, "telegram_tools_enabled", False)
        update = _make_update(1, 123456, 123456, "private", "What host am I on?")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": "I cannot use tools right now.",
            "reason": "routine request",
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert result.text == "I cannot use tools right now."
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["tools_required"] is False

    @pytest.mark.asyncio
    async def test_telegram_normal_no_tool_conversation(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Thanks, that helped!")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": "You're welcome!",
            "reason": "routine request",
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert result.text == "You're welcome!"
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["tools_required"] is False

    @pytest.mark.asyncio
    async def test_telegram_failed_tool_response_not_exposed(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Check disk usage.")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": "Tool 'disk_usage' failed (tool_error): Tool execution failed.",
            "reason": "tool request",
            "tool_results": [{"tool_name": "disk_usage", "success": False, "error_category": "tool_error"}],
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert "failed" in result.text.lower()
        assert "stdout" not in result.text.lower()
        assert "stderr" not in result.text.lower()
        assert "<freya_tool_call>" not in result.text

    @pytest.mark.asyncio
    async def test_telegram_malformed_output_never_reaches_user(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Run diagnostics.")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": 'Tool returned <freyja_tool_call>{"invalid": true}</freyja_tool_call>',
            "reason": "tool request",
            "tool_results": [{"tool_name": "hostname", "success": True}],
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert "<freyja_tool_call>" not in result.text
        assert '{"invalid": true}' not in result.text

    @pytest.mark.asyncio
    async def test_telegram_legitimate_json_response_passes_unchanged(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Give me a JSON example.")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": 'Here is an example: {"tool_name": "example_tool", "enabled": true}.',
            "reason": "routine request",
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert '{"tool_name": "example_tool", "enabled": true}' in result.text
        assert "<freyja_tool_call>" not in result.text

    @pytest.mark.asyncio
    async def test_telegram_code_block_with_braces_passes_unchanged(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Show me a C struct.")
        code_block = "```c\nstruct Tool { char tool_name[32]; int enabled; };\n```"
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": code_block,
            "reason": "routine request",
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert "struct Tool" in result.text
        assert "char tool_name[32]" in result.text
        assert result.text.count("```") == 2

    @pytest.mark.asyncio
    async def test_telegram_incomplete_nested_multiple_tool_markers(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Nested markers.")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": (
                "start "
                '<freyja_tool_call>{"tool_name":"a"}</freyja_tool_call>'
                " middle "
                '<freyja_tool_call>{"tool_name":"b"}</freyja_tool_call>'
                " end"
            ),
            "reason": "tool request",
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert "<freyja_tool_call>" not in result.text
        assert "start" in result.text
        assert "middle" in result.text
        assert "end" in result.text
        assert '"tool_name"' not in result.text

    @pytest.mark.asyncio
    async def test_telegram_casual_chat_cannot_bypass_tool_registry(self, tool_gateway, monkeypatch):
        monkeypatch.setattr(tool_gateway._settings, "telegram_tools_enabled", True)
        monkeypatch.setattr("freyja.config.settings.tools_enabled", True)
        update = _make_update(1, 123456, 123456, "private", "Thanks!")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": "You're welcome!",
            "reason": "routine request",
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert result.text == "You're welcome!"
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["tools_required"] is False

    @pytest.mark.asyncio
    async def test_telegram_timeout_through_gateway(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "What time is it?")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("request timed out")
            result = await tool_gateway.handle(update)

        assert result is not None
        assert result.success is False
        assert "process" in result.text.lower() or "later" in result.text.lower()

    @pytest.mark.asyncio
    async def test_telegram_iteration_limit_not_exposed(self, tool_gateway):
        update = _make_update(1, 123456, 123456, "private", "Loop forever.")
        mock_response = _ok_response({
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "response": "Tool iteration limit reached without a final answer.",
            "reason": "tool request",
            "tool_results": [
                {"tool_name": "hostname", "success": True},
                {"tool_name": "hostname", "success": True},
            ],
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await tool_gateway.handle(update)

        assert result is not None
        assert "iteration limit" in result.text.lower()
        assert "stdout" not in result.text.lower()
