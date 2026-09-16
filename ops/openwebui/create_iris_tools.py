import asyncio
import json

from open_webui.models.tools import ToolForm, ToolMeta, Tools
from open_webui.utils.plugin import load_tool_module_by_id
from open_webui.utils.tools import get_tool_specs


IRIS_DIAGNOSTICS = '''
"""Minimal Iris diagnostic tools for OpenWebUI."""

from datetime import datetime, timezone
import socket


class Tools:
    def iris_hostname(self) -> str:
        """Return the hostname visible to the OpenWebUI tool runtime."""
        return f"iris tool runtime hostname: {socket.gethostname()}"

    def iris_time(self) -> str:
        """Return the current server time visible to the OpenWebUI tool runtime."""
        return datetime.now(timezone.utc).astimezone().isoformat()
'''


IRIS_TERMINAL_DIAGNOSTICS = '''
"""Safe allowlisted local diagnostics for the OpenWebUI container runtime."""

import shutil
import subprocess
from typing import Literal


class Tools:
    _COMMANDS = {
        "hostname": ["hostname"],
        "whoami": ["whoami"],
        "pwd": ["pwd"],
        "uptime": ["uptime"],
        "ls": ["ls", "-la", "/app/backend/data"],
    }

    def local_diagnostic(self, command: Literal["hostname", "whoami", "pwd", "uptime", "ls"]) -> str:
        """Run one fixed allowlisted diagnostic command in the OpenWebUI tool runtime."""
        argv = self._COMMANDS.get(command)
        if argv is None:
            return "denied: command is not allowlisted"
        if shutil.which(argv[0]) is None:
            return f"unavailable: {argv[0]} is not installed in this runtime"
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
        except subprocess.TimeoutExpired:
            return f"timeout: {command} exceeded 5 seconds"
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 4000:
            output = output[:4000] + "\\n[truncated]"
        return f"exit={result.returncode}\\n{output}"
'''


ATLAS_STATUS = '''
"""Safe fixed Atlas status check for OpenWebUI."""

import subprocess


class Tools:
    def atlas_status(self) -> str:
        """Return Atlas hostname, user, and uptime using a fixed SSH command."""
        argv = [
            "ssh",
            "-i",
            "/app/backend/data/ssh/openwebui_status_ed25519",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "joe@100.119.235.114",
            "hostname; whoami; uptime",
        ]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        except subprocess.TimeoutExpired:
            return "timeout: Atlas status check exceeded 15 seconds"
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 4000:
            output = output[:4000] + "\\n[truncated]"
        return f"exit={result.returncode}\\n{output}"
'''


VULCAN_STATUS = '''
"""Safe fixed Vulcan status check for OpenWebUI."""

import subprocess


class Tools:
    def vulcan_status(self) -> str:
        """Return Vulcan hostname, user, and uptime using a fixed SSH command."""
        argv = [
            "ssh",
            "-i",
            "/app/backend/data/ssh/openwebui_status_ed25519",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "joe@Vulcan-1",
            "hostname; whoami; uptime",
        ]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        except subprocess.TimeoutExpired:
            return "timeout: Vulcan status check exceeded 15 seconds"
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 4000:
            output = output[:4000] + "\\n[truncated]"
        return f"exit={result.returncode}\\n{output}"
'''


VULCAN_FREE_RAM = '''
"""Safe fixed Vulcan memory check for OpenWebUI."""

import subprocess


class Tools:
    def vulcan_free_ram(self) -> str:
        """Return Vulcan memory availability using a fixed SSH command."""
        argv = [
            "ssh",
            "-i",
            "/app/backend/data/ssh/openwebui_status_ed25519",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "joe@Vulcan-1",
            "free -h",
        ]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        except subprocess.TimeoutExpired:
            return "timeout: Vulcan memory check exceeded 15 seconds"
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 4000:
            output = output[:4000] + "\\n[truncated]"
        return f"exit={result.returncode}\\n{output}"
'''


