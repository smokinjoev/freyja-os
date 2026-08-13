from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReminderList:
    list_id: str
    title: str
    writable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"list_id": self.list_id, "title": self.title, "writable": self.writable}


@dataclass(frozen=True)
class Reminder:
    reminder_id: str
    list_id: str
    title: str
    due: datetime | None = None
    notes: str | None = None
    completed: bool = False
    provider: str = "memory"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reminder_id": self.reminder_id,
            "list_id": self.list_id,
            "title": self.title,
            "completed": self.completed,
            "provider": self.provider,
        }
        if self.due is not None:
            payload["due"] = self.due.isoformat()
        if self.notes:
            payload["notes"] = self.notes
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
