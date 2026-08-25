from __future__ import annotations

import asyncio
import hmac
import socket
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from connectors.imessage.config import IMessageSettings
from connectors.imessage.models import IMessageReply
from connectors.imessage.transport import IMessageTransport
from freyja.calendar.models import CalendarEvent
from freyja.calendar.providers import AppleCalendarProvider
from freyja.config import settings
from freyja.identity.apple_contacts import load_apple_contacts
from freyja.macagent import MacAgentHealth, MacAgentOperationRequest, MacAgentOperationResult

MACAGENT_CAPABILITIES = [
    "apple.messages.read",
    "apple.messages.send",
    "apple.calendar.read",
    "apple.calendar.write",
    "apple.contacts.read",
    "apple.shortcuts.run",
]

app = FastAPI(
    title="Freyja Iris MacAgent",
    version="0.1.0",
    description="Authenticated Apple-native capability boundary for Freyja Iris.",
)


@app.get("/health")
async def health(authorization: str = Header(default="")) -> dict[str, Any]:
    _require_token(authorization)
    return MacAgentHealth(
        enabled=True,
        reachable=True,
        authenticated=True,
        host=socket.gethostname() or "iris",
        capabilities=MACAGENT_CAPABILITIES,
    ).model_dump(mode="json")


@app.post("/capabilities/{capability}")
async def invoke_capability(
    capability: str,
    request: MacAgentOperationRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    started = time.monotonic()
    _require_token(authorization)
    if capability != request.capability:
        raise HTTPException(status_code=400, detail="capability path does not match request")
    if request.director_authorized is not True:
        return _result(request, ok=False, error="director authorization required", started=started)
    if _requires_approval(request) and request.approval_granted is not True:
        return _result(request, ok=False, error="director approval required", started=started)
    try:
        output = await _dispatch_operation(request)
    except Exception as exc:
        return _result(request, ok=False, error=str(exc), started=started)
    return _result(request, ok=True, output=output, error=None, started=started)


async def _dispatch_operation(request: MacAgentOperationRequest) -> dict[str, Any]:
    if request.capability == "apple.calendar.read":
        return await _calendar_read(request)
    if request.capability == "apple.calendar.write":
        return await _calendar_write(request)
    if request.capability == "apple.messages.read":
        return await _messages_read(request)
    if request.capability == "apple.messages.send":
        return await _messages_send(request)
    if request.capability == "apple.contacts.read":
        return await _contacts_read(request)
    if request.capability == "apple.shortcuts.run":
        return await _shortcuts_run(request)
    raise ValueError(f"unsupported capability: {request.capability}")


def _requires_approval(request: MacAgentOperationRequest) -> bool:
    return request.capability in {
        "apple.calendar.write",
        "apple.messages.send",
        "apple.shortcuts.run",
    }


async def _calendar_read(request: MacAgentOperationRequest) -> dict[str, Any]:
    if request.operation != "list_events":
        raise ValueError("unsupported apple.calendar.read operation")
    provider = AppleCalendarProvider(timeout_seconds=settings.macagent_timeout_seconds)
    events = await provider.list_events(
        calendar_ids=_string_list(request.arguments.get("calendar_selectors") or request.arguments.get("calendar_ids")),
        start=_required_datetime(request.arguments.get("start"), "start"),
        end=_required_datetime(request.arguments.get("end"), "end"),
    )
    return {"events": [_calendar_event_payload(event) for event in events]}


async def _calendar_write(request: MacAgentOperationRequest) -> dict[str, Any]:
    provider = AppleCalendarProvider(timeout_seconds=settings.macagent_timeout_seconds)
    if request.operation == "create_event":
        event = CalendarEvent(
            event_id="",
            calendar_id=_required_string(request.arguments.get("calendar_selector"), "calendar_selector"),
            title=_required_string(request.arguments.get("title"), "title"),
            start=_required_datetime(request.arguments.get("start"), "start"),
            end=_required_datetime(request.arguments.get("end"), "end"),
            attendee_ids=tuple(_string_list(request.arguments.get("attendee_ids"))),
            location=_optional_string(request.arguments.get("location")),
            description=_optional_string(request.arguments.get("description")),
        )
        created = await provider.create_event(event)
        return {"event": _calendar_event_payload(created)}
    if request.operation == "modify_event":
        event = await provider.modify_event(
            _required_string(request.arguments.get("event_id"), "event_id"),
            dict(request.arguments.get("updates") or {}),
        )
        return {"event": _calendar_event_payload(event) if event else None}
    if request.operation == "delete_event":
        deleted = await provider.delete_event(_required_string(request.arguments.get("event_id"), "event_id"))
        return {"deleted": deleted}
    raise ValueError("unsupported apple.calendar.write operation")


async def _messages_read(request: MacAgentOperationRequest) -> dict[str, Any]:
    if request.operation != "recent_messages":
        raise ValueError("unsupported apple.messages.read operation")
    limit = _positive_int(request.arguments.get("limit"), default=20, maximum=100)
    transport = IMessageTransport(IMessageSettings())
    messages = await transport.recent_messages()
    return {"messages": [message.model_dump(mode="json") for message in messages[-limit:]]}


async def _messages_send(request: MacAgentOperationRequest) -> dict[str, Any]:
    if request.operation != "send_reply":
        raise ValueError("unsupported apple.messages.send operation")
    reply = IMessageReply(
        chat_id=_positive_int(request.arguments.get("chat_id"), default=0, maximum=2**63 - 1),
        text=_required_string(request.arguments.get("text"), "text", max_length=4000),
    )
    transport = IMessageTransport(IMessageSettings())
    await transport.send(reply)
    return {"sent": True, "chat_id": reply.chat_id}


async def _contacts_read(request: MacAgentOperationRequest) -> dict[str, Any]:
    if request.operation != "list_contacts":
        raise ValueError("unsupported apple.contacts.read operation")
    include_identifiers = request.arguments.get("include_identifiers") is True
    limit = _positive_int(request.arguments.get("limit"), default=100, maximum=1000)
    people = await asyncio.to_thread(
        load_apple_contacts,
        timeout_seconds=int(max(1, settings.macagent_timeout_seconds)),
        request_access=False,
    )
    return {"contacts": [person.to_dict(include_identifiers=include_identifiers) for person in people[:limit]]}


async def _shortcuts_run(request: MacAgentOperationRequest) -> dict[str, Any]:
    if request.operation != "run_shortcut":
        raise ValueError("unsupported apple.shortcuts.run operation")
    shortcut_name = _required_string(request.arguments.get("name"), "name", max_length=120)
    input_text = _optional_string(request.arguments.get("input"), max_length=8000)
    command = ["/usr/bin/shortcuts", "run", shortcut_name]
    if input_text is not None:
        command.extend(["--input-path", "-"])
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(input_text.encode("utf-8") if input_text is not None else None),
        timeout=settings.macagent_timeout_seconds,
    )
    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"shortcuts command failed with status {process.returncode}")
    return {"stdout": stdout.decode("utf-8", errors="replace"), "shortcut": shortcut_name}


