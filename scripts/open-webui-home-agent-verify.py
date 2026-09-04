#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_HOME_MEMORY_OPERATIONS = {
    "search",
    "remember",
    "update",
    "forget",
    "record-decision",
    "recent-events",
}
REQUIRED_AGENT_MODELS = {
    "agent/freyja",
    "agent/cloyd-gibbler",
    "agent/benedict",
    "agent/benedict-paralegal",
    "agent/agent-47",
    "agent/jennacide",
}
FREYJA41_BASELINE_TAG = "freyja-4.1-baseline-before-5.0-20260831-161448"
PROTECTED_RUNNING_SERVICES = {
    "freyja-open-webui-atlas-open-webui-1",
    "freyja-open-webui-atlas-model-proxy-1",
    "freyja3-agent-gateway-1",
    "freyja3-litellm-1",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the Open WebUI home-agent deployment without printing secrets.")
    parser.add_argument("--open-webui-url", default="http://127.0.0.1:3001")
    parser.add_argument("--freyja-url", default="http://127.0.0.1:8500")
    parser.add_argument("--model-proxy-url", default=os.environ.get("OPEN_WEBUI_MODEL_PROXY_URL", ""))
    parser.add_argument("--open-webui-api-key", default=os.environ.get("OPEN_WEBUI_API_KEY", ""))
    parser.add_argument("--output", type=Path, default=Path("certification/reports/open-webui-home-agent-live.json"))
    return parser


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any] | None, str | None]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = dict(headers or {})
    if body is not None:
        req_headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            data = json.loads(raw.decode("utf-8")) if raw else None
            return response.status, data, None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError:
            data = None
        return exc.code, data, None
    except Exception as exc:
        return 0, None, exc.__class__.__name__


def check(name: str, ok: bool, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence or {}}


