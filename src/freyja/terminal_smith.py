import json
import os
import re
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SECRET_ENV_NAMES = {
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
}


@dataclass(frozen=True)
class TerminalSmithConfig:
    tmux_bin: str = "/opt/homebrew/bin/tmux"
    tmux_session: str = "agent-smith"
    qwen_bin: str = "/opt/homebrew/bin/qwen"
    qwen_home: str = str(Path.home() / ".local" / "state" / "freyja" / "gateway-remote" / "qwen-smith")
    token_file: str = str(Path.home() / ".local" / "state" / "freyja" / "gateway-remote" / "msty-nexus-token")
    base_url: str = "http://100.94.80.21:3939/v1"
    model: str = "@preset/freyja-coder"
    workdir: str = str(Path.home())
    capture_dir: str = "logs/smith-session-captures"
    terminal_url: str = "https://iris.tail3995b4.ts.net/"
    timeout_seconds: float = 8.0

    @classmethod
    def from_environment(cls, *, repository_root: str | Path | None = None) -> "TerminalSmithConfig":
        capture_dir = os.environ.get("AGENT_SMITH_CAPTURE_DIR")
        if not capture_dir and repository_root:
            capture_dir = str(Path(repository_root) / "logs" / "smith-session-captures")
        terminal_url = os.environ.get("AGENT_SMITH_TERMINAL_URL") or _discover_tailscale_serve_url() or cls.terminal_url
        return cls(
            tmux_bin=os.environ.get("AGENT_SMITH_TMUX_BIN", cls.tmux_bin),
            tmux_session=os.environ.get("AGENT_SMITH_TMUX_SESSION", cls.tmux_session),
            qwen_bin=os.environ.get("FREYJA_GATEWAY_REMOTE_QWEN_BIN", cls.qwen_bin),
            qwen_home=os.environ.get("FREYJA_GATEWAY_REMOTE_QWEN_HOME", cls.qwen_home),
            token_file=os.environ.get("FREYJA_GATEWAY_REMOTE_NEXUS_TOKEN_FILE", cls.token_file),
            base_url=os.environ.get("FREYJA_GATEWAY_REMOTE_VULCAN_MODEL_BASE_URL", cls.base_url),
            model=os.environ.get("FREYJA_GATEWAY_REMOTE_VULCAN_MODEL", cls.model),
            workdir=os.environ.get("AGENT_SMITH_WORKDIR", cls.workdir),
            capture_dir=capture_dir or cls.capture_dir,
            terminal_url=terminal_url,
        )


