"""Tests for get_weather semantics, temporal parsing, and provider failure handling."""

from __future__ import annotations

import datetime as _datetime
import calendar
from unittest.mock import patch

import httpx
import pytest

from freyja.config import Settings, settings as _settings
from freyja.tools.weather import (
    WeatherRequestType,
    _OPENMETEO_MAX_FORECAST_DAYS,
    _classify_temporal_intent,
    _extract_location,
    classify_weather_request,
    get_weather,
    weather_response_text,
)


@pytest.fixture
def enable_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_settings, "weather_tool_enabled", True)


@pytest.fixture
def disable_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_settings, "weather_tool_enabled", False)


class TestTemporalParsing:
    def _next_weekday_today(self, weekday: int) -> _datetime.date:
        today = _datetime.date.today()
        days = (weekday - today.weekday()) % 7
        return today + _datetime.timedelta(days=days)

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
        today = _datetime.date.today()
        decision = _classify_temporal_intent("What is the weather tomorrow in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "tomorrow"
        assert decision.target_date == today + _datetime.timedelta(days=1)
        assert decision.error_message == ""

    def test_named_weekday_within_range(self):
        today = self._next_weekday_today(calendar.WEDNESDAY)
        decision = _classify_temporal_intent("What is the weather Friday in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "friday"
        assert decision.target_date == today + _datetime.timedelta(days=2)

    def test_named_weekday_outside_range(self):
        today = _datetime.date.today()
        # The next Thursday is 1 day out. To get a weekday outside the 7-day window,
        # explicitly request the date in 8 days, which the classifier routes as an explicit date.
        target = today + _datetime.timedelta(days=_OPENMETEO_MAX_FORECAST_DAYS + 1)
        decision = _classify_temporal_intent(f"What is the weather {target.isoformat()} in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_date == target
        assert decision.error_message != ""
        assert "outside" in decision.error_message.lower()

    def test_relative_days_within_range(self):
        today = _datetime.date.today()
        decision = _classify_temporal_intent("What is the weather in 3 days in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "in 3 days"
        assert decision.target_date == today + _datetime.timedelta(days=3)

    def test_relative_days_outside_range(self):
        today = _datetime.date.today()
        decision = _classify_temporal_intent("What is the weather in 8 days in Aiken?", today=today)
        assert decision.error_message != ""
        assert "outside" in decision.error_message.lower()

    def test_explicit_iso_date_within_range(self):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=2)
        decision = _classify_temporal_intent(f"What is the weather {target.isoformat()} in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_date == target

    def test_explicit_iso_date_today(self):
        today = _datetime.date.today()
        decision = _classify_temporal_intent(f"What is the weather {today.isoformat()} in Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.CURRENT

    def test_explicit_past_date_rejected(self):
        today = _datetime.date.today()
        target = today - _datetime.timedelta(days=1)
        decision = _classify_temporal_intent(f"What is the weather {target.isoformat()} in Aiken?", today=today)
        assert decision.error_message != ""
        assert "past" in decision.error_message.lower()

    def test_explicit_date_outside_range(self):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=_OPENMETEO_MAX_FORECAST_DAYS + 1)
        decision = _classify_temporal_intent(f"What is the weather {target.isoformat()} in Aiken?", today=today)
        assert decision.error_message != ""
        assert "outside" in decision.error_message.lower()

    def test_malformed_date_returns_error(self):
        today = _datetime.date.today()
        decision = _classify_temporal_intent("What is the weather 2026-02-30 in Aiken?", today=today)
        assert decision.error_message != ""
        assert "could not understand" in decision.error_message.lower()

    def test_bare_weather_defaults_current(self):
        decision = _classify_temporal_intent("What is the weather in Aiken?")
        assert decision.request_type == WeatherRequestType.CURRENT
        assert decision.target_label == "now"

    def test_forecast_no_date_defaults_tomorrow(self):
        today = _datetime.date.today()
        decision = _classify_temporal_intent("What is the weather forecast for Aiken?", today=today)
        assert decision.request_type == WeatherRequestType.FORECAST
        assert decision.target_label == "forecast"
        assert decision.target_date == today + _datetime.timedelta(days=1)


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
        today = _datetime.date.today()
        result = await get_weather(
            "Aiken, SC",
            request_type=WeatherRequestType.FORECAST,
            target_date=today + _datetime.timedelta(days=1),
            target_label="tomorrow",
        )
        assert result["live_data_available"] is False
        assert result["summary"] == "Live weather data is not configured."
        assert "tomorrow" in result["detail"].lower()


def _openmeteo_geo_response() -> dict:
    return {
        "results": [
            {
                "id": 456123,
                "name": "Aiken",
                "latitude": 33.559,
                "longitude": -81.722,
                "admin1": "South Carolina",
                "country": "United States",
            }
        ]
    }


def _openmeteo_current_response() -> dict:
    return {
        "latitude": 33.56,
        "longitude": -81.72,
        "current": {
            "time": f"{_datetime.date.today().isoformat()}T14:00",
            "temperature_2m": 72.5,
            "relative_humidity_2m": 55,
            "apparent_temperature": 74.0,
            "weather_code": 1,
            "wind_speed_10m": 5.2,
        },
    }


def _openmeteo_forecast_response(target_iso: str) -> dict:
    return {
        "latitude": 33.56,
        "longitude": -81.72,
        "daily": {
            "time": [target_iso],
            "weather_code": [0],
            "temperature_2m_max": [75.0],
            "temperature_2m_min": [58.0],
            "relative_humidity_2m_mean": [60],
        },
    }


def _mock_get(url: str, *args, **kwargs) -> httpx.Response:
    request = httpx.Request("GET", url)
    if "geocoding-api" in url:
        return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
    if "current" in kwargs.get("params", {}):
        return httpx.Response(200, json=_openmeteo_current_response(), request=request)
    return httpx.Response(200, json=_openmeteo_forecast_response((_datetime.date.today() + _datetime.timedelta(days=1)).isoformat()), request=request)


class TestGetWeatherCurrent:
    @pytest.mark.asyncio
    async def test_current_hits_forecast_endpoint(self, enable_weather):
        captured = {}

        def _capture(*args, **kwargs):
            captured["url"] = str(args[0])
            request = httpx.Request("GET", captured["url"])
            if "geocoding-api" in captured["url"]:
                return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
            return httpx.Response(200, json=_openmeteo_current_response(), request=request)

        with patch("httpx.AsyncClient.get", side_effect=_capture):
            result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is True
        assert result["request_type"] == "current"
        assert "api.open-meteo.com/v1/forecast" in captured["url"]
        assert result["temperature_f"] == 72.5
        assert result["location"] == "Aiken, South Carolina, United States"

    @pytest.mark.asyncio
    async def test_current_provider_500(self, enable_weather):
        def _bad(*args, **kwargs):
            url = str(args[0])
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(
                "500",
                request=request,
                response=httpx.Response(500, text="Internal Server Error", request=request),
            )

        with patch("httpx.AsyncClient.get", side_effect=_bad):
            result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is False
        assert "location not found" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_current_provider_timeout(self, enable_weather):
        def _timeout(*args, **kwargs):
            raise httpx.TimeoutException("timeout")

        with patch("httpx.AsyncClient.get", side_effect=_timeout):
            result = await get_weather("Aiken, SC", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is False
        assert "location not found" in result["summary"].lower()


class TestGetWeatherForecast:
    @pytest.mark.asyncio
    async def test_tomorrow_hits_forecast_endpoint(self, enable_weather, monkeypatch: pytest.MonkeyPatch):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=1)
        captured = {}

        def _capture(*args, **kwargs):
            captured["url"] = str(args[0])
            request = httpx.Request("GET", captured["url"])
            if "geocoding-api" in captured["url"]:
                return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
            return httpx.Response(200, json=_openmeteo_forecast_response(target.isoformat()), request=request)

        monkeypatch.setattr("freyja.tools.weather._today", lambda: today)
        with patch("httpx.AsyncClient.get", side_effect=_capture):
            result = await get_weather(
                "Aiken, SC",
                request_type=WeatherRequestType.FORECAST,
                target_date=target,
                target_label="tomorrow",
            )

        assert result["live_data_available"] is True
        assert result["request_type"] == "forecast"
        assert "api.open-meteo.com/v1/forecast" in captured["url"]
        assert result["target_label"] == "tomorrow"
        assert result["high_f"] == 75.0
        assert result["low_f"] == 58.0

    @pytest.mark.asyncio
    async def test_forecast_missing_period(self, enable_weather, monkeypatch: pytest.MonkeyPatch):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=1)

        def _empty_forecast(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            if "geocoding-api" in str(args[0]):
                return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
            return httpx.Response(200, json={"daily": {"time": []}}, request=request)

        monkeypatch.setattr("freyja.tools.weather._today", lambda: today)
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
    async def test_forecast_date_supported_max(self, enable_weather, monkeypatch: pytest.MonkeyPatch):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=_OPENMETEO_MAX_FORECAST_DAYS)

        def _forecast(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            if "geocoding-api" in str(args[0]):
                return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
            return httpx.Response(
                200,
                json=_openmeteo_forecast_response(target.isoformat()),
                request=request,
            )

        monkeypatch.setattr("freyja.tools.weather._today", lambda: today)
        with patch("httpx.AsyncClient.get", side_effect=_forecast):
            result = await get_weather(
                "Aiken, SC",
                request_type=WeatherRequestType.FORECAST,
                target_date=target,
                target_label="in 7 days",
            )

        assert result["live_data_available"] is True
        assert result["high_f"] == 75.0

    @pytest.mark.asyncio
    async def test_forecast_date_beyond_max(self, enable_weather, monkeypatch: pytest.MonkeyPatch):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=_OPENMETEO_MAX_FORECAST_DAYS + 1)
        async def _fake_resolve(q):
            return _openmeteo_geo_response()["results"][0]
        monkeypatch.setattr("freyja.tools.weather._resolve_location", _fake_resolve)
        monkeypatch.setattr("freyja.tools.weather._today", lambda: today)
        result = await get_weather(
            "Aiken, SC",
            request_type=WeatherRequestType.FORECAST,
            target_date=target,
            target_label="in 8 days",
        )
        assert result["live_data_available"] is False
        assert "outside" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_forecast_past_date_rejected(self, enable_weather, monkeypatch: pytest.MonkeyPatch):
        today = _datetime.date.today()
        target = today - _datetime.timedelta(days=1)
        async def _fake_resolve(q):
            return _openmeteo_geo_response()["results"][0]
        monkeypatch.setattr("freyja.tools.weather._resolve_location", _fake_resolve)
        monkeypatch.setattr("freyja.tools.weather._today", lambda: today)
        result = await get_weather(
            "Aiken, SC",
            request_type=WeatherRequestType.FORECAST,
            target_date=target,
            target_label="yesterday",
        )
        assert result["live_data_available"] is False
        assert "past" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_unknown_place_returns_safe_fallback(self, enable_weather):
        def _empty_geo(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            return httpx.Response(200, json={"results": None}, request=request)

        with patch("httpx.AsyncClient.get", side_effect=_empty_geo):
            result = await get_weather("Xylophoneburg", request_type=WeatherRequestType.CURRENT)

        assert result["live_data_available"] is False
        assert "location not found" in result["summary"].lower()


class TestResponseText:
    @pytest.mark.asyncio
    async def test_response_text_indicates_live_source(self, enable_weather):
        def _capture(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            if "geocoding-api" in str(args[0]):
                return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
            return httpx.Response(200, json=_openmeteo_current_response(), request=request)

        with patch("httpx.AsyncClient.get", side_effect=_capture):
            text = await weather_response_text("What is the weather now in Aiken, SC?")

        assert "Current weather" in text
        assert "live data from Open-Meteo" in text

    @pytest.mark.asyncio
    async def test_response_text_forecast(self, enable_weather):
        today = _datetime.date.today()
        target = today + _datetime.timedelta(days=1)

        def _capture(*args, **kwargs):
            request = httpx.Request("GET", str(args[0]))
            if "geocoding-api" in str(args[0]):
                return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
            return httpx.Response(
                200,
                json=_openmeteo_forecast_response(target.isoformat()),
                request=request,
            )

        with patch("freyja.tools.weather._today", return_value=today), patch("httpx.AsyncClient.get", side_effect=_capture):
            text = await weather_response_text("What is the weather tomorrow in Aiken, SC?")

        assert "Forecast" in text
        assert "tomorrow" in text.lower()
        assert "live data from Open-Meteo" in text

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
