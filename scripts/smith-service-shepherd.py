#!/usr/bin/env python3
"""Observation-only service watchdog for Agent Smith.

Smith lives outside Docker so it can observe Docker-backed services without
sharing their failure domain or attempting autonomous repair.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("FREYJA_REPO", "/Users/freyja/freyja-os"))
CONFIG_PATH = Path(os.environ.get("SMITH_SHEPHERD_CONFIG", REPO / "config/agent-smith-watchdog.yaml"))
LOG_PATH = Path(os.environ.get("SMITH_SHEPHERD_LOG", REPO / "logs/smith-service-shepherd.jsonl"))
STATUS_PATH = Path(
    os.environ.get(
        "SMITH_SHEPHERD_STATUS",
        Path.home() / ".local/state/freyja/smith-service-shepherd-status.json",
    )
)
ALERT_ENV_PATH = Path(os.environ.get("SMITH_ALERT_ENV_FILE", Path.home() / ".config/freyja-os/smith-alert.env"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(command: list[str], timeout: int = 20, cwd: Path | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd or REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def read_alert_env(path: Path) -> dict[str, str]:
    """Read only the dedicated fixed-recipient Discord delivery credential."""
    values = {
        key: os.environ.get(key, "").strip()
        for key in ("SMITH_DISCORD_ALERT_BOT_TOKEN", "SMITH_DISCORD_ALERT_RECIPIENT_ID")
    }
    if not path.is_file():
        return {key: value for key, value in values.items() if value}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"SMITH_DISCORD_ALERT_BOT_TOKEN", "SMITH_DISCORD_ALERT_RECIPIENT_ID"} and not values.get(key):
            values[key] = value.strip()
    return {key: value for key, value in values.items() if value}


def http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None, timeout: int = 8) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else None
            return {"ok": 200 <= response.status < 300, "status": response.status, "body": parsed}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def send_discord_alert(config: dict[str, Any], text: str) -> dict[str, Any]:
    delivery = ((config.get("smith_shepherd") or {}).get("alert_delivery") or {})
    if not delivery.get("enabled") or delivery.get("transport") != "discord":
        return {"ok": False, "reason": "discord alert delivery is disabled"}
    values = read_alert_env(ALERT_ENV_PATH)
    token = values.get("SMITH_DISCORD_ALERT_BOT_TOKEN", "")
    recipient_id = values.get("SMITH_DISCORD_ALERT_RECIPIENT_ID", "")
    if not token or not recipient_id:
        return {"ok": False, "reason": "dedicated Discord alert credential is unavailable"}
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "FreyjaDiscordDmConnector/0.1",
        "Content-Type": "application/json",
    }
    try:
        open_dm = urllib.request.Request(
            "https://discord.com/api/v10/users/@me/channels",
            data=json.dumps({"recipient_id": recipient_id}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(open_dm, timeout=15) as response:
            channel = json.loads(response.read().decode("utf-8"))
        channel_id = str(channel.get("id") or "")
        if not channel_id:
            return {"ok": False, "reason": "Discord did not return a DM channel"}
        message = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=json.dumps({"content": text[:1800]}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(message, timeout=15) as response:
            delivered = 200 <= response.status < 300
        return {"ok": delivered, "transport": "discord", "recipient": delivery.get("recipient"), "delivery": "accepted" if delivered else "rejected"}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "transport": "discord", "recipient": delivery.get("recipient"), "reason": type(exc).__name__}


def launchctl_state(label: str) -> dict[str, Any]:
    domain = f"gui/{os.getuid()}/{label}"
    result = run(["launchctl", "print", domain], timeout=10)
    state = {"label": label, "loaded": result["ok"]}
    for line in result["stdout"].splitlines():
        stripped = line.strip()
        if stripped.startswith("state =") and "state" not in state:
            state["state"] = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid ="):
            state["pid"] = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("last exit code ="):
            state["last_exit_code"] = stripped.split("=", 1)[1].strip()
    return state


def observe_launch_agent(label: str) -> dict[str, Any]:
    state = launchctl_state(label)
    if state.get("state") == "running" or state.get("pid"):
        return {"action": "observe_only", "healthy": True, "state": state}
    return {"action": "observe_only", "healthy": False, "state": state}


def docker_ok() -> bool:
    return run(["docker", "info"], timeout=12)["ok"]


def open_docker_desktop(dry_run: bool) -> dict[str, Any]:
    if docker_ok():
        return {"action": "none", "ok": True}
    if platform.system() != "Darwin":
        return {"action": "none", "ok": False, "reason": "non_darwin_host"}
    if dry_run:
        return {"action": "would_open_docker_desktop", "ok": False}
    started = run(["open", "-a", "Docker"], timeout=15)
    return {"action": "open_docker_desktop", "ok": started["ok"], "result": started}


def compose_ps(compose: dict[str, Any]) -> dict[str, Any]:
    command = ["docker", "compose"]
    env_file = compose.get("env_file")
    if env_file:
        command += ["--env-file", str(env_file)]
    for compose_file in compose.get("files") or []:
        command += ["-f", str(compose_file)]
    command += ["ps", "--format", "json"]
    result = run(command, timeout=25, cwd=Path(compose.get("project_dir") or REPO))
    services: list[dict[str, Any]] = []
    if result["ok"] and result["stdout"]:
        for line in result["stdout"].splitlines():
            try:
                services.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"ok": result["ok"], "services": services, "result": result}


def compose_up(compose: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    status = compose_ps(compose)
    running = [service for service in status["services"] if service.get("State") == "running"]
    if status["ok"] and running:
        return {"action": "none", "status": status}
    if not compose.get("repair"):
        return {"action": "observe_only", "status": status}
    if dry_run:
        return {"action": "would_compose_up", "status": status}
    command = ["docker", "compose"]
    env_file = compose.get("env_file")
    if env_file:
        command += ["--env-file", str(env_file)]
    for compose_file in compose.get("files") or []:
        command += ["-f", str(compose_file)]
    command += ["up", "-d"]
    return {
        "action": "compose_up",
        "status": status,
        "result": run(command, timeout=120, cwd=Path(compose.get("project_dir") or REPO)),
    }


def ollama_tags(base_url: str) -> dict[str, Any]:
    return http_json(f"{base_url.rstrip('/')}/api/tags")


def model_present(tags: dict[str, Any], model: str) -> bool:
    models = ((tags.get("body") or {}).get("models") or []) if tags.get("ok") else []
    return any(item.get("name") == model or item.get("model") == model for item in models if isinstance(item, dict))


def probe_smith_routes(config: dict[str, Any]) -> dict[str, Any]:
    routes = ((config.get("smith_shepherd") or {}).get("model_routes") or {})
    primary = routes.get("primary") or {}
    backdoor = routes.get("openclaw_backdoor") or {}
    primary_base = primary.get("base_url", "http://100.94.80.21:11434")
    primary_model = primary.get("model", "qwen3.8:27b")
    openclaw_model = os.environ.get(backdoor.get("model_env", "SMITH_OPENCLAW_MODEL"), backdoor.get("default_model", "openclaw"))
    tags = ollama_tags(primary_base)
    return {
        "primary": {
            "base_url": primary_base,
            "model": primary_model,
            "available": model_present(tags, primary_model),
        },
        "openclaw_backdoor": {
            "base_url": backdoor.get("base_url", primary_base),
            "model": openclaw_model,
            "available": model_present(tags, openclaw_model),
        },
        "tags_ok": tags.get("ok"),
    }


def one_cycle(dry_run: bool) -> dict[str, Any]:
    config = read_yaml(CONFIG_PATH)
    shepherd = config.get("smith_shepherd") or {}
    disabled = set(shepherd.get("disabled_launch_agents") or [])
    launch_agents = [
        observe_launch_agent(label)
        for label in shepherd.get("managed_launch_agents", [])
        if label not in disabled
    ]
    docker = {"action": "observe_only", "ok": docker_ok()}
    compose = [
        {"action": "observe_only", "status": compose_ps(item)}
        for item in shepherd.get("managed_compose", [])
    ]
    report = {
        "time": now(),
        "host": platform.node(),
        "agent": "smith",
        "dry_run": dry_run,
        "config": str(CONFIG_PATH),
        "routes": probe_smith_routes(config),
        "launch_agents": launch_agents,
        "docker": docker,
        "compose": compose,
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(json.dumps(report, sort_keys=True) + "\n")
    STATUS_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Smith's native service shepherd.")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="observe and log without repairing")
    parser.add_argument("--test-alert", action="store_true", help="send one controlled Discord delivery test; never repairs services")
    parser.add_argument("--interval", type=int, default=None, help="override poll interval seconds")
    args = parser.parse_args()

    config = read_yaml(CONFIG_PATH)
    if args.test_alert:
        result = send_discord_alert(
            config,
            "Agent Smith controlled alert test: Discord delivery path verified. No repair was attempted.",
        )
        print(json.dumps({"alert_test": result}, sort_keys=True), flush=True)
        return 0 if result.get("ok") else 1
    interval = args.interval or int((config.get("smith_shepherd") or {}).get("interval_seconds") or 60)
    while True:
        report = one_cycle(args.dry_run)
        print(json.dumps({"time": report["time"], "routes": report["routes"], "dry_run": args.dry_run}, sort_keys=True), flush=True)
        if args.once:
            return 0
        time.sleep(max(10, interval))


if __name__ == "__main__":
    raise SystemExit(main())
