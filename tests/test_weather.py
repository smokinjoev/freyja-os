"""Tests for get_weather semantics, temporal parsing, and provider failure handling."""

from __future__ import annotations

import datetime as _datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.config import Settings, settings as _settings
from freyja.tools.weather import (
    WeatherRequestType,
    _OPENWEATHER_MAX_FORECAST_DAYS,
    _classify_temporal_intent,
    _extract_location,
    classify_weather_request,
    get_weather,
    weather_response_text,
)


@pytest.fixture
def enable_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_settings, "weather_tool_enabled", True)
    monkeypatch.setattr(_settings, "openweather_api_key", "fake-key")


@pytest.fixture
def disable_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_settings, "weather_tool_enabled", False)
    monkeypatch.setattr(_settings, "openweather_api_key", "")


class TestTemporalParsing:
    def test_now_is_current(self):
        decision = _classify_temporal_intent("What is the weather now in Aiken?")
        assert decision.request_type == WeatherRequestType.CURRENT
        assert decision.target_label == "now"

    def test_today_is_current(self):
        decision = _classify_temporal_intent("What is the weather today in Aiken?")
        assert decision.request_type == WeatherRequestType.CURRENT
        assert decision.target_label == "today"

    def test_tonight_is_current(self):
        decision = _classify_temporal_intent("What is the weather tonight in Aiken?")
        assert decision.request_type == WeatherRequestType.CURRENT
        assert decision.target_label == "tonight"

    def test_tomorrow_is_forecast(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather tomorrow in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "tomorrow"
        assert decision.target_date == _datetime.date(2026, 7, 16)
        assert decision.error_message == ""

    def test_named_weekday_within_range(self):
        today = _datetime.date(2026, 7, 15)  # Wednesday
        decision = _classify_temporal_intent("What is the weather Friday in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "friday"
        assert decision.target_date == _datetime.date(2026, 7, 17)

    def test_named_weekday_outside_range(self):
        today = _datetime.date(2026, 7, 15)  # Wednesday
        decision = _classify_temporal_intent("What is the weather next Tuesday in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.error_message != ""
        assert "outside" in decision.error_message.lower()

    def test_relative_days_within_range(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather in 3 days in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "in 3 days"
        assert decision.target_date == _datetime.date(2026, 7, 18)

    def test_relative_days_outside_range(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather in 7 days in Aiken?", today=today)
        assert decision.error_message != ""
        assert "outside" in decision.error_message.lower()

    def test_explicit_iso_date_within_range(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather 2026-07-17 in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_date == _datetime.date(2026, 7, 17)

    def test_explicit_iso_date_today(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather 2026-07-15 in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.CURRENT

    def test_explicit_past_date_rejected(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather 2026-07-10 in Aiken?", today=today)
        assert decision.error_message != ""
        assert "past" in decision.error_message.lower()

    def test_explicit_date_outside_range(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather 2026-07-25 in Aiken?", today=today)
        assert decision.error_message != ""
        assert "outside" in decision.error_message.lower()

    def test_malformed_date_returns_error(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather 2026-02-30 in Aiken?", today=today)
        assert decision.error_message != ""
        assert "could not understand" in decision.error_message.lower()

    def test_bare_weather_defaults_current(self):
        decision = _classify_temporal_intent("What is the weather in Aiken?")
        assert decision.request_type == WeatherRequestType.CURRENT
        assert decision.target_label == "now"

    def test_forecast_no_date_defaults_tomorrow(self):
        today = _datetime.date(2026, 7, 15)
        decision = _classify_temporal_intent("What is the weather forecast for Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "forecast"
        assert decision.target_date == _datetime.date(2026, 7, 16)


class TestLocationExtraction:
    def test_extract_location_basic(self):
        loc = _extract_location("What is the weather in Aiken, South Carolina?")
        assert "Aiken" in loc and "South Carolina" in loc

    def test_extract_location_tomorrow(self):
        loc = _extract_location("What is the weather tomorrow in Aiken, SC?")
        assert "Aiken" in loc and "SC" in loc
        assert "tomorrow" not in loc.lower()

    def test_extract_location_named_weekday(self):
        loc = _extract_location("Weather Friday in Aiken?")
        assert loc.strip() == "Aiken"
        assert "friday" not in loc.lower()

    def test_extract_location_relative_days(self):
        loc = _extract_location("Weather in 3 days in Aiken?")
        assert loc.strip() == "Aiken"
        assert "3" not in loc
        assert "days" not in loc.lower()


class TestGetWeatherDisabled:
    @pytest.mark.asyncio
    async def test_current_disabled_returns_safe_response(self, disable_weather):
        result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)
        assert result["live_data_available"] is False
        assert result["request_type"] == "current"
        assert "not configured" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_tomorrow_disabled_returns_safe_response(self, disable_weather):
        today = _datetime.date(2026, 7, 15)
        result = await get_weather(
            "Aiken, SC",
            request_type=WeatherRequestType.FORECAST,
            target_date=today + _datetime.timedelta(days=1),
            target_label="tomorrow",
        )
        assert result["live_data_available"] is False
        assert result["summary"] == "Live weather data is not configured."
        assert "tomorrow" in result["detail"].lower()


class TestGetWeatherCurrent:
    @pytest.mark.asyncio
    async def test_current_hits_current_endpoint(self, enable_weather):
        captured = {}

        def _capture_current(*args, **kwargs):
            captured["url"] = str(args[0])
            request = httpx.Request("GET", captured["url"])
            response_data = {
                "name": "Aiken",
                "weather": [{"main": "Clear", "description": "clear sky"}],
                "main": {"temp": 76, "feels_like": 75, "humidity": 58},
                "wind": {"speed": 5},
                "dt": 1784188800,
            }
            return httpx.Response(200, json=response_data, request=request)

        with patch("httpx.AsyncClient.get", side_effect=_capture_current):
            result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is True
        assert result["request_type"] == "current"
        assert "weather" in captured["url"]
        assert "forecast" not in captured["url"]

    @pytest.mark.asyncio
    async def test_current_provider_401(self, enable_weather):
        def _bad(*args, **kwargs):
            url = str(args[0])
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(
                "401",
                request=request,
                response=httpx.Response(401, text="Unauthorized", request=request),
            )

        with patch("httpx.AsyncClient.get", side_effect=_bad):
            result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is False
        assert result["detail"] == "HTTP 401"

    @pytest.mark.asyncio
    async def test_current_provider_timeout(self, enable_weather):
        def _timeout(*args, **kwargs):
            raise httpx.TimeoutException("timeout")

        with patch("httpx.AsyncClient.get", side_effect=_timeout):
            result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is False
        assert "unavailable" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_current_missing_api_key(self, monkeypatch):
        monkeypatch.setattr(_settings, "weather_tool_enabled", True)
        monkeypatch.setattr(_settings, "openweather_api_key", "")
        result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)
        assert result["live_data_available"] is False
        assert "not configured" in result["summary"].lower()


class TestGetWeatherForecast:
    @pytest.mark.asyncio
    async def test_tomorrow_hits_forecast_endpoint(self, enable_weather):
        today = _datetime.date(2026, 7, 15)
        target = today + _datetime.timedelta(days=1)
        captured = {}

        def _capture_forecast(*args, **kwargs):
            captured["url"] = str(args[0])
            request = httpx.Request("GET", captured["url"])
            response_data = {
                "city": {"name": "Aiken", "id": 12345},
                "list": [
                    {
                        "dt": 1784241600,
                        "main": {"temp": 78, "feels_like": 77, "humidity": 55},
                        "weather": [{"main": "Clear", "description": "clear sky"}],
                    }
                ],
            }
            return httpx.Response(200, json=response_data, request=request)

        with patch("httpx.AsyncClient.get", side_effect=_capture_forecast):
            result = await get_weather(
                "Aiken, SC",
                request_type=WeatherRequestType.FORECAST,
                target_date=target,
                target_label="tomorrow",
            )

        assert result["live_data_available"] is True
        assert result["request_type"] == "forecast"
        assert "forecast" in captured["url"]
        assert result["target_label"] == "tomorrow"
        assert result["high_f"] == 78
        assert result["low_f"] == 78

    @pytest.mark.asyncio
    async def test_forecast_missing_period(self, enable_weather):
        today = _datetime.date(2026, 7, 15)
        target = today + _datetime.timedelta(days=1)

        def _empty_forecast(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            return httpx.Response(200, json={"city": {"name": "Aiken"}, "list": []}, request=request)

        with patch("httpx.AsyncClient.get", side_effect=_empty_forecast):
            result = await get_weather(
                "Aiken, SC",
                request_type=WeatherRequestType.FORECAST,
                target_date=target,
                target_label="tomorrow",
            )

        assert result["live_data_available"] is False
        assert "missing" in result["summary"].lower() or "did not return" in result["detail"].lower()

    @pytest.mark.asyncio
    async def test_forecast_date_supported_max(self, enable_weather):
        today = _datetime.date(2026, 7, 15)
        target = today + _datetime.timedelta(days=_OPENWEATHER_MAX_FORECAST_DAYS)

        def _forecast(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            return httpx.Response(
                200,
                json={
                    "city": {"name": "Aiken"},
                    "list": [
                        {
                            "dt": int(_datetime.datetime.combine(target, _datetime.datetime.min.time()).timestamp()) + 3600,
                            "main": {"temp": 80, "feels_like": 79, "humidity": 50},
                            "weather": [{"main": "Sunny", "description": "sunny"}],
                        }
                    ],
                },
                request=request,
            )

        with patch("httpx.AsyncClient.get", side_effect=_forecast):
            result = await get_weather(
                "Aiken, SC",
                request_type=WeatherRequestType.FORECAST,
                target_date=target,
                target_label="in 5 days",
            )

        assert result["live_data_available"] is True
        assert result["high_f"] == 80

    @pytest.mark.asyncio
    async def test_forecast_date_beyond_max(self, enable_weather):
        today = _datetime.date(2026, 7, 15)
        target = today + _datetime.timedelta(days=_OPENWEATHER_MAX_FORECAST_DAYS + 1)
        result = await get_weather(
            "Aiken, SC",
            request_type=WeatherRequestType.FORECAST,
            target_date=target,
            target_label="in 6 days",
        )
        assert result["live_data_available"] is False
        assert "outside" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_forecast_past_date_rejected(self, enable_weather):
        today = _datetime.date(2026, 7, 15)
        target = today - _datetime.timedelta(days=1)
        result = await get_weather(
            "Aiken, SC",
            request_type=WeatherRequestType.FORECAST,
            target_date=target,
            target_label="yesterday",
        )
        assert result["live_data_available"] is False
        assert "past" in result["summary"].lower()


class TestResponseText:
    @pytest.mark.asyncio
    async def test_response_text_indicates_live_source(self, enable_weather):
        def _current(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            return httpx.Response(
                200,
                json={
                    "name": "Aiken",
                    "weather": [{"main": "Clear", "description": "clear sky"}],
                    "main": {"temp": 76, "feels_like": 75, "humidity": 58},
                    "wind": {"speed": 5},
                    "dt": 1784188800,
                },
                request=request,
            )

        with patch("httpx.AsyncClient.get", side_effect=_current):
            text = await weather_response_text("What is the weather now in Aiken, SC?")

        assert "Current weather" in text
        assert "live data from OpenWeatherMap" in text

    @pytest.mark.asyncio
    async def test_response_text_forecast(self, enable_weather):
        today = _datetime.date(2026, 7, 15)

        def _forecast(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            return httpx.Response(
                200,
                json={
                    "city": {"name": "Aiken"},
                    "list": [
                        {
                            "dt": 1784241600,
                            "main": {"temp": 78, "feels_like": 77, "humidity": 55},
                            "weather": [{"main": "Clear", "description": "clear sky"}],
                        }
                    ],
                },
                request=request,
            )

        with patch("freyja.tools.weather._today", return_value=today), patch("httpx.AsyncClient.get", side_effect=_forecast):
            text = await weather_response_text("What is the weather tomorrow in Aiken, SC?")

        assert "Forecast" in text
        assert "tomorrow" in text.lower()
        assert "live data from OpenWeatherMap" in text

    @pytest.mark.asyncio
    async def test_response_text_disabled_never_fabricates(self, disable_weather):
        text = await weather_response_text("What is the weather tomorrow in Aiken, SC?")
        assert "not configured" in text.lower()
        assert "sunny" not in text.lower()
        assert "75" not in text


class TestClassificationIntegration:
    def test_classify_current_request(self):
        req = classify_weather_request("What is the weather now in Aiken?")
        assert req.is_valid
        assert req.request_type == WeatherRequestType.CURRENT
        assert req.target_label == "now"
        assert "Aiken" in req.location

    def test_classify_tomorrow_request(self):
        req = classify_weather_request("What is the weather tomorrow in Aiken?")
        assert req.is_valid
        assert req.request_type == WeatherRequestType.FORECAST
        assert req.target_label == "tomorrow"

    def test_classify_outside_range_request(self):
        req = classify_weather_request("What is the weather in 10 days in Aiken?")
        assert not req.is_valid
        assert "outside" in req.error_message.lower()

    def test_tomorrow_never_invokes_current_mode(self):
        req = classify_weather_request("What is the weather tomorrow in Aiken?")
        assert req.request_type == WeatherRequestType.FORECAST
        assert req.target_date is not None


class TestModelPolicyStillHolds:
    def test_router_min_chat_capability(self):
        from freyja.router import _meets_min_chat_capability

        assert _meets_min_chat_capability("qwen2.5:7b")
        assert not _meets_min_chat_capability("qwen2.5:1.5b")

    def test_default_freyja_model_is_7b(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_CHAT_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_CLASSIFICATION_MODEL", raising=False)
        s = Settings(_env_file=None)
        assert s.ollama_model == "qwen2.5:7b"
        assert s.ollama_chat_model == "qwen2.5:7b"
        assert s.ollama_classification_model == "qwen2.5:1.5b"
