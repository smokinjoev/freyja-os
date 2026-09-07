from __future__ import annotations

import importlib.util
import json
import plistlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER = REPO_ROOT / "deploy" / "compose" / "freyja-gateway-remote" / "server.py"
PLIST = REPO_ROOT / "scripts" / "com.freyja-os.gateway-remote.plist"
QWEN_LAUNCHER = REPO_ROOT / "scripts" / "run-agent-smith-qwen.sh"


def load_server():
    spec = importlib.util.spec_from_file_location("gateway_remote", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_token_generation_stores_hashes_only(tmp_path, monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "TOKEN_FILE", tmp_path / "tokens.json")

    issued = server.ensure_tokens()

    stored = json.loads((tmp_path / "tokens.json").read_text(encoding="utf-8"))
    assert sorted(issued) == ["beth", "jenna", "joe", "liam"]
    assert all("sha256" in record for record in stored.values())
    for raw in issued.values():
        assert raw not in str(stored)


def test_append_trace_omits_prompt_and_credentials(tmp_path, monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "TRACE_FILE", tmp_path / "trace.jsonl")

    server.append_trace(
        {
            "event": "terminal_started",
            "person": "joe",
            "repo": "/Users/freyja/freyja-os",
            "prompt": "secret prompt",
            "credential": "secret-token",
        }
    )

    body = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "secret prompt" not in body
    assert "secret-token" not in body
    assert "terminal_started" in body


def test_allowed_repo_accepts_exact_repo_and_root_children(tmp_path, monkeypatch) -> None:
    server = load_server()
    exact = tmp_path / "freyja-os"
    root = tmp_path / "workspace"
    child = root / "new-app"
    outside = tmp_path / "outside"
    exact.mkdir()
    root.mkdir()
    outside.mkdir()
    monkeypatch.setattr(server, "ALLOWED_REPOS", (exact.resolve(),))
    monkeypatch.setattr(server, "ALLOWED_ROOTS", (root.resolve(),))

    assert server.allowed_repo(str(exact)) == exact.resolve()
    assert server.allowed_repo(str(child), create=True) == child.resolve()

    try:
        server.allowed_repo(str(outside))
    except ValueError as exc:
        assert "outside allowed workspace roots" in str(exc)
    else:
        raise AssertionError("outside folder should be denied")


def test_qwen_command_is_plain_interactive_terminal(monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "QWEN_BIN", "/opt/homebrew/bin/qwen")
    monkeypatch.setattr(server, "VULCAN_MODEL", "@preset/freyja-coder")

    assert server.qwen_command() == ["/opt/homebrew/bin/qwen", "--model", "@preset/freyja-coder"]


def test_terminal_env_points_qwen_at_vulcan(tmp_path, monkeypatch) -> None:
    server = load_server()
    token_file = tmp_path / "msty-nexus-token"
    token_file.write_text("nexus-token\n", encoding="utf-8")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("OPENROUTER_API_KEY", "cloud-key")
    monkeypatch.setattr(server, "VULCAN_MODEL_BASE_URL", "http://100.94.80.21:3939/v1")
    monkeypatch.setattr(server, "VULCAN_MODEL", "@preset/freyja-coder")
    monkeypatch.setattr(server, "SMITH_QWEN_HOME", tmp_path / "qwen-smith")
    monkeypatch.setattr(server, "NEXUS_TOKEN_FILE", token_file)

    env = server.terminal_env()

    assert env["OPENAI_BASE_URL"] == "http://100.94.80.21:3939/v1"
    assert env["OPENAI_API_KEY"] == "nexus-token"
    assert env["QWEN_HOME"] == str(tmp_path / "qwen-smith")
    assert "OPENROUTER_API_KEY" not in env
    assert "/opt/homebrew/bin" in env["PATH"].split(":")


def test_nexus_status_reports_token_presence_without_value(tmp_path, monkeypatch) -> None:
    server = load_server()
    token_file = tmp_path / "msty-nexus-token"
    token_file.write_text("secret-nexus-token\n", encoding="utf-8")
    monkeypatch.setattr(server, "NEXUS_TOKEN_FILE", token_file)

    status = server.nexus_config_status()

    assert status["token_present"] is True
    assert status["token_file"] == str(token_file)
    assert "secret-nexus-token" not in json.dumps(status)


def test_smith_qwen_home_contains_only_vulcan_provider(tmp_path, monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "SMITH_QWEN_HOME", tmp_path / "qwen-smith")
    monkeypatch.setattr(server, "VULCAN_MODEL_BASE_URL", "http://100.94.80.21:3939/v1")
    monkeypatch.setattr(server, "VULCAN_MODEL", "@preset/freyja-coder")

    server.ensure_smith_qwen_home()

    settings = json.loads((tmp_path / "qwen-smith" / "settings.json").read_text(encoding="utf-8"))
    assert settings["model"]["baseUrl"] == "http://100.94.80.21:3939/v1"
    assert settings["model"]["name"] == "@preset/freyja-coder"
    assert settings["modelProviders"]["openai"][0]["baseUrl"] == "http://100.94.80.21:3939/v1"
    assert "openrouter" not in json.dumps(settings).lower()


def test_sanitize_text_redacts_common_secret_shapes() -> None:
    server = load_server()

    text = server.sanitize_text("Authorization: Bearer abcdefghijklmnop\npassword: hunter2\nsk-abcdefghijklmnopqrstuvwxyz")

    assert "abcdefghijklmnop" not in text
    assert "hunter2" not in text
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in text


def test_launchagent_runs_ttyd_terminal_for_agent_smith() -> None:
    with PLIST.open("rb") as handle:
        plist = plistlib.load(handle)

    args = plist["ProgramArguments"]

    assert args[:7] == [
        "/opt/homebrew/bin/ttyd",
        "--interface",
        "127.0.0.1",
        "--port",
        "8010",
        "--writable",
        "--check-origin",
    ]
    assert "--ping-interval" in args
    assert args[args.index("--ping-interval") + 1] == "30"
    assert "disableReconnect=true" in args
    assert "/Users/freyja/freyja-os/scripts/run-agent-smith-qwen.sh" in args
    assert plist["EnvironmentVariables"]["AGENT_SMITH_WORKDIR"] == "/Users/freyja"


def test_qwen_launcher_points_agent_smith_at_vulcan_only() -> None:
    body = QWEN_LAUNCHER.read_text(encoding="utf-8")

    assert "http://100.94.80.21:3939/v1" in body
    assert "@preset/freyja-coder" in body
    assert "msty-nexus-token" in body
    assert '"enableAutoUpdate": False' in body
    assert 'unset OPENROUTER_API_KEY' in body
    assert 'TMUX_SESSION="${AGENT_SMITH_TMUX_SESSION:-agent-smith}"' in body
    assert 'exec "$TMUX_BIN" new-session -A -s "$TMUX_SESSION"' in body
    assert 'printf "%q " "$QWEN_BIN" --model "$FREYJA_GATEWAY_REMOTE_VULCAN_MODEL"' in body
