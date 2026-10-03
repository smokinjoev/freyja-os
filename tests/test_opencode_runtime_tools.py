from __future__ import annotations

import asyncio
from pathlib import Path

from freyja.config import settings
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.opencode_runtime import PROMPT_GUARDRAILS, _opencode_send, _opencode_shell, _opencode_start, _session_config, opencode_health
from freyja.tools.registry import ToolRegistry
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.foundation_models import GatewaySender, SecurityDomainId
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
    calls = []

    def fake_request(method, path, body=None, **kwargs):
        calls.append({"method": method, "path": path, "body": body, **kwargs})
        if path.endswith("/prompt_async"):
            return {"ok": True}
        return {"ok": True, "directory": "/repo"}

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
    assert result["state"] == "submitted"
    submit = calls[0]
    assert submit["path"] == "/session/ses_remote/prompt_async"
    assert submit["timeout_seconds"] == 45
    assert submit["base_url"] == "http://atlas.test"
    assert submit["body"]["tools"]["task"] is False
    assert submit["body"]["parts"][0]["text"].startswith(PROMPT_GUARDRAILS)


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


def test_opencode_health_reports_missing_password_file_without_raising(monkeypatch, tmp_path) -> None:
    missing_password = tmp_path / "missing-password"
    monkeypatch.setattr(settings, "opencode_password_file", str(missing_password))

    health = opencode_health(alias="freyja-code")

    assert health["ok"] is False
    assert health["alias"] == "freyja-code"
    assert str(missing_password) in health["error"]


def test_opencode_health_skips_password_when_auth_is_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "opencode_auth_enabled", False)
    monkeypatch.setattr(settings, "opencode_password_file", str(tmp_path / "missing-password"))
    monkeypatch.setattr(
        "freyja.tools.opencode_runtime._request",
        lambda *args, **kwargs: {"ok": True, "session": {"id": "ses_test"}},
    )

    health = opencode_health(alias="freyja-code")

    assert health["ok"] is True


def test_agent_runtime_binds_read_only_opencode_status_to_managed_alias() -> None:
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=GatewaySender(sender_id="person:joe", display_name="Joe", security_domain_id=SecurityDomainId.PERSON_JOE),
            target_agent="cloyd-gibbler",
            prompt="Use your read-only OpenCode status tool.",
            conversation_id="test-cloyd-status",
            channel="discord",
        )
    ).handoff

    assert handoff is not None
    assert AgentRuntimeV3._arguments_for_tool("opencode.status", handoff.prompt, handoff) == {
        "alias": "freyja-core-coder"
    }


def test_agent_runtime_prioritizes_non_adjacent_opencode_status_words() -> None:
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=GatewaySender(sender_id="person:joe", display_name="Joe", security_domain_id=SecurityDomainId.PERSON_JOE),
            target_agent="cloyd-gibbler",
            prompt="What is the OpenCode working directory and session state?",
            conversation_id="test-cloyd-status-words",
            channel="discord",
        )
    ).handoff

    assert handoff is not None
    runtime = AgentRuntimeV3()
    assert runtime.choose_tools(runtime._agent("cloyd-gibbler"), handoff.prompt, handoff.available_tools) == ["opencode.status"]


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
