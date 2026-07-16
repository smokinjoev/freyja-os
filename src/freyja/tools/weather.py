"""Bounded weather tool with current/forecast modes and safe fallback."""

from __future__ import annotations

import calendar
import datetime as _datetime
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from freyja.config import settings


_OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
_OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
_OPENWEATHER_MAX_FORECAST_DAYS = 5


class WeatherRequestType(StrEnum):
    CURRENT = "current"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


class WeatherRequestIntent(StrEnum):
    CURRENT = "current"
    TONIGHT = "tonight"
    TOMORROW = "tomorrow"
    WEEKDAY = "weekday"
    EXPLICIT_DATE = "explicit_date"
    FUTURE_DAYS = "future_days"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WeatherRequest:
    location: str
    request_type: WeatherRequestType
    intent: WeatherRequestIntent
    target_date: _datetime.date | None = None
    target_label: str = ""
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error_message


@dataclass(frozen=True)
class ForecastDecision:
    request_type: WeatherRequestType
    target_date: _datetime.date | None
    target_label: str
    error_message: str


def _today() -> _datetime.date:
    """Return today's date; overridable in tests via monkeypatch."""
    return _datetime.datetime.now().date()


def _sanitize_location_query(query: str) -> str:
    """Strip likely injection characters from a location query."""
    return re.sub(r"[^\w\s,\-]", "", query).strip()[:100]


def _parse_explicit_date(text: str) -> _datetime.date | None:
    """Parse ISO or slash dates (yyyy-mm-dd, mm/dd/yyyy, etc)."""
    for sep in ("-", "/"):
        try:
            if sep == "-":
                return _datetime.datetime.strptime(text, "%Y-%m-%d").date()
            else:
                return _datetime.datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            pass
    return None


def _weekday_index(name: str) -> int | None:
    """Return 0 for Monday ... 6 for Sunday, or None."""
    name = name.lower()
    for idx, day in enumerate(calendar.day_name):
        if day.lower() == name:
            return idx
    for idx, day in enumerate(calendar.day_abbr):
        if day.lower() == name:
            return idx
    return None


