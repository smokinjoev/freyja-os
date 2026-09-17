from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import freyja.core as core
from freyja.calendar.providers import InMemoryCalendarProvider
from freyja.calendar.service import CalendarService


def test_house_query_contains_core_hosts() -> None:
    result = core.house_query("vulcan")

    assert result["ok"] is True
    assert result["matches"]["vulcan"]["network_identities"]["tailscale"] == "100.94.80.21"
    assert "Msty Nexus on 3939" in result["matches"]["vulcan"]["major_services"]


def test_terminal_argv_uses_house_ssh_user_for_atlas() -> None:
    assert core._terminal_argv("atlas", "hostname") == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "joe@100.119.235.114",
        "hostname",
    ]


@pytest.mark.asyncio
async def test_terminal_blocks_destructive_commands() -> None:
    result = await core.terminal("iris", "rm -rf /tmp/freyja-core-test")

    assert result["ok"] is False
    assert result["approval_required"] is True


@pytest.mark.asyncio
async def test_core_loop_infers_vulcan_tools_and_uses_nexus(monkeypatch) -> None:
    terminal_calls = []

    async def fake_terminal(host: str, command: str) -> dict:
        terminal_calls.append((host, command))
        return {"ok": True, "host": host, "command": command, "stdout": '{"status":"ok"}', "stderr": ""}

    async def fake_nexus_chat(messages: list[dict[str, str]]) -> str:
        assert "Vulcan" in messages[-1]["content"] or "vulcan" in messages[-1]["content"]
        return "Vulcan Nexus is reachable and returned health ok."

    monkeypatch.setattr(core, "terminal", fake_terminal)
    monkeypatch.setattr(core, "nexus_chat", fake_nexus_chat)

    result = await core.run_core_loop("How is Vulcan doing?")

    assert result["answer"] == "Vulcan Nexus is reachable and returned health ok."
    assert ("iris", "curl -fsS --max-time 5 http://100.94.80.21:3939/health") in terminal_calls
    assert result["observations"][0]["tool"] == "house_query"


@pytest.mark.asyncio
async def test_core_loop_infers_agent_control(monkeypatch) -> None:
    calls = []

    async def fake_agent_control(arguments: dict) -> dict:
        calls.append(arguments)
        return {"ok": True, "action": arguments["action"], "alias": arguments["alias"]}

    async def fake_nexus_chat(messages: list[dict[str, str]]) -> str:
        return "Started a coding agent and sent it a read-only repo investigation prompt."

    monkeypatch.setattr(core, "agent_control", fake_agent_control)
    monkeypatch.setattr(core, "nexus_chat", fake_nexus_chat)

    result = await core.run_core_loop("Start a coding agent to investigate this repo.")

    assert [call["action"] for call in calls] == ["start", "send"]
    assert "Started a coding agent" in result["answer"]


@pytest.mark.asyncio
async def test_agent_control_send_timeout_reports_working(monkeypatch) -> None:
    async def fake_send(request):
        return {"ok": False, "error": "timed out"}

    async def fake_status(request):
        return {"ok": True, "state": {"type": "busy"}, "session": "ses_test"}

    monkeypatch.setattr(core, "_opencode_send", fake_send)
    monkeypatch.setattr(core, "_opencode_status", fake_status)

    result = await core.agent_control({"action": "send", "alias": "coder", "prompt": "investigate"})

    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["send_timed_out"] is True
    assert result["status"]["state"] == {"type": "busy"}


def test_slow_diagnostic_uses_bounded_read_only_top() -> None:
    call = core.choose_tool("Why is Freyja slow?", [])

    assert call is not None
    assert call.name == "terminal"
    assert call.arguments["command"] == "top -l 1 -n 15 -stats pid,cpu,mem,command"
    assert core._is_read_only_command(call.arguments["command"]) is True

    followup = core.choose_tool(
        "Why is Freyja slow?",
        [{"tool": "terminal", "arguments": {"command": "top -l 1 -n 15 -stats pid,cpu,mem,command"}, "result": {"ok": True}}],
    )
    assert followup is not None
    assert followup.name == "terminal"
    assert followup.arguments["command"] == "pgrep -fl freyja"
    assert core._is_read_only_command(followup.arguments["command"]) is True


