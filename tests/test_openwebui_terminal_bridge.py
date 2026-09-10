from __future__ import annotations

import json
import os
import subprocess
import time
import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE = REPO_ROOT / "scripts" / "openwebui-terminal-bridge.py"
SESSION = "pytest-openwebui-bridge"


def _bridge(*args: str, state_dir: Path, stdin: str | None = None) -> dict[str, object]:
    env = {
        **os.environ,
        "OPENWEBUI_TERMINAL_BRIDGE_STATE_DIR": str(state_dir),
    }
    result = subprocess.run(
        [str(BRIDGE), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_bridge_lifecycle_sends_literal_keys_and_stops(tmp_path: Path) -> None:
    try:
        started = _bridge("start", SESSION, "--agent", "shell-test", "--workdir", str(REPO_ROOT), state_dir=tmp_path)
        assert started["ok"] is True
        assert started["status"] == "started"
        assert started["workdir"] == str(REPO_ROOT)

        duplicate = _bridge("start", SESSION, "--agent", "shell-test", "--workdir", "/tmp", state_dir=tmp_path)
        assert duplicate["status"] == "already_running"
        assert duplicate["workdir"] == str(REPO_ROOT)

        status = _bridge("status", SESSION, state_dir=tmp_path)
        assert status["running"] is True
        assert status["agent"] == "shell-test"

        sent = _bridge("send", SESSION, "--stdin", "--enter", state_dir=tmp_path, stdin="printf BRIDGE_TEST_OK; pwd")
        assert sent["ok"] is True
        time.sleep(0.2)

        read = _bridge("read", SESSION, "--lines", "80", state_dir=tmp_path)
        assert read["ok"] is True
        assert "BRIDGE_TEST_OK" in str(read["output"])
        assert str(REPO_ROOT) in str(read["output"])

        interrupted = _bridge("send", SESSION, "--ctrl-c", state_dir=tmp_path)
        assert interrupted["ok"] is True
    finally:
        stopped = _bridge("stop", SESSION, state_dir=tmp_path)
        assert stopped["ok"] is True

    final_status = _bridge("status", SESSION, state_dir=tmp_path)
    assert final_status["running"] is False


def test_bridge_rejects_unsafe_session_names(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(BRIDGE), "status", "bad;name"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env={**os.environ, "OPENWEBUI_TERMINAL_BRIDGE_STATE_DIR": str(tmp_path)},
    )
    assert result.returncode != 0
    assert "session must contain only" in result.stderr


def test_openwebui_tool_source_defines_top_level_tools_class() -> None:
    source = (REPO_ROOT / "ops/openwebui/create_iris_tools.py").read_text(encoding="utf-8")
    module_ast = ast.parse(source)
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module_ast.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "OPENWEBUI_TERMINAL_BRIDGE"
    }
    namespace: dict[str, object] = {}
    exec(constants["OPENWEBUI_TERMINAL_BRIDGE"], namespace)
    tools = namespace.get("Tools")
    assert isinstance(tools, type)
    for method in ("terminal_start", "terminal_status", "terminal_send", "terminal_ctrl_c", "terminal_read", "terminal_stop"):
        assert callable(getattr(tools(), method))