def _weekday_from_today(target_weekday: int, today: _datetime.date) -> _datetime.date:
    """Return the next occurrence of target_weekday on or after today."""
    delta = (target_weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + _datetime.timedelta(days=delta)


def _classify_temporal_intent(prompt: str, today: _datetime.date | None = None) -> ForecastDecision:
    """Classify weather temporal intent from a natural-language prompt.

    Returns a ForecastDecision describing whether the user asked for current
    conditions or a forecast, and for which date. Unknown/malformed dates are
    reported via ``error_message`` so callers never silently substitute current
    conditions.
    """
    lowered = prompt.lower()
    today = today or _today()

    # 1. Explicit current-conditions cues.
    current_patterns = (
        r"\bnow\b",
        r"\btoday\b",
        r"\btonight\b",
        r"\bcurrent\b",
        r"\bcurrent conditions\b",
        r"\bright now\b",
        r"\bat the moment\b",
    )
    for pattern in current_patterns:
        if re.search(pattern, lowered):
            target_label = "now"
            if "tonight" in lowered:
                target_label = "tonight"
            elif "today" in lowered:
                target_label = "today"
            return ForecastDecision(
                request_type=WeatherRequestType.CURRENT,
                target_date=today,
                target_label=target_label,
                error_message="",
            )

    # 2. Relative future days.
    match = re.search(r"\bin\s+(\d+)\s+days?\b", lowered)
    if match:
        days = int(match.group(1))
        target_date = today + _datetime.timedelta(days=days)
        if days > _OPENWEATHER_MAX_FORECAST_DAYS:
            return ForecastDecision(
                request_type=WeatherRequestType.FORECAST,
                target_date=target_date,
                target_label=f"in {days} days",
                error_message=(
                    f"Forecasts are only available up to {_OPENWEATHER_MAX_FORECAST_DAYS} days out; "
                    f"{target_date.isoformat()} is outside that range."
                ),
            )
        return ForecastDecision(
            request_type=WeatherRequestType.FORECAST,
            target_date=target_date,
            target_label=f"in {days} days",
            error_message="",
        )

    # 3. Tomorrow.
    if re.search(r"\btomorrow\b", lowered):
        target_date = today + _datetime.timedelta(days=1)
        return ForecastDecision(
            request_type=WeatherRequestType.FORECAST,
            target_date=target_date,
            target_label="tomorrow",
            error_message="",
        )

    # 4. Named weekdays (case-insensitive, robust).
    weekday_match = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lowered)
    if weekday_match:
        weekday_name = weekday_match.group(1)
        weekday_idx = _weekday_index(weekday_name)
        if weekday_idx is not None:
            target_date = _weekday_from_today(weekday_idx, today)
            delta_days = (target_date - today).days
            if delta_days > _OPENWEATHER_MAX_FORECAST_DAYS:
                return ForecastDecision(
                    request_type=WeatherRequestType.FORECAST,
                    target_date=target_date,
                    target_label=weekday_name,
                    error_message=(
                        f"Forecasts are only available up to {_OPENWEATHER_MAX_FORECAST_DAYS} days out; "
                        f"{weekday_name.capitalize()} ({target_date.isoformat()}) is outside that range."
                    ),
                )
            return ForecastDecision(
                request_type=WeatherRequestType.FORECAST,
                target_date=target_date,
                target_label=weekday_name,
                error_message="",
            )

    # 5. Explicit dates (ISO or slash).
    iso_like = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{1,2}/\d{2})\b", prompt)
    if iso_like:
        date_text = iso_like.group(1)
        target_date = _parse_explicit_date(date_text)
        if target_date is None:
            return ForecastDecision(
                request_type=WeatherRequestType.UNKNOWN,
                target_date=None,
                target_label=date_text,
                error_message=f"Could not understand the date '{date_text}'. Please use a format like 2026-07-16 or 07/16/2026.",
            )
        delta_days = (target_date - today).days
        if delta_days < 0:
            return ForecastDecision(
                request_type=WeatherRequestType.UNKNOWN,
                target_date=target_date,
                target_label=target_date.isoformat(),
                error_message="I can only look up today's or future weather. Past dates are not supported.",
            )
        if delta_days > _OPENWEATHER_MAX_FORECAST_DAYS:
            return ForecastDecision(
                request_type=WeatherRequestType.FORECAST,
                target_date=target_date,
                target_label=target_date.isoformat(),
                error_message=(
                    f"Forecasts are only available up to {_OPENWEATHER_MAX_FORECAST_DAYS} days out; "
                    f"{target_date.isoformat()} is outside that range."
                ),
            )
        if delta_days == 0:
            return ForecastDecision(
                request_type=WeatherRequestType.CURRENT,
                target_date=today,
                target_label=target_date.isoformat(),
                error_message="",
            )
        return ForecastDecision(
            request_type=WeatherRequestType.FORECAST,
            target_date=target_date,
            target_label=target_date.isoformat(),
            error_message="",
        )

    # 6. Phrases containing "forecast" but no date -> assume tomorrow (common expectation).
    if "forecast" in lowered:
        target_date = today + _datetime.timedelta(days=1)
        return ForecastDecision(
            request_type=WeatherRequestType.FORECAST,
            target_date=target_date,
            target_label="forecast",
            error_message="",
        )

    # 7. Default fall-through for bare weather requests: current conditions.
    return ForecastDecision(
        request_type=WeatherRequestType.CURRENT,
        target_date=today,
        target_label="now",
        error_message="",
    )


def _extract_location(prompt: str) -> str:
    """Heuristically extract a location from a weather prompt.

    Removes the leading weather phrase and any temporal qualifiers, returning
    the remainder as the location query. The provider geocoding step ultimately
    validates the location.
    """
    # Strip everything up to and including the first weather keyword.
    location = re.sub(
        r"^.*?\b(weather|forecast|temperature|raining|rain|snow)\b",
        "",
        prompt,
        count=1,
        flags=re.IGNORECASE,
    )

    # Remove temporal qualifiers and relative-date phrases.
    location = re.sub(r"\b(today|tonight|tomorrow|now|currently|this\s+week)\b", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\bin\s+\d+\s+days?\b|\b\d+\s+days?\b", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}/\d{1,2}/\d{2}\b", "", location)

    # Remove leading prepositions left behind by the weather phrase.
    location = re.sub(r"\b(in|at|for|on|of)\b", "", location, flags=re.IGNORECASE)
    # Drop trailing question mark if any.
    location = re.sub(r"\?$", "", location)

    cleaned = _sanitize_location_query(location)
    # If extraction wipes everything, fall back to a sanitized version of the prompt.
    if not cleaned and prompt:
        cleaned = _sanitize_location_query(prompt)
    return cleaned


