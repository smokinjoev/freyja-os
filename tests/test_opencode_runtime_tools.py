from __future__ import annotations

import asyncio
from pathlib import Path

from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.opencode_runtime import _opencode_shell, _opencode_start
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
