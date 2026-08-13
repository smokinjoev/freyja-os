"""Bounded weather tool with current/forecast modes and safe fallback.

Provider: Open-Meteo (https://open-meteo.com/)
* No API key required.
* Place-name lookup via Open-Meteo Geocoding API.
* Current and forecast data via Open-Meteo Forecast API.
"""

from __future__ import annotations

import calendar
import datetime as _datetime
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from freyja.config import settings


_OPENMETEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_OPENMETEO_MAX_FORECAST_DAYS = 7
_HTTP_TIMEOUT_SECONDS = 15.0


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


async def _resolve_location(query: str) -> dict[str, Any] | None:
    """Resolve a place name to a single Open-Meteo geocoding result.

    Returns the first matching result or None if the query is unknown or
    ambiguous. Uses bounded HTTP timeouts and a fixed provider endpoint.
    The geocoding API matches best on the primary place name, so if a query
    containing a comma returns no results we retry with just the leading token.
    """
    candidates = [_sanitize_location_query(query)]
    leading = query.split(",")[0].strip()
    if leading and leading != candidates[0]:
        candidates.append(_sanitize_location_query(leading))

    for name in candidates:
        if not name:
            continue
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _OPENMETEO_GEOCODING_URL,
                    params={"name": name, "count": 1, "language": "en", "format": "json"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            continue
        results = data.get("results") or []
        if results:
            return results[0]
    return None


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
        if days > _OPENMETEO_MAX_FORECAST_DAYS:
            return ForecastDecision(
                request_type=WeatherRequestType.FORECAST,
                target_date=target_date,
                target_label=f"in {days} days",
                error_message=(
                    f"Forecasts are only available up to {_OPENMETEO_MAX_FORECAST_DAYS} days out; "
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
            if delta_days > _OPENMETEO_MAX_FORECAST_DAYS:
                return ForecastDecision(
                    request_type=WeatherRequestType.FORECAST,
                    target_date=target_date,
                    target_label=weekday_name,
                    error_message=(
                        f"Forecasts are only available up to {_OPENMETEO_MAX_FORECAST_DAYS} days out; "
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
        if delta_days > _OPENMETEO_MAX_FORECAST_DAYS:
            return ForecastDecision(
                request_type=WeatherRequestType.FORECAST,
                target_date=target_date,
                target_label=target_date.isoformat(),
                error_message=(
                    f"Forecasts are only available up to {_OPENMETEO_MAX_FORECAST_DAYS} days out; "
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

    Removes the leading weather phrase, helper verbs, and any temporal
    qualifiers, returning the remainder as the location query. The provider
    geocoding step ultimately validates the location.
    """
    # Strip everything up to and including the first weather keyword.
    location = re.sub(
        r"^.*?\b(weather|forecast|temperature|raining|rain|snow)\b",
        "",
        prompt,
        count=1,
        flags=re.IGNORECASE,
    )
    location = re.sub(
        r"\b(?:and|,)\s+(?:what\s+|which\s+|how\s+many\s+)?(?:lights?|light\s+status|home\s+assistant|homeassistant|devices?|switches?).*$",
        "",
        location,
        flags=re.IGNORECASE,
    )

    # Remove helper verbs and question fragments commonly left in front of the location.
    location = re.sub(r"\b(is|will|be|are|does|do|did|can|could|would|should)\b", "", location, flags=re.IGNORECASE)
    # Remove temporal qualifiers and relative-date phrases.
    location = re.sub(r"\b(today|tonight|tomorrow|now|currently|this\s+week)\b", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\bin\s+\d+\s+days?\b|\b\d+\s+days?\b", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}/\d{1,2}/\d{2}\b", "", location)

    # Remove leading/trailing prepositions left behind by the weather phrase.
    location = re.sub(r"\b(in|at|for|on|of)\b", "", location, flags=re.IGNORECASE)
    # Drop trailing question mark if any.
    location = re.sub(r"\?$", "", location)

    cleaned = _sanitize_location_query(location)
    if cleaned.lower() in {"weather", "forecast", "temperature", "outside", "lights", "light status", "lights status"}:
        return ""
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

    if not settings.weather_tool_enabled:
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

    resolved = await _resolve_location(sanitized)
    if resolved is None:
        return {
            "live_data_available": False,
            "request_type": request_type.value,
            "location": sanitized,
            "target_label": target_label,
            "summary": "Location not found.",
            "detail": "I couldn't find that place. Please try a city name like 'Aiken, South Carolina' or 'Madrid, Spain'.",
        }

    display_location = _display_name(resolved)

    if request_type == WeatherRequestType.FORECAST:
        if target_date is None:
            return {
                "live_data_available": False,
                "request_type": request_type.value,
                "location": display_location,
                "target_label": target_label,
                "summary": "Forecast date missing.",
                "detail": "Please specify a date, such as 'tomorrow' or a weekday.",
            }
        delta_days = (target_date - _today()).days
        if delta_days < 0:
            return {
                "live_data_available": False,
                "request_type": request_type.value,
                "location": display_location,
                "target_label": target_label,
                "summary": "Past date not supported.",
                "detail": "I can only look up today's or future weather.",
            }
        if delta_days > _OPENMETEO_MAX_FORECAST_DAYS:
            return {
                "live_data_available": False,
                "request_type": request_type.value,
                "location": display_location,
                "target_label": target_label,
                "summary": "Forecast date outside supported range.",
                "detail": (
                    f"Forecasts are only available up to {_OPENMETEO_MAX_FORECAST_DAYS} days out."
                ),
            }
        return await _fetch_openmeteo_forecast(
            resolved,
            target_date=target_date,
            target_label=target_label,
        )

    return await _fetch_openmeteo_current(resolved)


def _display_name(result: dict[str, Any]) -> str:
    """Build a human-readable location name from a geocoding result."""
    parts = [
        result.get("name"),
        result.get("admin1"),
        result.get("country"),
    ]
    return ", ".join(str(p) for p in parts if p)


async def _fetch_openmeteo_forecast(
    result: dict[str, Any],
    target_date: _datetime.date,
    target_label: str,
) -> dict[str, Any]:
    """Fetch daily forecast from Open-Meteo for the resolved location."""
    try:
        lat = float(result["latitude"])
        lon = float(result["longitude"])
    except (KeyError, TypeError, ValueError):
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": _display_name(result),
            "target_label": target_label,
            "summary": "Location coordinates unavailable.",
            "detail": "Geocoding succeeded but did not return valid coordinates.",
        }

    today = _today()
    delta_days = (target_date - today).days
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _OPENMETEO_FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "auto",
                    "forecast_days": max(delta_days + 2, 3),
                    "models": "best_match",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": _display_name(result),
            "target_label": target_label,
            "summary": "Weather service returned an error.",
            "detail": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": _display_name(result),
            "target_label": target_label,
            "summary": "Weather service unavailable.",
            "detail": str(exc),
        }

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    if not dates:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": _display_name(result),
            "target_label": target_label,
            "summary": "Forecast period missing.",
            "detail": f"The weather provider did not return data for {target_label}.",
        }

    target_iso = target_date.isoformat()
    if target_iso not in dates:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.FORECAST.value,
            "location": _display_name(result),
            "target_label": target_label,
            "summary": "Forecast date unavailable.",
            "detail": f"The weather provider did not return data for {target_label}.",
        }

    idx = dates.index(target_iso)
    weather_code = daily.get("weather_code", [None] * len(dates))[idx]
    high = daily.get("temperature_2m_max", [None] * len(dates))[idx]
    low = daily.get("temperature_2m_min", [None] * len(dates))[idx]
    humidity = daily.get("relative_humidity_2m_mean", [None] * len(dates))[idx]

    summary, description = _openmeteo_weather_description(weather_code)

    return {
        "live_data_available": True,
        "request_type": WeatherRequestType.FORECAST.value,
        "location": _display_name(result),
        "target_label": target_label,
        "target_date": target_iso,
        "summary": summary,
        "description": description,
        "high_f": high,
        "low_f": low,
        "humidity_percent": int(humidity) if humidity is not None else None,
        "forecast_periods": 1,
        "raw": {
            "provider": "Open-Meteo",
            "endpoint": "forecast",
            "latitude": lat,
            "longitude": lon,
            "weather_code": weather_code,
        },
    }


async def _fetch_openmeteo_current(result: dict[str, Any]) -> dict[str, Any]:
    """Fetch current conditions from Open-Meteo for the resolved location."""
    try:
        lat = float(result["latitude"])
        lon = float(result["longitude"])
    except (KeyError, TypeError, ValueError):
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.CURRENT.value,
            "location": _display_name(result),
            "target_label": "now",
            "summary": "Location coordinates unavailable.",
            "detail": "Geocoding succeeded but did not return valid coordinates.",
        }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _OPENMETEO_FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "auto",
                    "forecast_days": 1,
                    "models": "best_match",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.CURRENT.value,
            "location": _display_name(result),
            "target_label": "now",
            "summary": "Weather service returned an error.",
            "detail": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        return {
            "live_data_available": False,
            "request_type": WeatherRequestType.CURRENT.value,
            "location": _display_name(result),
            "target_label": "now",
            "summary": "Weather service unavailable.",
            "detail": str(exc),
        }

    current = data.get("current", {})
    weather_code = current.get("weather_code")
    summary, description = _openmeteo_weather_description(weather_code)
    observation_time = None
    iso_time = current.get("time")
    if iso_time:
        try:
            observation_time = _datetime.datetime.fromisoformat(str(iso_time)).isoformat()
        except Exception:
            observation_time = None

    return {
        "live_data_available": True,
        "request_type": WeatherRequestType.CURRENT.value,
        "location": _display_name(result),
        "target_label": "now",
        "summary": summary,
        "description": description,
        "temperature_f": current.get("temperature_2m"),
        "feels_like_f": current.get("apparent_temperature"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_mph": current.get("wind_speed_10m"),
        "observation_time": observation_time,
        "raw": {
            "provider": "Open-Meteo",
            "endpoint": "forecast",
            "latitude": lat,
            "longitude": lon,
            "weather_code": weather_code,
        },
    }


_OPENMETEO_WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear", "clear sky"),
    1: ("Mainly clear", "mainly clear"),
    2: ("Partly cloudy", "partly cloudy"),
    3: ("Overcast", "overcast"),
    45: ("Fog", "fog"),
    48: ("Fog", "depositing rime fog"),
    51: ("Drizzle", "light drizzle"),
    53: ("Drizzle", "moderate drizzle"),
    55: ("Drizzle", "dense drizzle"),
    56: ("Freezing drizzle", "light freezing drizzle"),
    57: ("Freezing drizzle", "dense freezing drizzle"),
    61: ("Rain", "slight rain"),
    63: ("Rain", "moderate rain"),
    65: ("Rain", "heavy rain"),
    66: ("Freezing rain", "light freezing rain"),
    67: ("Freezing rain", "heavy freezing rain"),
    71: ("Snow", "slight snow"),
    73: ("Snow", "moderate snow"),
    75: ("Snow", "heavy snow"),
    77: ("Snow grains", "snow grains"),
    80: ("Rain showers", "slight rain showers"),
    81: ("Rain showers", "moderate rain showers"),
    82: ("Rain showers", "violent rain showers"),
    85: ("Snow showers", "slight snow showers"),
    86: ("Snow showers", "heavy snow showers"),
    95: ("Thunderstorm", "thunderstorm"),
    96: ("Thunderstorm", "thunderstorm with slight hail"),
    99: ("Thunderstorm", "thunderstorm with heavy hail"),
}


def _openmeteo_weather_description(code: int | None) -> tuple[str, str]:
    """Map an Open-Meteo weather code to a (summary, description) pair."""
    if code is None:
        return ("Unknown", "No description")
    return _OPENMETEO_WEATHER_CODES.get(code, ("Unknown", f"weather code {code}"))


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

    source = result["raw"].get("provider", "Open-Meteo")
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
