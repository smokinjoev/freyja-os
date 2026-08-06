from __future__ import annotations

from datetime import datetime

from freyja.reminders.models import Reminder, ReminderList
from freyja.reminders.providers import InMemoryReminderProvider, ReminderProvider


class ReminderService:
    def __init__(self, providers: dict[str, ReminderProvider] | None = None) -> None:
        self._providers = providers or {"memory": InMemoryReminderProvider()}

    async def lists(self, *, provider_name: str = "memory") -> list[ReminderList]:
        return await self._provider(provider_name).lists()

    async def list_reminders(
        self,
        *,
        list_ids: list[str] | None = None,
        include_completed: bool = False,
        provider_name: str = "memory",
    ) -> list[Reminder]:
        return await self._provider(provider_name).list_reminders(
            list_ids=list_ids or [],
            include_completed=include_completed,
        )

    async def create_reminder(
        self,
        *,
        title: str,
        due: datetime | None = None,
        notes: str | None = None,
        list_id: str | None = None,
        provider_name: str = "memory",
    ) -> Reminder:
        return await self._provider(provider_name).create_reminder(
            Reminder("", list_id or "default", title, due=due, notes=notes)
        )

    async def complete_reminder(self, *, reminder_id: str, provider_name: str = "memory") -> Reminder | None:
        return await self._provider(provider_name).complete_reminder(reminder_id)

    async def delete_reminder(self, *, reminder_id: str, provider_name: str = "memory") -> bool:
        return await self._provider(provider_name).delete_reminder(reminder_id)

    def _provider(self, provider_name: str) -> ReminderProvider:
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise ValueError(f"unknown reminder provider: {provider_name}") from exc


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
