#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "freyja41-preservation-audit.json"
BASELINE_TAG = "freyja-4.1-baseline-before-5.0-20260831-161448"
PROTECTED_CONTAINERS = [
    "freyja-open-webui-atlas-open-webui-1",
    "freyja-open-webui-atlas-model-proxy-1",
    "freyja3-agent-gateway-1",
    "freyja3-litellm-1",
]
ROLLBACK_FILES = [
    ".codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch",
    ".codex-checkpoints/pre-open-webui-home-agent-status-20260904T133828-0400.txt",
    "logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz",
]
PROTECTED_ENDPOINTS = {
    "freyja3_agent_gateway_root": {"url": "http://127.0.0.1:8300/", "ok_statuses": {200}, "service": "freyja3-agent-gateway"},
    "freyja3_agent_gateway_health": {"url": "http://127.0.0.1:8300/health", "ok_statuses": {200}, "healthy_json": True},
    "freyja3_inference_health": {"url": "http://127.0.0.1:8300/freyja3/inference/health", "ok_statuses": {200}, "ok_json": True},
    "freyja3_litellm_health_auth_boundary": {"url": "http://127.0.0.1:4001/health", "ok_statuses": {200, 401}, "healthy_json": False},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 4.1 fallback preservation without exposing secrets.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _command(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=REPO_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return proc.returncode, proc.stdout.strip()


def _docker_status() -> dict[str, str]:
    code, out = _command(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    if code != 0:
        return {}
    statuses: dict[str, str] = {}
    for line in out.splitlines():
        if "\t" not in line:
            continue
        name, status = line.split("\t", 1)
        statuses[name] = status
    return statuses


def _request_json(url: str) -> tuple[int, dict[str, Any] | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else None, None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError:
            payload = None
        return exc.code, payload, None
    except Exception as exc:
        return 0, None, exc.__class__.__name__


def _endpoint_checks() -> list[dict[str, Any]]:
    checks = []
    for name, config in PROTECTED_ENDPOINTS.items():
        status, payload, error = _request_json(str(config["url"]))
        ok = status in config["ok_statuses"]
        if config.get("healthy_json"):
            ok = ok and (payload or {}).get("status") == "healthy"
        if config.get("service"):
            ok = ok and (payload or {}).get("service") == config["service"]
        if config.get("ok_json"):
            ok = ok and (payload or {}).get("ok") is True
        endpoints = (payload or {}).get("endpoints")
        checks.append(
            {
                "name": name,
                "ok": ok,
                "evidence": {
                    "url": config["url"],
                    "status": status,
                    "error": error,
                    "auth_required": status == 401,
                    "healthy": (payload or {}).get("status") == "healthy",
                    "service": (payload or {}).get("service"),
                    "ok_json": (payload or {}).get("ok"),
                    "endpoint_count": len(endpoints) if isinstance(endpoints, list) else None,
                },
            }
        )
    return checks


def build_report(now: int | None = None) -> dict[str, Any]:
    tag_code, _ = _command(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{BASELINE_TAG}"])
    statuses = _docker_status()
    protected = {
        name: {"present": name in statuses, "status": statuses.get(name), "running": statuses.get(name, "").startswith("Up")}
        for name in PROTECTED_CONTAINERS
    }
    endpoint_checks = _endpoint_checks()
    rollback = {path: (REPO_ROOT / path).exists() for path in ROLLBACK_FILES}
    freyja5_status = statuses.get("freyja5-gateway-1")
    checks = [
        {"name": "baseline_tag_present", "ok": tag_code == 0, "evidence": {"tag": BASELINE_TAG}},
        {"name": "protected_containers_running", "ok": all(item["running"] for item in protected.values()), "evidence": protected},
        {"name": "protected_legacy_endpoints_respond", "ok": all(item["ok"] for item in endpoint_checks), "evidence": {"checks": endpoint_checks}},
        {"name": "freyja5_side_by_side", "ok": bool(freyja5_status and freyja5_status.startswith("Up")), "evidence": {"freyja5-gateway-1": freyja5_status}},
        {"name": "rollback_artifacts_present", "ok": all(rollback.values()), "evidence": rollback},
    ]
    endpoint_contract_known = any(
        item["name"] == "freyja3_agent_gateway_root" and item["ok"]
        for item in endpoint_checks
    ) and any(
        item["name"] == "freyja3_inference_health" and item["ok"]
        for item in endpoint_checks
    )
    checks.append(
        {
            "name": "dedicated_freyja41_endpoint_contract_known",
            "ok": endpoint_contract_known,
            "evidence": {
                "contract": "protected legacy Freyja3 gateway on port 8300",
                "root": "http://127.0.0.1:8300/",
                "inference_health": "http://127.0.0.1:8300/freyja3/inference/health",
                "note": "no separately named Freyja 4.1 endpoint is defined in current repo evidence",
            },
        }
    )
    return {
        "report_type": "freyja41-preservation-audit",
        "generated_at_unix": int(now or time.time()),
        "secrets_included": False,
        "private_content_included": False,
        "baseline_tag": BASELINE_TAG,
        "checks": checks,
        "ok": all(check["ok"] for check in checks if check["name"] != "dedicated_freyja41_endpoint_contract_known"),
        "pending": [] if endpoint_contract_known else ["dedicated_freyja41_endpoint_contract"],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
