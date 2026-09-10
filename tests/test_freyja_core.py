from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import freyja.core as core


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