VULCAN_DIAGNOSTICS = '''
"""Safe allowlisted Vulcan diagnostics for OpenWebUI."""

import subprocess
from typing import Literal


class Tools:
    _REMOTE_COMMANDS = {
        "status": "hostname; whoami; uptime",
        "system_memory": "free -h",
        "gpu_memory": "if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader,nounits; elif command -v rocm-smi >/dev/null 2>&1; then rocm-smi --showmeminfo vram --showuse --showtemp; elif command -v radeontop >/dev/null 2>&1; then timeout 3 radeontop -d - -l 1; else echo 'no supported GPU memory tool found: nvidia-smi, rocm-smi, radeontop'; fi",
        "gpu_inventory": "if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi -L; elif command -v rocminfo >/dev/null 2>&1; then rocminfo | grep -E 'Name:|Marketing Name' | head -40; elif command -v lspci >/dev/null 2>&1; then lspci | grep -Ei 'vga|3d|display|nvidia|amd|ati'; else echo 'no supported GPU inventory tool found'; fi",
        "disk": "df -h / /home 2>/dev/null || df -h",
        "load": "uptime; ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -12",
    }

    def vulcan_diagnostic(
        self,
        check: Literal["status", "system_memory", "gpu_memory", "gpu_inventory", "disk", "load"],
    ) -> str:
        """Run one fixed allowlisted diagnostic check on Vulcan over SSH."""
        remote_command = self._REMOTE_COMMANDS.get(check)
        if remote_command is None:
            return "denied: diagnostic check is not allowlisted"
        argv = [
            "ssh",
            "-i",
            "/app/backend/data/ssh/openwebui_status_ed25519",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "joe@Vulcan-1",
            remote_command,
        ]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)
        except subprocess.TimeoutExpired:
            return f"timeout: Vulcan diagnostic {check} exceeded 20 seconds"
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 6000:
            output = output[:6000] + "\\n[truncated]"
        return f"exit={result.returncode}\\n{output}"
'''


VULCAN_AGENT = '''
"""Safe allowlisted Vulcan agent actions for OpenWebUI."""

import subprocess
from typing import Literal


class Tools:
    _REMOTE_ACTIONS = {
        "status": "hostname; whoami; uptime",
        "system_memory": "free -h",
        "gpu_memory": "if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader,nounits; elif command -v rocm-smi >/dev/null 2>&1; then rocm-smi --showmeminfo vram --showuse --showtemp; else echo 'no supported GPU memory tool found: nvidia-smi or rocm-smi'; fi",
        "gpu_inventory": "if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi -L; elif command -v rocminfo >/dev/null 2>&1; then rocminfo | grep -E 'Name:|Marketing Name' | head -40; elif command -v lspci >/dev/null 2>&1; then lspci | grep -Ei 'vga|3d|display|nvidia|amd|ati'; else echo 'no supported GPU inventory tool found'; fi",
        "disk": "df -h / /home 2>/dev/null || df -h",
        "load": "uptime; ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -12",
        "freyja_os_git_status": "cd ~/freyja-os 2>/dev/null || cd /srv/freyja-os 2>/dev/null || cd /opt/freyja-os 2>/dev/null || exit 12; git status --short --branch",
        "freyja_os_recent_commits": "cd ~/freyja-os 2>/dev/null || cd /srv/freyja-os 2>/dev/null || cd /opt/freyja-os 2>/dev/null || exit 12; git log --oneline -5",
        "freyja_os_test_inventory": "cd ~/freyja-os 2>/dev/null || cd /srv/freyja-os 2>/dev/null || cd /opt/freyja-os 2>/dev/null || exit 12; find . -maxdepth 3 \\( -name 'pyproject.toml' -o -name 'package.json' -o -name 'pytest.ini' -o -name 'tox.ini' \\) -print",
    }

    def vulcan_agent(
        self,
        action: Literal[
            "status",
            "system_memory",
            "gpu_memory",
            "gpu_inventory",
            "disk",
            "load",
            "freyja_os_git_status",
            "freyja_os_recent_commits",
            "freyja_os_test_inventory",
        ],
    ) -> str:
        """Run one approved diagnostic or coding-readiness action on Vulcan over SSH."""
        remote_command = self._REMOTE_ACTIONS.get(action)
        if remote_command is None:
            return "denied: action is not allowlisted"
        argv = [
            "ssh",
            "-i",
            "/app/backend/data/ssh/openwebui_status_ed25519",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "joe@Vulcan-1",
            remote_command,
        ]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=25, check=False)
        except subprocess.TimeoutExpired:
            return f"timeout: Vulcan action {action} exceeded 25 seconds"
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 8000:
            output = output[:8000] + "\\n[truncated]"
        return f"exit={result.returncode}\\n{output}"
'''