def classify_weather_request(prompt: str) -> WeatherRequest:
    """Convert a natural-language weather prompt into an explicit request."""
    decision = _classify_temporal_intent(prompt)
    location = _extract_location(prompt)
    intent = WeatherRequestIntent.CURRENT
    if decision.request_type == WeatherRequestType.FORECAST:
        if decision.target_label == "tomorrow":
            intent = WeatherRequestIntent.TOMORROW
        elif decision.target_label in {"forecast"}:
            intent = WeatherRequestIntent.FORECAST
        elif re.match(r"\d{4}-\d{2}-\d{2}", decision.target_label):
            intent = WeatherRequestIntent.EXPLICIT_DATE
        elif re.match(r"in \d+ days", decision.target_label):
            intent = WeatherRequestIntent.FUTURE_DAYS
        elif decision.target_label:
            intent = WeatherRequestIntent.WEEKDAY
        else:
            intent = WeatherRequestIntent.FORECAST
    elif decision.request_type == WeatherRequestType.UNKNOWN:
        intent = WeatherRequestIntent.UNKNOWN
    return WeatherRequest(
        location=location,
        request_type=decision.request_type,
        intent=intent,
        target_date=decision.target_date,
        target_label=decision.target_label,
        error_message=decision.error_message,
    )


def _safe_disabled_response(location: str = "", target_label: str = "") -> dict[str, Any]:
    label = f" for {target_label}" if target_label else ""
    return {
        "live_data_available": False,
        "request_type": WeatherRequestType.CURRENT.value,
        "location": location,
        "target_label": target_label,
        "summary": "Live weather data is not configured.",
        "detail": (
            f"I can't look up{label} weather without an enabled live-data provider. "
            "Please check the forecast through a trusted weather service."
        ),
    }


async def get_weather(
    location: str,
    request_type: WeatherRequestType | None = None,
    target_date: _datetime.date | None = None,
    target_label: str = "",
) -> dict[str, Any]:
    """Return current weather or a forecast for ``location``.

    ``request_type`` may be ``current`` or ``forecast``. When ``forecast`` is
    requested, ``target_date`` must be a future date within the provider's
    forecast window. If the tool is disabled, unauthenticated, or the request is
    malformed, returns a safe live-data-unavailable response and never
    fabricates a forecast.
    """
    if request_type is None:
        request_type = WeatherRequestType.CURRENT

    if not settings.weather_tool_enabled or not settings.openweather_api_key:
        return _safe_disabled_response(location, target_label)

    sanitized = _sanitize_location_query(location)
    if not sanitized:
        return {
            "live_data_available": False,
            "request_type": request_type.value,
            "location": location,
            "target_label": target_label,
            "summary": "Invalid location query.",
            "detail": "Please provide a city name, such as 'Aiken, South Carolina'.",
        }

    if request_type == WeatherRequestType.FORECAST:
        if target_date is None:
            return {
                "live_data_available": False,
                "request_type": request_type.value,
                "location": sanitized,
                "target_label": target_label,
                "summary": "Forecast date missing.",
                "detail": "Please specify a date, such as 'tomorrow' or a weekday.",
            }
        delta_days = (target_date - _today()).days
        if delta_days < 0:
            return {
                "live_data_available": False,
                "request_type": request_type.value,
                "location": sanitized,
                "target_label": target_label,
                "summary": "Past date not supported.",
                "detail": "I can only look up today's or future weather.",
            }
        if delta_days > _OPENWEATHER_MAX_FORECAST_DAYS:
            return {
                "live_data_available": False,
                "request_type": request_type.value,
                "location": sanitized,
                "target_label": target_label,
                "summary": "Forecast date outside supported range.",
                "detail": (
                    f"Forecasts are only available up to {_OPENWEATHER_MAX_FORECAST_DAYS} days out."
                ),
            }
        return await _fetch_openweather_forecast(
            sanitized,
            target_date=target_date,
            target_label=target_label,
        )

    return await _fetch_openweather_current(sanitized)


