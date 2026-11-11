"""Persistent recurring reminders delivered through Signal."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from connectors.signal.models import OutboundResponse
from freyja.scheduled_reminders import ScheduledReminder, ScheduledReminderStore


class SignalSender(Protocol):
    async def send(self, response: OutboundResponse) -> None: ...


class ScheduledReminderNotifier:
    def __init__(self, *, store: ScheduledReminderStore, transport: SignalSender, recipient: str) -> None:
        self.store = store
        self.transport = transport
        self.recipient = recipient.strip()

    async def dispatch_due(self, now: datetime) -> int:
        sent = 0
        if not self.recipient:
            return sent
        for reminder in self.store.due(now):
            await self.transport.send(
                OutboundResponse(recipient=self.recipient, text=str(reminder["text"]))
            )
            if self.store.mark_sent(str(reminder["reminder_id"]), str(reminder["send_date"])):
                sent += 1
        return sent