OPENWEBUI_TERMINAL_BRIDGE = '''
"""Constrained tmux terminal bridge for OpenWebUI coding-agent sessions."""

import json
import shlex
import subprocess
from typing import Literal


class Tools:
    _SSH_BASE = [
        "ssh",
        "-i",
        "/app/backend/data/ssh/openwebui_status_ed25519",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "UserKnownHostsFile=/app/backend/data/ssh/known_hosts",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "freyja@iris",
    ]
    _REMOTE_SCRIPT = "~/freyja-os/scripts/openwebui-terminal-bridge.py"

    def _run_bridge(self, args: list[str], stdin: str | None = None, timeout: int = 20) -> str:
        remote_command = " ".join([self._REMOTE_SCRIPT, *[shlex.quote(arg) for arg in args]])
        try:
            result = subprocess.run(
                [*self._SSH_BASE, remote_command],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"ok": False, "status": "timeout", "timeout_seconds": timeout})
        output = (result.stdout or result.stderr or "").strip()
        if len(output) > 50000:
            output = output[-50000:]
        return output

    def terminal_start(
        self,
        session: str = "openwebui-qwen",
        workdir: str = "~/freyja-os",
        agent: Literal["qwen"] = "qwen",
    ) -> str:
        """Start a named persistent Qwen coding-agent tmux session on Iris."""
        return self._run_bridge(["start", session, "--agent", agent, "--workdir", workdir], timeout=30)

    def terminal_status(self, session: str = "openwebui-qwen") -> str:
        """Report whether a named coding-agent tmux session is running."""
        return self._run_bridge(["status", session], timeout=15)

    def terminal_send(self, text: str, session: str = "openwebui-qwen", enter: bool = False) -> str:
        """Send literal keyboard text to a named tmux session; optionally press Enter."""
        args = ["send", session, "--stdin"]
        if enter:
            args.append("--enter")
        return self._run_bridge(args, stdin=text, timeout=15)

    def terminal_ctrl_c(self, session: str = "openwebui-qwen") -> str:
        """Send Ctrl-C to a named tmux session."""
        return self._run_bridge(["send", session, "--ctrl-c"], timeout=15)

    def terminal_read(self, session: str = "openwebui-qwen", lines: int = 200) -> str:
        """Read recent output from a named tmux session."""
        bounded_lines = max(1, min(int(lines), 2000))
        return self._run_bridge(["read", session, "--lines", str(bounded_lines)], timeout=15)

    def terminal_stop(self, session: str = "openwebui-qwen") -> str:
        """Interrupt and remove a named tmux session; this is the kill switch."""
        return self._run_bridge(["stop", session], timeout=20)
'''