def test_openai_compatible_chat_endpoint(monkeypatch) -> None:
    async def fake_loop(prompt: str, *, max_iterations: int | None = None) -> dict:
        return {"iterations": 1, "observations": [], "answer": f"answered: {prompt}"}

    monkeypatch.setattr(core, "run_core_loop", fake_loop)
    client = TestClient(core.create_app())

    response = client.post(
        "/v1/chat/completions",
        json={"model": "freyja-core", "messages": [{"role": "user", "content": "How is Vulcan doing?"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "answered: How is Vulcan doing?"
    assert body["freyja"]["iterations"] == 1


def test_tools_endpoint_lists_core_owned_tools() -> None:
    client = TestClient(core.create_app())

    response = client.get("/tools")

    assert response.status_code == 200
    tools = response.json()["tools"]
    assert "status.check" in tools
    assert "calendar.resolve_date" in tools
    assert "opencode.send" in tools


def test_calendar_resolve_date_this_weekend_is_deterministic() -> None:
    result = core.resolve_date_tool({"phrase": "this weekend", "base_date": "2026-09-17"})

    assert result["ok"] is True
    assert result["start_date"] == "2026-09-19"
    assert result["end_date"] == "2026-09-20"
    assert result["dates"] == ["2026-09-19", "2026-09-20"]


def test_calendar_resolve_date_next_friday() -> None:
    result = core.resolve_date_tool({"phrase": "next Friday", "base_date": "2026-09-17"})

    assert result["ok"] is True
    assert result["date"] == "2026-09-18"


def test_calendar_create_event_requires_calendar() -> None:
    client = TestClient(core.create_app())

    response = client.post(
        "/tools/call",
        json={
            "tool": "calendar.create_event",
            "arguments": {
                "title": "Freyja Core smoke",
                "start": "2026-09-19T10:00:00+00:00",
                "end": "2026-09-19T10:15:00+00:00",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "calendar_id" in response.json()["error"]


@pytest.mark.asyncio
async def test_calendar_create_event_uses_calendar_service(monkeypatch) -> None:
    service = CalendarService(
        providers={"memory": InMemoryCalendarProvider()},
        default_provider_name="memory",
    )
    monkeypatch.setattr(core, "get_calendar_service", lambda: service)

    result = await core.create_calendar_event_tool(
        {
            "title": "Freyja Core smoke",
            "start": "2026-09-19T10:00:00+00:00",
            "end": "2026-09-19T10:15:00+00:00",
            "calendar_id": "joe",
            "provider": "memory",
        }
    )

    assert result["ok"] is True
    assert result["event"]["title"] == "Freyja Core smoke"
    assert result["event"]["calendar_id"] == "joe"


@pytest.mark.asyncio
async def test_calendar_delete_event_requires_explicit_cleanup_approval(monkeypatch) -> None:
    service = CalendarService(
        providers={"memory": InMemoryCalendarProvider()},
        default_provider_name="memory",
    )
    monkeypatch.setattr(core, "get_calendar_service", lambda: service)

    result = await core.delete_calendar_event_tool({"event_id": "event-1", "provider": "memory"})

    assert result["ok"] is False
    assert result["approval_required"] is True


@pytest.mark.asyncio
async def test_calendar_delete_event_deletes_with_cleanup_approval(monkeypatch) -> None:
    service = CalendarService(
        providers={"memory": InMemoryCalendarProvider()},
        default_provider_name="memory",
    )
    monkeypatch.setattr(core, "get_calendar_service", lambda: service)
    created = await core.create_calendar_event_tool(
        {
            "title": "Freyja Core cleanup smoke",
            "start": "2026-09-19T10:00:00+00:00",
            "end": "2026-09-19T10:15:00+00:00",
            "calendar_id": "joe",
            "provider": "memory",
        }
    )

    result = await core.delete_calendar_event_tool(
        {
            "event_id": created["event"]["event_id"],
            "provider": "memory",
            "approval": "DELETE_FREYJA_CORE_SMOKE_EVENT",
        }
    )

    assert result["ok"] is True
    assert result["deleted"] is True


@pytest.mark.asyncio
async def test_opencode_read_routes_to_output(monkeypatch) -> None:
    calls = []

    async def fake_agent_control(arguments: dict) -> dict:
        calls.append(arguments)
        return {"ok": True, "action": arguments["action"]}

    monkeypatch.setattr(core, "agent_control", fake_agent_control)

    result = await core.opencode_tool("opencode.read", {"alias": "coder"})

    assert result["ok"] is True
    assert calls == [{"action": "output", "alias": "coder"}]
