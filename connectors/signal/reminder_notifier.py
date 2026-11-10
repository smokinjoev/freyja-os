"""Deliver email reminder candidates through Freyja's Signal transport."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from connectors.gmail.reminders import ReminderStore
from connectors.signal.models import OutboundResponse


class SignalSender(Protocol):
    async def send(self, response: OutboundResponse) -> None: ...


class EmailReminderNotifier:
    def __init__(self, *, store: ReminderStore, transport: SignalSender, recipient: str,
                 timezone: str = "America/New_York", max_items: int = 8,
                 max_message_chars: int = 4000) -> None:
        self.store = store
        self.transport = transport
        self.recipient = recipient.strip()
        self.timezone = ZoneInfo(timezone)
        self.max_items = max(1, max_items)
        self.max_message_chars = max(500, max_message_chars)

    async def dispatch_pending(self) -> dict[str, int | bool]:
        if not self.recipient:
            return {"sent": False, "candidate_count": 0, "marked_notified": 0}
        candidates = self.store.list_unnotified(limit=200)
        if not candidates:
            return {"sent": False, "candidate_count": 0, "marked_notified": 0}
        message = self._format_digest(candidates)
        await self.transport.send(OutboundResponse(recipient=self.recipient, text=message))
        marked = self.store.mark_notified([str(item["candidate_id"]) for item in candidates])
        return {"sent": True, "candidate_count": len(candidates), "marked_notified": marked}

    def _format_digest(self, candidates: list[dict[str, str | None]]) -> str:
        visible = candidates[: self.max_items]
        lines = ["I found some possible reminders in your email:"]
        for index, item in enumerate(visible, 1):
            due = datetime.fromisoformat(str(item["due_at"])).astimezone(self.timezone)
            due_text = due.strftime("%a, %b %-d at %-I:%M %p")
            summary = " ".join(str(item["summary"]).split())
            sender = str(item["sender"] or "").strip()
            detail = f" — {sender}" if sender else ""
            lines.append(f"{index}. {summary} — due {due_text}{detail}")
        remaining = len(candidates) - len(visible)
        if remaining:
            lines.append(f"…and {remaining} more.")
        lines.append("Want me to help with any of these?")
        message = "\n".join(lines)
        if len(message) <= self.max_message_chars:
            return message
        return message[: self.max_message_chars - 1].rstrip() + "…"
