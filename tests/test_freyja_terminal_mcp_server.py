from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER = REPO_ROOT / "scripts" / "freyja-terminal-mcp-server.py"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("freyja_terminal_mcp_server", SERVER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_terminal_mcp_server_exposes_expected_tools() -> None:
    module = _load_server_module()
    tool_names = {tool.name for tool in await module.mcp.list_tools()}
    assert {
        "terminal_start",
        "terminal_status",
        "terminal_send",
        "terminal_ctrl_c",
        "terminal_read",
        "terminal_stop",
    } <= tool_names