def run_command(args: list[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(args, check=False, text=True, capture_output=True, timeout=10)
    except Exception as exc:
        return 1, "", exc.__class__.__name__
    return completed.returncode, completed.stdout, completed.stderr


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks: list[dict[str, Any]] = []

    status, data, error = request_json("GET", f"{args.open_webui_url.rstrip('/')}/api/version")
    checks.append(check("open_webui_version", status == 200 and bool(data and data.get("version")), {"status": status, "version": (data or {}).get("version"), "error": error}))

    status, data, error = request_json("GET", f"{args.open_webui_url.rstrip('/')}/api/config")
    checks.append(check("open_webui_auth_enabled", status == 200 and bool((data or {}).get("features", {}).get("auth")), {"status": status, "error": error}))

    status, data, error = request_json("GET", f"{args.freyja_url.rstrip('/')}/health")
    checks.append(check("freyja5_health", status == 200 and (data or {}).get("status") == "healthy", {"status": status, "error": error}))

    status, data, error = request_json("GET", f"{args.freyja_url.rstrip('/')}/v1/models")
    model_ids = {item.get("id") for item in (data or {}).get("data", []) if isinstance(item, dict)}
    checks.append(check("freyja5_agent_models", status == 200 and REQUIRED_AGENT_MODELS.issubset(model_ids), {"status": status, "missing": sorted(REQUIRED_AGENT_MODELS - model_ids), "error": error}))

    if args.model_proxy_url:
        status, data, error = request_json("GET", f"{args.model_proxy_url.rstrip('/')}/v1/models")
        proxy_model_ids = {item.get("id") for item in (data or {}).get("data", []) if isinstance(item, dict)}
        checks.append(
            check(
                "model_proxy_agent_models",
                status == 200 and REQUIRED_AGENT_MODELS.issubset(proxy_model_ids),
                {"status": status, "missing": sorted(REQUIRED_AGENT_MODELS - proxy_model_ids), "error": error},
            )
        )
    else:
        checks.append(check("model_proxy_agent_models", False, {"status": "skipped", "reason": "model proxy URL not supplied"}))

    status, data, error = request_json("GET", f"{args.freyja_url.rstrip('/')}/freyja-home-memory/operations")
    operations = set((data or {}).get("operations", []))
    checks.append(check("home_memory_operations", status == 200 and REQUIRED_HOME_MEMORY_OPERATIONS == operations, {"status": status, "missing": sorted(REQUIRED_HOME_MEMORY_OPERATIONS - operations), "error": error}))

    record_id = f"live-verify-{int(time.time())}"
    joe_headers = {"x-freyja-client-type": "open-webui", "x-freyja-client-subject": "person:joe"}
    beth_headers = {"x-freyja-client-type": "open-webui", "x-freyja-client-subject": "person:beth"}
    status, _, error = request_json(
        "POST",
        f"{args.freyja_url.rstrip('/')}/freyja-home-memory/remember",
        headers=joe_headers,
        payload={
            "scope": "personal:joe",
            "owner": "joe",
            "content": "Live home-agent verifier scope check.",
            "provenance": "open-webui-home-agent-verify",
            "sensitivity": "private",
            "record_id": record_id,
        },
    )
    checks.append(check("home_memory_joe_write", status == 200, {"status": status, "error": error}))

    status, data, error = request_json(
        "GET",
        f"{args.freyja_url.rstrip('/')}/freyja-home-memory/search?scope=personal:joe&q=verifier",
        headers=joe_headers,
    )
    records = (data or {}).get("records", [])
    checks.append(check("home_memory_joe_read", status == 200 and any(record.get("id") == record_id for record in records), {"status": status, "record_count": len(records), "error": error}))

    status, _, error = request_json(
        "GET",
        f"{args.freyja_url.rstrip('/')}/freyja-home-memory/search?scope=personal:joe&q=verifier",
        headers=beth_headers,
    )
    checks.append(check("home_memory_beth_denied_joe_scope", status == 403, {"status": status, "error": error}))

    code, stdout, stderr = run_command(["git", "tag", "--list", FREYJA41_BASELINE_TAG])
    checks.append(
        check(
            "freyja41_baseline_tag_present",
            code == 0 and stdout.strip() == FREYJA41_BASELINE_TAG,
            {"tag": FREYJA41_BASELINE_TAG, "present": stdout.strip() == FREYJA41_BASELINE_TAG, "error": bool(stderr.strip())},
        )
    )

    code, stdout, stderr = run_command(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    running = {}
    if code == 0:
        for line in stdout.splitlines():
            name, _, status_text = line.partition("\t")
            if name:
                running[name] = status_text
    missing_services = sorted(PROTECTED_RUNNING_SERVICES - set(running))
    unhealthy_services = sorted(
        name
        for name in PROTECTED_RUNNING_SERVICES & set(running)
        if "Up" not in running[name]
    )
    checks.append(
        check(
            "protected_side_by_side_services_running",
            code == 0 and not missing_services and not unhealthy_services,
            {
                "missing": missing_services,
                "unhealthy": unhealthy_services,
                "observed": {name: running.get(name) for name in sorted(PROTECTED_RUNNING_SERVICES) if name in running},
                "error": bool(stderr.strip()),
            },
        )
    )

    if args.open_webui_api_key:
        status, data, error = request_json(
            "GET",
            f"{args.open_webui_url.rstrip('/')}/api/models",
            headers={"authorization": "Bearer <redacted>"},
        )
        checks.append(check("open_webui_authenticated_models", status == 200 and bool((data or {}).get("data")), {"status": status, "error": error}))
    else:
        checks.append(check("open_webui_authenticated_models", False, {"status": "skipped", "reason": "credential not supplied"}))

    report = {
        "report_type": "open-webui-home-agent-live-verification",
        "timestamp_unix": int(time.time()),
        "open_webui_url": args.open_webui_url,
        "freyja_url": args.freyja_url,
        "model_proxy_url": args.model_proxy_url or None,
        "secrets_included": False,
        "checks": checks,
        "ok": all(item["ok"] for item in checks if item["name"] not in {"open_webui_authenticated_models", "model_proxy_agent_models"}),
        "auth_required_checks_pending": [
            item["name"]
            for item in checks
            if item["name"] == "open_webui_authenticated_models" and not item["ok"]
        ],
        "optional_checks_pending": [
            item["name"]
            for item in checks
            if item["name"] == "model_proxy_agent_models" and not item["ok"]
        ],
    }

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
