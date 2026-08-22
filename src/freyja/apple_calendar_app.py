from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from freyja.calendar.apple_eventkit import run_eventkit


app = FastAPI(title="Freyja Apple Calendar Bridge", docs_url=None, redoc_url=None)


def _authorize(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("FREYJA_APPLE_CALENDAR_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


class EventPayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    start: str
    end: str
    calendar_id: str | None = None
    location: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=4000)


class EventUpdate(BaseModel):
    event_id: str = Field(min_length=1)
    updates: dict[str, Any]


@app.get("/health")
def health(_: None = Depends(_authorize)) -> dict[str, Any]:
    return {"status": "ok", **run_eventkit("status")}


@app.get("/calendars")
def calendars(_: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("calendars")


@app.post("/permissions/request")
def request_permissions(_: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("request-access", request_access=True, timeout_seconds=120)


@app.get("/events")
def list_events(start: str, end: str, calendar_id: list[str] | None = None, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("list", {"start": start, "end": end, "calendar_ids": calendar_id or []})


@app.get("/events/{event_id}")
def get_event(event_id: str, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("get", {"event_id": event_id})


@app.post("/events")
def create_event(payload: EventPayload, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("create", payload.model_dump(exclude_none=True))


@app.patch("/events")
def modify_event(payload: EventUpdate, _: None = Depends(_authorize)) -> dict[str, Any]:
    allowed = {key: value for key, value in payload.updates.items() if key in {"title", "start", "end", "location", "description"}}
    return run_eventkit("modify", {"event_id": payload.event_id, **allowed})


@app.delete("/events/{event_id}")
def delete_event(event_id: str, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("delete", {"event_id": event_id})
