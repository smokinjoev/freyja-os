from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Protocol

import httpx

from freyja.reminders.models import Reminder, ReminderList


class ReminderProvider(Protocol):
    async def lists(self) -> list[ReminderList]: ...

    async def list_reminders(
        self,
        *,
        list_ids: list[str],
        include_completed: bool,
    ) -> list[Reminder]: ...

    async def create_reminder(self, reminder: Reminder) -> Reminder: ...

    async def complete_reminder(self, reminder_id: str) -> Reminder | None: ...

    async def delete_reminder(self, reminder_id: str) -> bool: ...


class InMemoryReminderProvider:
    def __init__(
        self,
        reminders: list[Reminder] | None = None,
        lists: list[ReminderList] | None = None,
    ) -> None:
        self._lists = {item.list_id: item for item in (lists or [ReminderList("default", "Reminders")])}
        self._reminders = {item.reminder_id: item for item in reminders or []}

    async def lists(self) -> list[ReminderList]:
        return list(self._lists.values())

    async def list_reminders(self, *, list_ids: list[str], include_completed: bool) -> list[Reminder]:
        requested = set(list_ids)
        return sorted(
            [
                reminder
                for reminder in self._reminders.values()
                if (not requested or reminder.list_id in requested)
                and (include_completed or not reminder.completed)
            ],
            key=lambda item: (item.completed, item.due or datetime.max, item.title.lower()),
        )

    async def create_reminder(self, reminder: Reminder) -> Reminder:
        list_id = reminder.list_id or "default"
        created = replace(
            reminder,
            reminder_id=reminder.reminder_id or f"reminder-{uuid.uuid4()}",
            list_id=list_id,
            provider="memory",
        )
        self._reminders[created.reminder_id] = created
        return created

    async def complete_reminder(self, reminder_id: str) -> Reminder | None:
        reminder = self._reminders.get(reminder_id)
        if reminder is None:
            return None
        updated = replace(reminder, completed=True)
        self._reminders[reminder_id] = updated
        return updated

    async def delete_reminder(self, reminder_id: str) -> bool:
        return self._reminders.pop(reminder_id, None) is not None


class AppleReminderProvider:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url or not token:
            raise ValueError("Apple Reminders bridge URL and token are required")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.request(method, f"{self._base_url}{path}", headers=headers, **kwargs)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Apple Reminders bridge returned an invalid response")
        return payload

    async def lists(self) -> list[ReminderList]:
        payload = await self._request("GET", "/lists")
        return [_list_from_bridge(item) for item in payload.get("lists", [])]

    async def list_reminders(self, *, list_ids: list[str], include_completed: bool) -> list[Reminder]:
        params: list[tuple[str, str | bool]] = [("include_completed", include_completed)]
        params.extend(("list_id", value) for value in list_ids)
        payload = await self._request("GET", "/reminders", params=params)
        return [_reminder_from_bridge(item) for item in payload.get("reminders", [])]

    async def create_reminder(self, reminder: Reminder) -> Reminder:
        payload = await self._request("POST", "/reminders", json=_reminder_to_bridge(reminder))
        created = _reminder_from_bridge(payload.get("reminder"))
        if not created.reminder_id:
            raise RuntimeError("Apple Reminders did not return a confirmed reminder ID")
        return replace(created, provider="apple")

    async def complete_reminder(self, reminder_id: str) -> Reminder | None:
        payload = await self._request("POST", f"/reminders/{reminder_id}/complete")
        reminder = payload.get("reminder")
        return _reminder_from_bridge(reminder) if reminder else None

    async def delete_reminder(self, reminder_id: str) -> bool:
        payload = await self._request("DELETE", f"/reminders/{reminder_id}")
        return bool(payload.get("deleted"))


def _reminder_to_bridge(reminder: Reminder) -> dict:
    payload: dict = {"title": reminder.title, "list_id": reminder.list_id or None}
    if reminder.due is not None:
        payload["due"] = reminder.due.isoformat()
    if reminder.notes:
        payload["notes"] = reminder.notes
    return payload


def _list_from_bridge(value: object) -> ReminderList:
    if not isinstance(value, dict) or "list_id" not in value or "title" not in value:
        raise RuntimeError("Apple Reminders bridge list is incomplete")
    return ReminderList(
        list_id=str(value["list_id"]),
        title=str(value["title"]),
        writable=bool(value.get("writable", True)),
    )


def _reminder_from_bridge(value: object) -> Reminder:
    if not isinstance(value, dict):
        raise RuntimeError("Apple Reminders bridge returned an invalid reminder")
    required = ("reminder_id", "list_id", "title")
    if any(not value.get(key) for key in required):
        raise RuntimeError("Apple Reminders bridge reminder is incomplete")
    due = value.get("due")
    return Reminder(
        reminder_id=str(value["reminder_id"]),
        list_id=str(value["list_id"]),
        title=str(value["title"]),
        due=datetime.fromisoformat(str(due).replace("Z", "+00:00")) if due else None,
        notes=str(value["notes"]) if value.get("notes") else None,
        completed=bool(value.get("completed", False)),
        provider="apple",
        metadata={"list_title": value.get("list_title")},
    )