class TerminalSmithController:
    """Controls the free-running Agent Smith Qwen session in tmux."""

    def __init__(self, config: TerminalSmithConfig):
        self.config = config

    def status(self, *, include_output: bool = True) -> dict[str, Any]:
        session = self.config.tmux_session
        exists = self._run([self.config.tmux_bin, "has-session", "-t", session], check=False)
        base: dict[str, Any] = {
            "ok": exists.returncode == 0,
            "session": session,
            "state": "running" if exists.returncode == 0 else "missing",
            "model": self.config.model,
            "base_url": self.config.base_url,
            "workdir": self.config.workdir,
            "terminal_url": self.config.terminal_url,
            "launcher_command": self.launcher_command(),
        }
        if exists.returncode != 0:
            base["error"] = (exists.stderr or exists.stdout or "tmux session is not running").strip()
            return base

        pane = self._run(
            [
                self.config.tmux_bin,
                "display-message",
                "-p",
                "-t",
                f"{session}:0.0",
                "#{pane_pid}\t#{pane_current_command}\t#{pane_current_path}\t#{session_created}\t#{session_attached}",
            ],
            check=False,
        )
        if pane.returncode == 0:
            parts = pane.stdout.strip().split("\t")
            if len(parts) >= 5:
                base.update(
                    {
                        "pane_pid": parts[0],
                        "pane_command": parts[1],
                        "pane_path": parts[2],
                        "session_created_epoch": _int_or_none(parts[3]),
                        "session_attached": parts[4] == "1",
                    }
                )
        if include_output:
            base["recent_output"] = self.capture_pane(lines=80).get("output", "")
        return base

    def interrupt(self) -> dict[str, Any]:
        before = self.capture_pane(lines=160)
        result = self._run([self.config.tmux_bin, "send-keys", "-t", f"{self.config.tmux_session}:0.0", "C-c"], check=False)
        status = self.status(include_output=True)
        return {
            "ok": result.returncode == 0,
            "action": "interrupt",
            "before": before,
            "status": status,
            "error": result.stderr.strip() if result.returncode != 0 else "",
        }

    def restart(self) -> dict[str, Any]:
        before = self.capture_to_file(reason="restart")
        existed = before.get("session_exists") is True
        if existed:
            self._run([self.config.tmux_bin, "send-keys", "-t", f"{self.config.tmux_session}:0.0", "C-c"], check=False)
            time.sleep(0.2)
            self._run([self.config.tmux_bin, "kill-session", "-t", self.config.tmux_session], check=False)

        self._write_qwen_settings()
        env = self._qwen_env()
        command = self.launcher_command()
        start = self._run(
            [
                self.config.tmux_bin,
                "new-session",
                "-d",
                "-s",
                self.config.tmux_session,
                "-c",
                self.config.workdir,
                command,
            ],
            env=env,
            check=False,
        )
        status = self.status(include_output=True)
        ok = start.returncode == 0 and status.get("ok") is True
        return {
            "ok": ok,
            "action": "restart",
            "interrupted_existing_session": existed,
            "capture": before,
            "start": {
                "ok": start.returncode == 0,
                "returncode": start.returncode,
                "stderr": start.stderr.strip(),
                "stdout": start.stdout.strip(),
            },
            "status": status,
        }

    def ping(self, *, expected: str | None = None, timeout_seconds: float = 90.0) -> dict[str, Any]:
        expected = expected or f"SMITH_READY_{uuid.uuid4().hex[:8]}"
        prompt = f"Reply exactly: {expected}"
        send = self._run([self.config.tmux_bin, "send-keys", "-t", f"{self.config.tmux_session}:0.0", prompt, "Enter"], check=False)
        if send.returncode != 0:
            return {"ok": False, "action": "ping", "error": send.stderr.strip(), "status": self.status(include_output=True)}
        deadline = time.monotonic() + timeout_seconds
        last_output = ""
        response_marker = f"\u25c6 {expected}"
        while time.monotonic() < deadline:
            capture = self.capture_pane(lines=120)
            last_output = capture.get("output", "")
            if response_marker in last_output:
                return {"ok": True, "action": "ping", "expected": expected, "status": self.status(include_output=True)}
            time.sleep(2.0)
        return {
            "ok": False,
            "action": "ping",
            "expected": expected,
            "error": f"Timed out waiting for {expected}",
            "recent_output": last_output,
            "status": self.status(include_output=True),
        }

    def capture_pane(self, *, lines: int = 160) -> dict[str, Any]:
        session = self.config.tmux_session
        exists = self._run([self.config.tmux_bin, "has-session", "-t", session], check=False)
        if exists.returncode != 0:
            return {"ok": False, "session_exists": False, "output": "", "error": (exists.stderr or exists.stdout).strip()}
        result = self._run(
            [self.config.tmux_bin, "capture-pane", "-pt", f"{session}:0.0", "-S", f"-{int(lines)}"],
            check=False,
        )
        return {
            "ok": result.returncode == 0,
            "session_exists": True,
            "output": result.stdout,
            "error": result.stderr.strip() if result.returncode != 0 else "",
        }

    def capture_to_file(self, *, reason: str) -> dict[str, Any]:
        capture = self.capture_pane(lines=400)
        capture_dir = Path(self.config.capture_dir).expanduser()
        capture_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = capture_dir / f"{self.config.tmux_session}-{reason}-{timestamp}.log"
        metadata = {
            "captured_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "session": self.config.tmux_session,
            "launcher_command": self.launcher_command(),
            "base_url": self.config.base_url,
            "model": self.config.model,
            "workdir": self.config.workdir,
            "session_exists": capture.get("session_exists"),
            "capture_ok": capture.get("ok"),
            "capture_error": capture.get("error", ""),
        }
        path.write_text(json.dumps(metadata, indent=2) + "\n\n" + capture.get("output", ""), encoding="utf-8")
        return {**metadata, "path": str(path)}

    def launcher_command(self) -> str:
        return shlex.join([self.config.qwen_bin, "--model", self.config.model])

    def _write_qwen_settings(self) -> None:
        qwen_home = Path(self.config.qwen_home).expanduser()
        qwen_home.mkdir(parents=True, exist_ok=True)
        settings = {
            "$version": 4,
            "general": {"enableAutoUpdate": False},
            "model": {"name": self.config.model, "baseUrl": self.config.base_url},
            "modelProviders": {
                "openai": [
                    {
                        "id": self.config.model,
                        "name": "Vulcan Nexus",
                        "baseUrl": self.config.base_url,
                        "envKey": "OPENAI_API_KEY",
                        "generationConfig": {"contextWindowSize": 128000},
                        "models": [self.config.model],
                    }
                ]
            },
            "security": {"auth": {"baseUrl": self.config.base_url, "selectedType": "openai"}},
            "ui": {"autoModeAcknowledged": True},
        }
        (qwen_home / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    def _qwen_env(self) -> dict[str, str]:
        token_path = Path(self.config.token_file).expanduser()
        if not token_path.is_file():
            raise FileNotFoundError(f"Agent Smith Nexus bearer token not found at {token_path}")
        env = dict(os.environ)
        for name in SECRET_ENV_NAMES:
            env.pop(name, None)
        env.update(
            {
                "PATH": "/opt/homebrew/bin:/Users/freyja/.local/npm/bin:/Users/freyja/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                "TERM": env.get("TERM", "xterm-256color"),
                "QWEN_HOME": str(Path(self.config.qwen_home).expanduser()),
                "OPENAI_BASE_URL": self.config.base_url,
                "OPENAI_API_KEY": token_path.read_text(encoding="utf-8").strip(),
                "FREYJA_GATEWAY_REMOTE_VULCAN_MODEL": self.config.model,
            }
        )
        return env

    def _run(
        self,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            check=check,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
            env=env,
        )


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _discover_tailscale_serve_url() -> str | None:
    try:
        result = subprocess.run(
            ["tailscale", "serve", "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = re.search(r"https://[^\s]+", result.stdout)
    if not match:
        return None
    return match.group(0).rstrip("/") + "/"
