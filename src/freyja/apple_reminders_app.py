from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from freyja.reminders.apple_eventkit import run_eventkit


app = FastAPI(title="Freyja Apple Reminders Bridge", docs_url=None, redoc_url=None)


def _authorize(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("FREYJA_APPLE_REMINDERS_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


class ReminderPayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    due: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    list_id: str | None = None


@app.get("/health")
def health(_: None = Depends(_authorize)) -> dict[str, Any]:
    return {"status": "ok", **run_eventkit("status")}


@app.post("/permissions/request")
def request_permissions(_: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("request-access", request_access=True, timeout_seconds=120)


@app.get("/lists")
def lists(_: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("lists")


@app.get("/reminders")
def list_reminders(
    list_id: list[str] | None = None,
    include_completed: bool = False,
    _: None = Depends(_authorize),
) -> dict[str, Any]:
    return run_eventkit("list", {"list_ids": list_id or [], "include_completed": include_completed})


@app.post("/reminders")
def create_reminder(payload: ReminderPayload, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("create", payload.model_dump(exclude_none=True))


@app.post("/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: str, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("complete", {"reminder_id": reminder_id})


@app.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: str, _: None = Depends(_authorize)) -> dict[str, Any]:
    return run_eventkit("delete", {"reminder_id": reminder_id})