OPENCODE_RUNTIME = '''
"""Direct OpenCode controls for approved Freyja coding-agent sessions."""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request


class Tools:
    _ALIASES_FILE = "/app/backend/data/opencode-runtime-aliases.json"
    _MODEL = {"providerID": "vulcan-nexus", "modelID": "@preset/freyja-coder"}
    _DEFAULTS = {
        "atlas-dashboard": {
            "base_url": "http://100.119.235.114:4097",
            "directory": "/home/joe/cloyd-services",
            "password_file": "/app/backend/data/secrets/opencode-password",
            "session": "",
            "username": "joe",
        },
        "freyja-code": {
            "base_url": "http://100.115.228.56:4097",
            "directory": "/Users/freyja/freyja-os",
            "password_file": "/app/backend/data/secrets/opencode-iris-password",
            "session": "",
            "username": "joe",
        },
    }

    def _aliases(self) -> dict:
        try:
            with open(self._ALIASES_FILE, "r", encoding="utf-8") as handle:
                aliases = json.load(handle)
        except Exception:
            aliases = {}
        for alias, defaults in self._DEFAULTS.items():
            aliases.setdefault(alias, defaults.copy())
        return aliases

    def _save_aliases(self, aliases: dict) -> None:
        with open(self._ALIASES_FILE, "w", encoding="utf-8") as handle:
            json.dump(aliases, handle, indent=2, sort_keys=True)

    def _config(self, alias: str) -> dict:
        aliases = self._aliases()
        value = aliases.get(alias)
        if isinstance(value, str):
            value = {"session": value}
        if not isinstance(value, dict):
            value = {}
        defaults = self._DEFAULTS.get(alias, self._DEFAULTS["freyja-code"])
        return {**defaults, **value}

    def _password(self, config: dict) -> str:
        with open(config["password_file"], "r", encoding="utf-8") as handle:
            return handle.read().strip()

    def _request(self, config: dict, method: str, path: str, body: dict | None = None, query: dict | None = None, timeout: int = 300):
        if query:
            path = f"{path}?{urllib.parse.urlencode(query)}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(f"{config['base_url'].rstrip('/')}{path}", data=data, method=method)
        credentials = f"{config['username']}:{self._password(config)}".encode("utf-8")
        request.add_header("authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))
        if body is not None:
            request.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            return {"ok": False, "status": exc.code, "error": exc.read().decode("utf-8", errors="replace")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not payload:
            return {"ok": True}
        result = json.loads(payload)
        if isinstance(result, dict):
            result.setdefault("ok", True)
        return result

    def _session(self, alias: str) -> tuple[dict, str]:
        config = self._config(alias)
        session = config.get("session") or ""
        return config, session

    def _recent_action(self, parts: list[dict]) -> dict | None:
        for part in reversed(parts):
            if part.get("type") == "tool":
                state = part.get("state") or {}
                return {
                    "tool": part.get("tool"),
                    "status": state.get("status"),
                    "title": state.get("title"),
                    "input": state.get("input"),
                    "error": state.get("error"),
                }
        return None

    def _summarize_message(self, session: str, result: dict) -> dict:
        parts = result.get("parts", []) if isinstance(result, dict) else []
        text = "\\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()
        action = self._recent_action(parts)
        return {
            "ok": True,
            "session": session,
            "state": "completed" if (result.get("info") or {}).get("time", {}).get("completed") else "working",
            "message": (result.get("info") or {}).get("id"),
            "recent_action": action,
            "result": text,
        }

    def opencode_start(self, alias: str = "freyja-code", directory: str = "") -> str:
        """Start an OpenCode coding-agent session for an approved alias."""
        config = self._config(alias)
        target_directory = directory or config["directory"]
        result = self._request(config, "POST", "/session", {"title": alias}, query={"directory": target_directory}, timeout=60)
        if not result.get("ok", True):
            return json.dumps(result)
        aliases = self._aliases()
        config["session"] = result["id"]
        aliases[alias] = config
        self._save_aliases(aliases)
        return json.dumps({"ok": True, "alias": alias, "session": result["id"], "working_directory": result.get("directory"), "state": "idle"})

    def opencode_send(self, prompt: str, alias: str = "freyja-code") -> str:
        """Send a coding or development prompt to an OpenCode session."""
        config, session = self._session(alias)
        if not session:
            start = json.loads(self.opencode_start(alias, config["directory"]))
            if not start.get("ok"):
                return json.dumps(start)
            config, session = self._session(alias)
        result = self._request(config, "POST", f"/session/{session}/message", {"model": self._MODEL, "agent": "build", "parts": [{"type": "text", "text": prompt}]})
        if not result.get("ok", True):
            return json.dumps(result)
        return json.dumps(self._summarize_message(session, result))

    def opencode_shell(self, command: str, alias: str = "freyja-code") -> str:
        """Run a shell command through an existing OpenCode session and return output."""
        config, session = self._session(alias)
        if not session:
            return json.dumps({"ok": False, "error": f"Unknown OpenCode session alias: {alias}"})
        result = self._request(config, "POST", f"/session/{session}/shell", {"agent": "build", "model": self._MODEL, "command": command})
        if not result.get("ok", True):
            return json.dumps(result)
        return json.dumps(self._summarize_message(session, result))

    def opencode_status(self, alias: str = "freyja-code") -> str:
        """Return OpenCode session state, working directory, and recent action."""
        config, session = self._session(alias)
        if not session:
            return json.dumps({"ok": False, "error": f"Unknown OpenCode session alias: {alias}"})
        statuses = self._request(config, "GET", "/session/status", timeout=30)
        current = self._request(config, "GET", f"/session/{session}", timeout=30)
        messages = self._request(config, "GET", f"/session/{session}/message", query={"limit": "1"}, timeout=30)
        parts = messages[0].get("parts", []) if isinstance(messages, list) and messages else []
        return json.dumps({
            "ok": True,
            "alias": alias,
            "session": session,
            "working_directory": current.get("directory") if isinstance(current, dict) else None,
            "state": statuses.get(session, "idle") if isinstance(statuses, dict) else "unknown",
            "recent_action": self._recent_action(parts),
        })

    def opencode_output(self, alias: str = "freyja-code", limit: int = 5) -> str:
        """Return recent OpenCode messages and tool output for a session."""
        config, session = self._session(alias)
        if not session:
            return json.dumps({"ok": False, "error": f"Unknown OpenCode session alias: {alias}"})
        messages = self._request(config, "GET", f"/session/{session}/message", query={"limit": str(max(1, min(int(limit), 25)))}, timeout=30)
        return json.dumps({"ok": True, "session": session, "messages": messages})

    def opencode_stop(self, alias: str = "freyja-code") -> str:
        """Abort current OpenCode work for a session."""
        config, session = self._session(alias)
        if not session:
            return json.dumps({"ok": False, "error": f"Unknown OpenCode session alias: {alias}"})
        return json.dumps({"ok": True, "session": session, "aborted": self._request(config, "POST", f"/session/{session}/abort", timeout=30)})
'''


