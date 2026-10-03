import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

import freyja.main as freyja_main
import freyja.terminal_smith as terminal_smith
from freyja.terminal_smith import TerminalSmithConfig, TerminalSmithController


def _completed(args: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_terminal_smith_restart_captures_interrupts_and_recreates_only_smith(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    qwen_home = tmp_path / "qwen-smith"
    workdir = tmp_path / "work"
    workdir.mkdir()
    config = TerminalSmithConfig(
        tmux_bin="/bin/tmux",
        tmux_session="agent-smith",
        qwen_bin="/bin/qwen",
        qwen_home=str(qwen_home),
        token_file=str(token_file),
        base_url="http://vulcan.test/v1",
        model="@preset/freyja-coder",
        workdir=str(workdir),
        capture_dir=str(tmp_path / "captures"),
        terminal_url="http://iris.test:8010/",
    )
    controller = TerminalSmithController(config)
    commands: list[list[str]] = []
    start_env: dict[str, str] = {}

    def fake_run(args, **kwargs):
        commands.append(list(args))
        if args[1:3] == ["has-session", "-t"]:
            return _completed(args)
        if args[1] == "capture-pane":
            return _completed(args, stdout="hung request output\n")
        if args[1] == "display-message":
            return _completed(args, stdout=f"12345\tnode\t{workdir}\t1780000000\t0\n")
        if args[1] == "new-session":
            start_env.update(kwargs["env"])
            return _completed(args)
        return _completed(args)

    monkeypatch.setattr(terminal_smith.subprocess, "run", fake_run)
    monkeypatch.setattr(terminal_smith.time, "sleep", lambda _seconds: None)

    result = controller.restart()

    assert result["ok"] is True
    assert result["interrupted_existing_session"] is True
    assert Path(result["capture"]["path"]).read_text(encoding="utf-8").endswith("hung request output\n")
    assert ["/bin/tmux", "send-keys", "-t", "agent-smith:0.0", "C-c"] in commands
    assert ["/bin/tmux", "kill-session", "-t", "agent-smith"] in commands
    assert [
        "/bin/tmux",
        "new-session",
        "-d",
        "-s",
        "agent-smith",
        "-c",
        str(workdir),
        "/bin/qwen --model @preset/freyja-coder",
    ] in commands
    settings = json.loads((qwen_home / "settings.json").read_text(encoding="utf-8"))
    assert settings["model"]["baseUrl"] == "http://vulcan.test/v1"
    assert settings["model"]["name"] == "@preset/freyja-coder"
    assert start_env["OPENAI_BASE_URL"] == "http://vulcan.test/v1"
    assert start_env["OPENAI_API_KEY"] == "secret-token"
    assert "OPENROUTER_API_KEY" not in start_env


def test_terminal_smith_ping_waits_for_qwen_response_marker(tmp_path, monkeypatch) -> None:
    config = TerminalSmithConfig(
        tmux_bin="/bin/tmux",
        tmux_session="agent-smith",
        qwen_bin="/bin/qwen",
        qwen_home=str(tmp_path / "qwen"),
        token_file=str(tmp_path / "token"),
        capture_dir=str(tmp_path / "captures"),
    )
    controller = TerminalSmithController(config)
    captures = iter(
        [
            "  > Reply exactly: SMITH_READY_test\n",
            "  > Reply exactly: SMITH_READY_test\n\n  \u25c6 SMITH_READY_test\n",
            "  > Reply exactly: SMITH_READY_test\n\n  \u25c6 SMITH_READY_test\n",
        ]
    )

    def fake_run(args, **_kwargs):
        if args[1:3] == ["has-session", "-t"]:
            return _completed(args)
        if args[1] == "send-keys":
            return _completed(args)
        if args[1] == "capture-pane":
            return _completed(args, stdout=next(captures))
        if args[1] == "display-message":
            return _completed(args, stdout=f"12345\tnode\t{tmp_path}\t1780000000\t0\n")
        return _completed(args)

    monkeypatch.setattr(terminal_smith.subprocess, "run", fake_run)
    monkeypatch.setattr(terminal_smith.time, "sleep", lambda _seconds: None)

    result = controller.ping(expected="SMITH_READY_test")

    assert result["ok"] is True
    assert result["expected"] == "SMITH_READY_test"


def test_terminal_smith_config_prefers_tailscale_serve_url(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_SMITH_TERMINAL_URL", raising=False)

    def fake_run(args, **_kwargs):
        assert args == ["tailscale", "serve", "status"]
        return _completed(args, stdout="https://iris.tail3995b4.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8010\n")

    monkeypatch.setattr(terminal_smith.subprocess, "run", fake_run)

    config = TerminalSmithConfig.from_environment(repository_root="/repo")

    assert config.terminal_url == "https://iris.tail3995b4.ts.net/"


def test_agent_runs_page_exposes_terminal_smith_controls() -> None:
    page = TestClient(freyja_main.app).get("/agent-runs")

    assert page.status_code == 200
    assert "Terminal Smith" in page.text
    assert "/agent-runs/api/terminal-smith/health" in page.text
    assert "Restart Smith" in page.text
    assert "data-terminal-action=\"restart\"" in page.text
    assert "data-terminal-action=\"interrupt\"" in page.text
    assert "data-terminal-action=\"ping\"" in page.text
    assert "Open Terminal" in page.text
    assert "leaves other Freyja services alone" in page.text


def test_agent_runs_terminal_smith_api_uses_controller(monkeypatch) -> None:
    calls: list[str] = []

    class FakeController:
        def status(self):
            calls.append("status")
            return {"ok": True, "session": "agent-smith", "state": "running"}

        def interrupt(self):
            calls.append("interrupt")
            return {"ok": True, "action": "interrupt"}

        def restart(self):
            calls.append("restart")
            return {"ok": True, "action": "restart", "status": {"ok": True}}

        def ping(self):
            calls.append("ping")
            return {"ok": True, "action": "ping", "expected": "SMITH_READY"}

    monkeypatch.setattr(freyja_main, "_terminal_smith_controller", lambda: FakeController())
    client = TestClient(freyja_main.app)

    assert client.get("/agent-runs/api/terminal-smith/health").json()["session"] == "agent-smith"
    assert client.post("/agent-runs/api/terminal-smith/interrupt").json()["action"] == "interrupt"
    assert client.post("/agent-runs/api/terminal-smith/restart").json()["action"] == "restart"
    assert client.post("/agent-runs/api/terminal-smith/ping").json()["expected"] == "SMITH_READY"
    assert calls == ["status", "interrupt", "restart", "ping"]
