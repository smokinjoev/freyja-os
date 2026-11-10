from datetime import datetime, time, date
from zoneinfo import ZoneInfo

from connectors.signal.scheduled_reminders import ScheduledReminder, ScheduledReminderNotifier, ScheduledReminderStore
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry
from freyja.tools.scheduled_reminders import register_scheduled_reminder_tools


async def test_every_other_day_reminder_sends_once_per_due_day(tmp_path) -> None:
    store = ScheduledReminderStore(tmp_path / "reminders.sqlite3")
    store.upsert(ScheduledReminder("meds", "Time to take your meds.", date(2026, 10, 24), time(12, 30), 2))

    class Transport:
        def __init__(self): self.sent = []
        async def send(self, response): self.sent.append(response)

    transport = Transport()
    notifier = ScheduledReminderNotifier(store=store, transport=transport, recipient="+15551234567")
    eastern = ZoneInfo("America/New_York")

    assert await notifier.dispatch_due(datetime(2026, 10, 24, 12, 29, tzinfo=eastern)) == 0
    assert await notifier.dispatch_due(datetime(2026, 10, 24, 12, 30, tzinfo=eastern)) == 1
    assert await notifier.dispatch_due(datetime(2026, 10, 24, 13, 0, tzinfo=eastern)) == 0
    assert await notifier.dispatch_due(datetime(2026, 10, 25, 13, 0, tzinfo=eastern)) == 0
    assert await notifier.dispatch_due(datetime(2026, 10, 26, 12, 30, tzinfo=eastern)) == 1
    assert len(transport.sent) == 2


async def test_scheduled_reminder_tools_manage_persistent_schedule(tmp_path, monkeypatch) -> None:
    from freyja.tools import scheduled_reminders

    monkeypatch.setattr(scheduled_reminders.gmail_settings, "gmail_reminder_store_path", str(tmp_path / "reminders.sqlite3"))
    registry = ToolRegistry(audit_enabled=False)
    register_scheduled_reminder_tools(registry)

    created = await registry.execute(ToolExecutionRequest(
        tool_name="scheduled_reminder_create",
        arguments={
            "text": "Reminder: time to take your meds.",
            "start_date": "2026-10-24", "local_time": "12:30", "interval_days": 2,
        }, metadata={"director_authorized": True},
    ))
    reminder_id = created.output["reminder"]["reminder_id"]
    listed = await registry.execute(ToolExecutionRequest(
        tool_name="scheduled_reminder_list", metadata={"director_authorized": True},
    ))
    updated = await registry.execute(ToolExecutionRequest(
        tool_name="scheduled_reminder_update",
        arguments={"reminder_id": reminder_id, "local_time": "13:00"},
        metadata={"director_authorized": True},
    ))
    stopped = await registry.execute(ToolExecutionRequest(
        tool_name="scheduled_reminder_stop", arguments={"reminder_id": reminder_id},
        metadata={"director_authorized": True},
    ))

    assert created.output["created"] is True
    assert listed.output["count"] == 1
    assert updated.output["reminder"]["local_time"] == "13:00"
    assert stopped.output["stopped"] is True