def _require_token(authorization: str) -> None:
    expected = settings.macagent_token.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="macagent token not configured")
    scheme, _, supplied = authorization.partition(" ")
    authorized = scheme.lower() == "bearer" and bool(supplied) and hmac.compare_digest(supplied, expected)
    if not authorized:
        raise HTTPException(
            status_code=401,
            detail="MacAgent authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _result(
    request: MacAgentOperationRequest,
    *,
    ok: bool,
    output: dict[str, Any] | None = None,
    error: str | None,
    started: float,
) -> dict[str, Any]:
    return MacAgentOperationResult(
        ok=ok,
        capability=request.capability,
        operation=request.operation,
        output=output or {},
        error=error,
        duration_ms=int((time.monotonic() - started) * 1000),
    ).model_dump(mode="json")


def _calendar_event_payload(event: CalendarEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "calendar_id": event.calendar_id,
        "title": event.title,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "attendee_ids": list(event.attendee_ids),
        "location": event.location,
        "description": event.description,
        "metadata": dict(event.metadata),
    }


def _required_datetime(value: Any, field: str):
    from datetime import datetime

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601 datetime") from exc


def _required_string(value: Any, field: str, *, max_length: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    return text


def _optional_string(value: Any, *, max_length: int = 1000) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string field must be a string")
    if len(value) > max_length:
        raise ValueError("optional string field is too long")
    return value


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list of strings")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("expected a list of non-empty strings")
        result.append(item.strip())
    return result


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    if value is None:
        value = default
    if not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError(f"expected integer between 1 and {maximum}")
    return value