CLOYD_SMITH_LOOP = '''
"""Canonical Cloyd-Smith loop controls through Freyja Director."""

import json
import urllib.error
import urllib.request

class Tools:
    base_url = "http://100.115.228.56:8000"

    def _request(self, method: str, path: str, body: dict | None = None) -> str:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        if body is not None:
            request.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return json.dumps({"ok": False, "status": exc.code, "error": detail, "source": self.base_url})
        except OSError as exc:
            return json.dumps({"ok": False, "error": str(exc), "source": self.base_url})
        return payload or json.dumps({"ok": True, "source": self.base_url})

    def cloyd_smith_submit(
        self,
        objective: str,
        prompt: str = "",
        smith_alias: str = "freyja-code",
        acceptance_criteria: str = "",
    ) -> str:
        """Deprecated: ask Joe/Codex to create new jobs through Freyja, then use status/actions here."""
        return json.dumps(
            {
                "ok": False,
                "status": "submit_not_exposed",
                "objective": objective,
                "next_action": "Use the Agent Runs monitor to create/reconcile jobs; this OpenWebUI tool only reviews and clears canonical jobs.",
                "monitor": f"{self.base_url}/agent-runs",
            }
        )

    def cloyd_smith_status(self, job_id: str = "") -> str:
        """Return canonical Agent Runs status; job_id filters the returned runs client-side."""
        status = json.loads(self._request("GET", "/agent-runs/api/status"))
        if job_id and status.get("ok"):
            status["runs"] = [run for run in status.get("runs", []) if run.get("job_id") == job_id]
            status["job"] = status["runs"][0] if status["runs"] else None
            if not status["job"]:
                status["ok"] = False
                status["error"] = f"Job {job_id} is not visible in the canonical Agent Runs monitor."
        return json.dumps(status)

    def cloyd_smith_record(self, job_id: str, event_type: str, payload_json: str = "{}", status: str = "", next_action: str = "") -> str:
        """Deprecated: use mark_done, mark_blocked, retry, follow_up, or stop to change canonical job state."""
        return json.dumps(
            {
                "ok": False,
                "status": "record_not_exposed",
                "job_id": job_id,
                "next_action": "Use a concrete queue-clearing action: cloyd_smith_mark_done, cloyd_smith_mark_blocked, cloyd_smith_retry, cloyd_smith_follow_up, cloyd_smith_replace, or cloyd_smith_stop.",
            }
        )

    def cloyd_smith_stop(self, job_id: str) -> str:
        """Stop a queued or running canonical Cloyd-Smith job."""
        return self._request("POST", f"/agent-runs/api/jobs/{job_id}/stop")

    def cloyd_smith_retry(self, job_id: str) -> str:
        """Retry one blocked, stale, or stopped job after Freyja preflights OpenCode health."""
        return self._request("POST", f"/agent-runs/api/jobs/{job_id}/retry")

    def cloyd_smith_mark_done(self, job_id: str) -> str:
        """Mark a needs-review job done after evidence proves the objective."""
        return self._request("POST", f"/agent-runs/api/jobs/{job_id}/done")

    def cloyd_smith_mark_blocked(self, job_id: str, reason: str = "") -> str:
        """Mark an active or needs-review job blocked with a concrete reason."""
        return self._request("POST", f"/agent-runs/api/jobs/{job_id}/block")

    def cloyd_smith_follow_up(self, job_id: str, prompt: str) -> str:
        """Queue exactly one bounded follow-up prompt for a review, blocked, or stale job."""
        return self._request("POST", f"/agent-runs/api/jobs/{job_id}/follow-up", {"prompt": prompt})

    def cloyd_smith_replace(
        self,
        job_id: str,
        prompt: str,
        objective: str = "",
        smith_alias: str = "",
        acceptance_criteria: str = "",
    ) -> str:
        """Create a narrower replacement job for a blocked canonical job and supersede the old job."""
        criteria = [line.strip() for line in acceptance_criteria.splitlines() if line.strip()]
        body = {"prompt": prompt, "acceptance_criteria": criteria}
        if objective:
            body["objective"] = objective
        if smith_alias:
            body["smith_alias"] = smith_alias
        return self._request("POST", f"/agent-runs/api/jobs/{job_id}/replace", body)
'''


