#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGENTS = REPO_ROOT / "config" / "open-webui-home-agents.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-chat-smoke.json"
DEFAULT_OPEN_WEBUI_URL = "http://100.119.235.114:3001"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_TOKENS = 256
MODEL_IDS = {
    "freyja": "agent/freyja",
    "cloyd": "agent/cloyd-gibbler",
    "smith": "agent/freyja-coder",
    "benedict": "agent/benedict",
    "agent-44": "agent/agent-47",
    "jenna": "agent/jennacide",
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authenticated Open WebUI chat smoke test for Freyja home agents."
    )
    parser.add_argument("--open-webui-url", default=os.environ.get("OPEN_WEBUI_URL", DEFAULT_OPEN_WEBUI_URL))
    parser.add_argument("--open-webui-api-key", default=os.environ.get("OPEN_WEBUI_API_KEY", ""))
    parser.add_argument("--agents", type=Path, default=DEFAULT_AGENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=_env_float("OPEN_WEBUI_CHAT_SMOKE_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("OPEN_WEBUI_CHAT_SMOKE_MAX_TOKENS", DEFAULT_MAX_TOKENS)))
    parser.add_argument("--agent", action="append", choices=sorted(MODEL_IDS), help="Limit to one or more agent ids.")
    parser.add_argument("--dry-run", action="store_true", help="Render the intended checks without calling Open WebUI.")
    return parser


def load_manifest(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("secrets_included") is not False:
        raise ValueError("agent manifest must be explicit and secret-free")
    return data


def model_profile_map(manifest: dict[str, Any]) -> dict[str, str]:
    profiles = manifest.get("model_profiles") or {}
    result: dict[str, str] = {}
    for agent in manifest.get("agents") or []:
        profile_id = agent.get("model_profile")
        profile = profiles.get(profile_id) or {}
        result[agent["id"]] = profile.get("model", "")
    return result


def request_chat_completion(
    base_url: str,
    api_key: str,
    model_id: str,
    display_name: str,
    *,
    timeout: float,
    max_tokens: int,
) -> tuple[int, dict[str, Any] | None, str | None, float]:
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Smoke test for {display_name}. Reply with only the words: "
                    "Freyja home agent online"
                ),
            }
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            elapsed = time.monotonic() - started
            data = json.loads(raw.decode("utf-8")) if raw else None
            return response.status, data, None, elapsed
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, None, None, time.monotonic() - started
    except Exception as exc:
        return 0, None, exc.__class__.__name__, time.monotonic() - started


def agent_checks(
    manifest: dict[str, Any],
    *,
    selected_agents: set[str] | None = None,
) -> list[dict[str, Any]]:
    expected_models = model_profile_map(manifest)
    checks = []
    for agent in manifest.get("agents") or []:
        agent_id = agent["id"]
        if selected_agents and agent_id not in selected_agents:
            continue
        checks.append(
            {
                "agent_id": agent_id,
                "display_name": agent["display_name"],
                "open_webui_model_id": MODEL_IDS[agent_id],
                "expected_vulcan_model": expected_models.get(agent_id),
                "model_profile": agent["model_profile"],
            }
        )
    return checks


def pending_next_actions(reason: str) -> tuple[list[str], list[str]]:
    if reason == "OPEN_WEBUI_API_KEY not supplied":
        return (
            ["OPEN_WEBUI_API_KEY"],
            [
                "Use the existing Atlas Open WebUI admin account and generate an admin or service-account API key.",
                "Set OPEN_WEBUI_API_KEY outside source control.",
                "Rerun scripts/smoke-open-webui-home-agent-chats.py and require status=complete for all home agents.",
            ],
        )
    if reason == "dry run":
        return (
            [],
            [
            "Set OPEN_WEBUI_API_KEY when ready to perform the authenticated home-agent chat smoke.",
                "Rerun without --dry-run and require status=complete for all selected agents.",
            ],
        )
    return ([], ["Resolve the reported pending reason, then rerun the authenticated chat smoke."])


def build_pending_report(args: argparse.Namespace, manifest: dict[str, Any], reason: str) -> dict[str, Any]:
    generated_at = int(time.time())
    missing_configuration, next_actions = pending_next_actions(reason)
    return {
        "report_type": "open-webui-home-agent-chat-smoke",
        "generated_at_unix": generated_at,
        "timestamp_unix": generated_at,
        "git_head": _git_head(),
        "open_webui_url": args.open_webui_url,
        "secrets_included": False,
        "private_content_included": False,
        "complete": False,
        "status": "pending",
        "reason": reason,
        "missing_configuration": missing_configuration,
        "next_actions": next_actions,
        "checks": agent_checks(manifest, selected_agents=set(args.agent or []) or None),
    }


def run_smoke(args: argparse.Namespace, manifest: dict[str, Any]) -> dict[str, Any]:
    checks = agent_checks(manifest, selected_agents=set(args.agent or []) or None)
    for check in checks:
        status, data, error, elapsed = request_chat_completion(
            args.open_webui_url,
            args.open_webui_api_key,
            check["open_webui_model_id"],
            check["display_name"],
            timeout=args.timeout,
            max_tokens=args.max_tokens,
        )
        choices = (data or {}).get("choices") or []
        content = ""
        if choices and isinstance(choices[0], dict):
            content = (choices[0].get("message") or {}).get("content") or ""
        check.update(
            {
                "http_status": status,
                "elapsed_seconds": round(elapsed, 3),
                "response_present": bool(content.strip()),
                "error_class": error,
                "ok": status == 200 and bool(content.strip()),
            }
        )
    generated_at = int(time.time())
    return {
        "report_type": "open-webui-home-agent-chat-smoke",
        "generated_at_unix": generated_at,
        "timestamp_unix": generated_at,
        "git_head": _git_head(),
        "open_webui_url": args.open_webui_url,
        "secrets_included": False,
        "private_content_included": False,
        "complete": all(item["ok"] for item in checks),
        "status": "complete" if all(item["ok"] for item in checks) else "failed",
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest(args.agents)
    if args.dry_run:
        report = build_pending_report(args, manifest, "dry run")
    elif not args.open_webui_api_key:
        report = build_pending_report(args, manifest, "OPEN_WEBUI_API_KEY not supplied")
    else:
        report = run_smoke(args, manifest)

    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] in {"complete", "pending"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
