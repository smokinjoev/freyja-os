"""Live, model-independent activity telemetry for the OpenCode server."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from freyja.config import settings


class OpenCodeFeedback:
    """Consume OpenCode SSE events and retain a small, safe status snapshot."""

    def __init__(self, *, stale_after_seconds: float = 90.0) -> None:
        self.stale_after_seconds = stale_after_seconds
        self._task: asyncio.Task[None] | None = None
        self._snapshot: dict[str, Any] = {
            "ok": True,
            "state": "connecting",
            "last_event_at": None,
            "last_event_type": None,
            "last_activity": None,
            "session": None,
            "connection": "starting",
        }

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="opencode-feedback")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def status(self) -> dict[str, Any]:
        result = dict(self._snapshot)
        last_event_epoch = result.pop("_last_event_epoch", None)
        if result.get("state") == "working" and last_event_epoch is not None:
            age = round(max(0.0, time.time() - float(last_event_epoch)), 1)
            result["seconds_since_last_event"] = age
            if age >= self.stale_after_seconds:
                result["state"] = "stalled"
                result["reason"] = f"No OpenCode event for {int(age)} seconds."
        return result

    async def _run(self) -> None:
        while True:
            try:
                password = Path(settings.opencode_password_file).expanduser().read_text(encoding="utf-8").strip()
                encoded = base64.b64encode(f"{settings.opencode_username}:{password}".encode("utf-8")).decode("ascii")
                headers = {"Authorization": f"Basic {encoded}", "Accept": "text/event-stream"}
                # ``/global/event`` carries server heartbeats.  Workspace
                # events carry the session text, reasoning, and tool activity
                # that a human needs to see while a coding task is running.
                url = f"{settings.opencode_base_url.rstrip('/')}/event"
                self._snapshot["connection"] = "connected"
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=10, pool=10)) as client:
                    async with client.stream(
                        "GET", url, headers=headers, params={"directory": settings.repository_root}
                    ) as response:
                        response.raise_for_status()
                        event_data: list[str] = []
                        async for line in response.aiter_lines():
                            if not line:
                                self._record(event_data)
                                event_data = []
                            elif line.startswith("data:"):
                                event_data.append(line[5:].lstrip())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._snapshot["connection"] = "reconnecting"
                self._snapshot["connection_error"] = str(exc)
                await asyncio.sleep(3)

    def _record(self, lines: list[str]) -> None:
        if not lines:
            return
        try:
            event = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict):
            return
        # OpenCode currently wraps each server-sent event in a ``payload``
        # envelope.  Keep accepting a bare event as well for compatibility.
        if isinstance(event.get("payload"), dict):
            event = event["payload"]
        event_type = str(event.get("type") or event.get("event") or "unknown")
        properties = event.get("properties") if isinstance(event.get("properties"), dict) else event
        now = datetime.now(timezone.utc).isoformat()
        # A transport heartbeat proves the subscription is alive, but says
        # nothing about a coding job.  Never let it erase useful job state.
        if event_type.lower() == "server.heartbeat":
            self._snapshot["connection"] = "connected"
            self._snapshot["last_heartbeat_at"] = now
            return
        session = properties.get("sessionID") or properties.get("sessionId") or event.get("sessionID")
        activity = _activity(event_type, properties)
        state = _state(event_type)
        self._snapshot.update(
            {
                "ok": True,
                "state": state,
                "last_event_at": now,
                "_last_event_epoch": time.time(),
                "last_event_type": event_type,
                "last_activity": activity,
                "session": session or self._snapshot.get("session"),
                "connection": "connected",
            }
        )
        self._snapshot.pop("connection_error", None)


def _state(event_type: str) -> str:
    lowered = event_type.lower()
    if lowered.startswith(("server.", "global.", "workspace.")):
        return "idle"
    if "idle" in lowered or "completed" in lowered or "ended" in lowered or "success" in lowered:
        return "idle"
    if "failed" in lowered or "error" in lowered:
        return "error"
    return "working"


def _activity(event_type: str, properties: dict[str, Any]) -> str:
    lowered = event_type.lower()
    part = properties.get("part") if isinstance(properties.get("part"), dict) else {}
    part_type = str(part.get("type") or "").lower()
    if part_type == "reasoning":
        return "reasoning"
    if part_type.startswith("tool"):
        tool = part.get("tool") or (part.get("state") or {}).get("title")
        return f"tool: {tool}" if tool else "tool activity"
    if part_type == "step-start":
        return "starting next step"
    if "tool" in lowered:
        tool = properties.get("tool") or properties.get("name") or properties.get("title")
        return f"tool: {tool}" if tool else "tool activity"
    if "reasoning" in lowered:
        return "reasoning"
    if "text" in lowered:
        return "writing response"
    if "retry" in lowered:
        return "retrying"
    if "idle" in lowered:
        return "idle"
    return event_type