async def _fetch_openweather_current(location: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                _OPENWEATHER_CURRENT_URL,
                params={
                    "q": location,
                    "appid": settings.openweather_api_key,
                    "units": "imperial",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.CURRENT.value,
            "location": location,
            "target_label": "now",
            "summary": "Weather service returned an error.",
            "detail": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.CURRENT.value,
            "location": location,
            "target_label": "now",
            "summary": "Weather service unavailable.",
            "detail": str(exc),
        }

    weather = data.get("weather", [{}])[0]
    main = data.get("main", {})
    wind = data.get("wind", {})
    dt = data.get("dt")
    observation_time = None
    if dt:
        try:
            observation_time = _datetime.datetime.fromtimestamp(dt, tz=_datetime.UTC).isoformat()
        except Exception:
            observation_time = None
    return {
        "live_data_available": True,
        "request_type": WeatherRequestType.CURRENT.value,
        "location": data.get("name", location),
        "target_label": "now",
        "summary": weather.get("main", "Unknown"),
        "description": weather.get("description", "No description"),
        "temperature_f": main.get("temp"),
        "feels_like_f": main.get("feels_like"),
        "humidity_percent": main.get("humidity"),
        "wind_mph": wind.get("speed"),
        "observation_time": observation_time,
        "raw": {
            "provider": "OpenWeatherMap",
            "endpoint": "current",
            "id": data.get("id"),
        },
    }


async def _fetch_openweather_forecast(
    location: str,
    target_date: _datetime.date,
    target_label: str,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                _OPENWEATHER_FORECAST_URL,
                params={
                    "q": location,
                    "appid": settings.openweather_api_key,
                    "units": "imperial",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": location,
            "target_label": target_label,
            "summary": "Weather service returned an error.",
            "detail": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": location,
            "target_label": target_label,
            "summary": "Weather service unavailable.",
            "detail": str(exc),
        }

    # OpenWeatherMap /forecast returns 3-hour slices for 5 days.
    slices = data.get("list", [])
    start_of_day = _datetime.datetime.combine(target_date, _datetime.datetime.min.time())
    end_of_day = start_of_day + _datetime.timedelta(days=1)
    target_slices = [
        s for s in slices
        if start_of_day <= _datetime.datetime.fromtimestamp(s.get("dt", 0), tz=_datetime.UTC).replace(tzinfo=None) < end_of_day
    ]
    if not target_slices:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": data.get("city", {}).get("name", location),
            "target_label": target_label,
            "summary": "Forecast period missing.",
            "detail": f"The weather provider did not return data for {target_label}.",
        }

    # Aggregate: high, low, most common condition.
    temps = [s.get("main", {}).get("temp") for s in target_slices if s.get("main", {}).get("temp") is not None]
    feels_likes = [s.get("main", {}).get("feels_like") for s in target_slices if s.get("main", {}).get("feels_like") is not None]
    humidities = [s.get("main", {}).get("humidity") for s in target_slices if s.get("main", {}).get("humidity") is not None]
    conditions = [s.get("weather", [{}])[0].get("main") for s in target_slices]
    descriptions = [s.get("weather", [{}])[0].get("description") for s in target_slices]
    summaries = [c for c in conditions if c]
    summary = max(set(summaries), key=summaries.count) if summaries else "Unknown"
    description = descriptions[0] if descriptions else "No description"

    return {
        "live_data_available": True,
        "request_type": WeatherRequestType.FORECAST.value,
        "location": data.get("city", {}).get("name", location),
        "target_label": target_label,
        "target_date": target_date.isoformat(),
        "summary": summary,
        "description": description,
        "high_f": max(temps) if temps else None,
        "low_f": min(temps) if temps else None,
        "avg_feels_like_f": sum(feels_likes) / len(feels_likes) if feels_likes else None,
        "humidity_percent": int(sum(humidities) / len(humidities)) if humidities else None,
        "forecast_periods": len(target_slices),
        "raw": {
            "provider": "OpenWeatherMap",
            "endpoint": "forecast",
            "city_id": data.get("city", {}).get("id"),
        },
    }


async def weather_response_text(request: WeatherRequest | str) -> str:
    """Return a human-readable weather response or safe fallback.

    Accepts either a raw prompt string (legacy convenience) or a classified
    ``WeatherRequest``.
    """
    if isinstance(request, str):
        parsed = classify_weather_request(request)
    else:
        parsed = request

    if parsed.error_message:
        return parsed.error_message

    result = await get_weather(
        location=parsed.location,
        request_type=parsed.request_type,
        target_date=parsed.target_date,
        target_label=parsed.target_label,
    )
    if not result["live_data_available"]:
        return f"{result['summary']}\n\n{result['detail']}"

    source = result["raw"].get("provider", "OpenWeatherMap")
    if result["request_type"] == WeatherRequestType.FORECAST.value:
        return (
            f"Forecast for {result['location']} {result['target_label']}:\n"
            f"{result['summary']} ({result['description']}).\n"
            f"High: {result['high_f']}°F. Low: {result['low_f']}°F.\n"
            f"Humidity: {result['humidity_percent']}%.\n"
            f"(live data from {source})"
        )
    return (
        f"Current weather for {result['location']}:\n"
        f"{result['summary']} ({result['description']}).\n"
        f"Temperature: {result['temperature_f']}°F (feels like {result['feels_like_f']}°F).\n"
        f"Humidity: {result['humidity_percent']}%.\n"
        f"Wind: {result['wind_mph']} mph.\n"
        f"(live data from {source})"
    )


_TIME_SENSITIVE_KEYWORDS = frozenset(
    {
        "weather",
        "forecast",
        "temperature",
        "rain",
        "snow",
        "storm",
        "current events",
        "news",
        "price",
        "stock",
        "score",
        "schedule",
        "flight",
        "traffic",
        "eta",
    }
)


def is_time_sensitive_query(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(kw in lowered for kw in _TIME_SENSITIVE_KEYWORDS)
