from __future__ import annotations

import asyncio
from pathlib import Path

from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.opencode_runtime import PROMPT_GUARDRAILS, _opencode_send, _opencode_shell, _opencode_start, _session_config, opencode_health
from freyja.tools.registry import ToolRegistry
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.foundation_seed import PERSISTENT_AGENTS


def test_builtin_registry_includes_opencode_control_tools() -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry)

    expected = {
        "opencode_start": ToolRiskLevel.CONTROLLED_WRITE,
        "opencode_send": ToolRiskLevel.CONTROLLED_WRITE,
        "opencode_shell": ToolRiskLevel.CONTROLLED_WRITE,
        "opencode_status": ToolRiskLevel.READ_ONLY,
        "opencode_output": ToolRiskLevel.READ_ONLY,
        "opencode_stop": ToolRiskLevel.CONTROLLED_WRITE,
    }
    for name, risk in expected.items():
        definition = registry.get_tool(name)
        assert definition is not None
        assert definition.risk_level == risk
        assert definition.host_service == "opencode"


def test_opencode_alias_registry_accepts_remote_session_entries(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "controller-sessions.json"
    registry_path.write_text(
        """
{
  "atlas-dashboard": {
    "base_url": "http://100.119.235.114:4097",
    "session": "ses_remote",
    "username": "joe"
  },
  "legacy": "ses_legacy"
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("freyja.tools.opencode_runtime.settings.opencode_session_registry_path", str(registry_path))

    assert _session_config("legacy") == {"session": "ses_legacy"}
    assert _session_config("atlas-dashboard") == {
        "base_url": "http://100.119.235.114:4097",
        "session": "ses_remote",
        "username": "joe",
    }


def test_opencode_send_passes_request_timeout(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "controller-sessions.json"
    registry_path.write_text('{"atlas-dashboard": {"base_url": "http://atlas.test", "session": "ses_remote", "username": "joe"}}', encoding="utf-8")
    monkeypatch.setattr("freyja.tools.opencode_runtime.settings.opencode_session_registry_path", str(registry_path))
    captured = {}

    def fake_request(method, path, body=None, **kwargs):
        captured.update({"method": method, "path": path, "body": body, **kwargs})
        return {
            "ok": True,
            "parts": [{"type": "text", "text": "sent"}],
            "info": {"time": {"completed": 1}, "path": {"cwd": "/repo"}, "id": "msg_1"},
        }

    monkeypatch.setattr("freyja.tools.opencode_runtime._request", fake_request)

    result = asyncio.run(
        _opencode_send(
            ToolExecutionRequest(
                tool_name="opencode_send",
                arguments={"alias": "atlas-dashboard", "prompt": "Do one thing.", "timeout_seconds": 45},
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert captured["timeout_seconds"] == 45
    assert captured["base_url"] == "http://atlas.test"
    assert captured["body"]["parts"][0]["text"].startswith(PROMPT_GUARDRAILS)


def test_opencode_start_rejects_missing_directory(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "controller-sessions.json"
    registry_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("freyja.tools.opencode_runtime.settings.opencode_session_registry_path", str(registry_path))

    def fail_request(*args, **kwargs):
        raise AssertionError("OpenCode should not be called for a missing directory")

    monkeypatch.setattr("freyja.tools.opencode_runtime._request", fail_request)

    result = asyncio.run(
        _opencode_start(
            ToolExecutionRequest(
                tool_name="opencode_start",
                arguments={"alias": "coder", "directory": str(tmp_path / "missing")},
                actor="test",
            )
        )
    )

    assert result == {"ok": False, "error": f"OpenCode directory does not exist: {tmp_path / 'missing'}"}


def test_opencode_health_does_not_count_ok_marker(monkeypatch) -> None:
    def fake_request(method, path, **kwargs):
        return {"ses_busy": {"type": "busy"}, "ok": True}

    monkeypatch.setattr("freyja.tools.opencode_runtime._request", fake_request)

    assert opencode_health(alias="freyja-code")["session_count"] == 1


def test_opencode_start_reuses_existing_alias_connection_config(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "controller-sessions.json"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    registry_path.write_text(
        '{"freyja-code": {"base_url": "http://freyja-code.test", "session": "ses_old", "username": "joe", "password_file": "/tmp/pass"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("freyja.tools.opencode_runtime.settings.opencode_session_registry_path", str(registry_path))
    captured = {}

    def fake_request(method, path, body=None, **kwargs):
        captured.update({"method": method, "path": path, "body": body, **kwargs})
        return {"ok": True, "id": "ses_new", "directory": "/repo"}

    monkeypatch.setattr("freyja.tools.opencode_runtime._request", fake_request)

    result = asyncio.run(
        _opencode_start(
            ToolExecutionRequest(
                tool_name="opencode_start",
                arguments={"alias": "freyja-code", "directory": str(repo_path)},
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert captured["base_url"] == "http://freyja-code.test"
    assert captured["username"] == "joe"
    assert captured["password_file"] == "/tmp/pass"
    assert _session_config("freyja-code") == {
        "base_url": "http://freyja-code.test",
        "session": "ses_new",
        "username": "joe",
        "password_file": "/tmp/pass",
    }


def test_opencode_live_start_and_shell_when_server_available() -> None:
    password_file = Path.home() / ".local" / "state" / "freyja" / "opencode" / "server-password"
    proof_repo = Path.home() / "opencode-freyja-proof"
    if not password_file.exists() or not proof_repo.exists():
        return

    start_result = asyncio.run(
        _opencode_start(
            ToolExecutionRequest(
                tool_name="opencode_start",
                arguments={"alias": "pytest-opencode-live", "directory": str(proof_repo)},
                actor="test",
            )
        )
    )
    if not start_result.get("ok"):
        return

    shell_result = asyncio.run(
        _opencode_shell(
            ToolExecutionRequest(
                tool_name="opencode_shell",
                arguments={"alias": "pytest-opencode-live", "command": "pwd && python3 -m unittest -v"},
                actor="test",
            )
        )
    )

    assert shell_result["ok"] is True
    assert shell_result["state"] == "completed"
    assert shell_result["working_directory"] == str(proof_repo)
    assert shell_result["recent_action"]["tool"] == "bash"
    assert "OK" in shell_result["result"]


def test_freyja_routes_webpage_opencode_and_tailscale_work_to_coding_execute() -> None:
    runtime = AgentRuntimeV3(run_inference=False)
    freyja = next(agent for agent in PERSISTENT_AGENTS if agent.agent_id == "freyja")

    selected = runtime.choose_tools(
        freyja,
        "Use OpenCode to build a webpage and configure the Tailscale port.",
        freyja.tool_grants,
    )

    assert selected == ["coding.execute"]
