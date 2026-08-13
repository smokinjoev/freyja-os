from __future__ import annotations

from datetime import UTC, datetime

import pytest

from freyja.reminders import InMemoryReminderProvider, Reminder, ReminderList, ReminderService
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry
from freyja.tools.reminders import register_reminder_tools, set_reminder_service


@pytest.fixture
def registry() -> ToolRegistry:
    registry = ToolRegistry(audit_enabled=False)
    register_reminder_tools(registry)
    yield registry
    set_reminder_service(None)


@pytest.fixture
def service() -> ReminderService:
    provider = InMemoryReminderProvider(
        reminders=[Reminder("reminder-1", "home", "Buy milk", due=datetime(2026, 8, 8, 12, tzinfo=UTC))],
        lists=[ReminderList("home", "Home")],
    )
    service = ReminderService(providers={"memory": provider})
    set_reminder_service(service)
    return service


@pytest.mark.asyncio
async def test_reminders_list_tool_uses_service(registry: ToolRegistry, service: ReminderService) -> None:
    result = await registry.execute(
        ToolExecutionRequest(tool_name="reminders_list", arguments={"list_ids": ["home"]})
    )

    assert result.success is True
    assert result.output["count"] == 1
    assert result.output["reminders"][0]["title"] == "Buy milk"


@pytest.mark.asyncio
async def test_reminders_create_complete_delete_tools(registry: ToolRegistry, service: ReminderService) -> None:
    created = await registry.execute(
        ToolExecutionRequest(
            tool_name="reminders_create",
            arguments={"title": "Call dentist", "due": "2026-08-09T15:00:00+00:00", "list_id": "home"},
        )
    )
    reminder_id = created.output["reminder"]["reminder_id"]

    completed = await registry.execute(
        ToolExecutionRequest(tool_name="reminders_complete", arguments={"reminder_id": reminder_id})
    )
    deleted = await registry.execute(
        ToolExecutionRequest(tool_name="reminders_delete", arguments={"reminder_id": reminder_id})
    )

    assert created.success is True
    assert completed.output["completed"] is True
    assert completed.output["reminder"]["completed"] is True
    assert deleted.output["deleted"] is True