async def upsert_tool(tool_id: str, name: str, description: str, content: str) -> None:
    module, frontmatter = await load_tool_module_by_id(tool_id, content=content)
    specs = get_tool_specs(module)
    form = ToolForm(
        id=tool_id,
        name=name,
        content=content,
        meta=ToolMeta(description=description, manifest=frontmatter, has_user_valves=False),
        access_grants=[],
    )
    existing = await Tools.get_tool_by_id(tool_id)
    if existing:
        updated = await Tools.update_tool_by_id(
            tool_id,
            {
                "name": form.name,
                "content": form.content,
                "specs": specs,
                "meta": form.meta.model_dump(),
                "valves": {},
            },
        )
        print("updated", updated.id, [spec["name"] for spec in specs])
    else:
        created = await Tools.insert_new_tool("codex-local", form, specs)
        print("created", created.id, [spec["name"] for spec in specs])


async def main() -> None:
    await upsert_tool(
        "iris_diagnostics",
        "Iris Diagnostics",
        "Minimal safe OpenWebUI runtime diagnostics for Iris.",
        IRIS_DIAGNOSTICS,
    )
    await upsert_tool(
        "iris_terminal_diagnostics",
        "Iris Terminal Diagnostics",
        "Safe allowlisted local diagnostics for the OpenWebUI container runtime.",
        IRIS_TERMINAL_DIAGNOSTICS,
    )
    await upsert_tool(
        "atlas_status",
        "Atlas Status",
        "Safe fixed SSH status check for Atlas from the OpenWebUI runtime.",
        ATLAS_STATUS,
    )
    await upsert_tool(
        "vulcan_status",
        "Vulcan Status",
        "Safe fixed SSH status check for Vulcan from the OpenWebUI runtime.",
        VULCAN_STATUS,
    )
    await upsert_tool(
        "vulcan_free_ram",
        "Vulcan Free RAM",
        "Safe fixed SSH memory check for Vulcan from the OpenWebUI runtime.",
        VULCAN_FREE_RAM,
    )
    await upsert_tool(
        "vulcan_diagnostics",
        "Vulcan Diagnostics",
        "Safe allowlisted SSH diagnostics for Vulcan from the OpenWebUI runtime.",
        VULCAN_DIAGNOSTICS,
    )
    await upsert_tool(
        "vulcan_agent",
        "Vulcan Agent",
        "Single safe allowlisted SSH action surface for Vulcan diagnostics and coding readiness.",
        VULCAN_AGENT,
    )
    await upsert_tool(
        "openwebui_terminal_bridge",
        "OpenWebUI Terminal Bridge",
        "Constrained SSH-to-tmux keyboard bridge for persistent Qwen coding sessions.",
        OPENWEBUI_TERMINAL_BRIDGE,
    )
    await upsert_tool(
        "opencode_runtime",
        "OpenCode Runtime",
        "Control Freyja's approved OpenCode coding-agent sessions through Freyja Director.",
        OPENCODE_RUNTIME,
    )
    await upsert_tool(
        "cloyd_smith_loop",
        "Cloyd Smith Loop 5.2",
        "Durable Freyja 5.2 job receipts and status for Cloyd supervising Smith outside the browser stream.",
        CLOYD_SMITH_LOOP,
    )

    rows = []
    for tool_id in (
        "iris_diagnostics",
        "iris_terminal_diagnostics",
        "atlas_status",
        "vulcan_status",
        "vulcan_free_ram",
        "vulcan_diagnostics",
        "vulcan_agent",
        "openwebui_terminal_bridge",
        "opencode_runtime",
        "cloyd_smith_loop",
    ):
        tool = await Tools.get_tool_by_id(tool_id)
        rows.append({"id": tool.id, "name": tool.name, "specs": tool.specs})
    print(json.dumps(rows, indent=2))


asyncio.run(main())
