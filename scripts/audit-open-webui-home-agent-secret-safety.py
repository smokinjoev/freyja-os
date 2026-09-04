#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-secret-safety.json"
TEXT_ARTIFACTS = (
    "config/open-webui-home-agents.yaml",
    "config/open-webui-home-resources.yaml",
    "config/freyja-channels.yaml",
    "config/freyja-proactive.yaml",
    "docs/operations/open-webui-home-agent.md",
    "scripts/export-open-webui-home-agents.py",
    "scripts/export-open-webui-home-resources.py",
    "scripts/apply-open-webui-home-agents-offline.py",
    "scripts/apply-open-webui-home-resources-offline.py",
    "scripts/activate-open-webui-home-agent-post-auth.py",
    "scripts/audit-freyja41-preservation.py",
    "scripts/audit-open-webui-home-agent-access.py",
    "scripts/audit-open-webui-home-agent-completion.py",
    "scripts/audit-open-webui-inference-policy.py",
    "scripts/bind-open-webui-home-agent-access.py",
    "scripts/build-open-webui-home-agent-bundle.py",
    "scripts/open-webui-home-agent-verify.py",
    "scripts/smoke-open-webui-home-agent-chats.py",
    "scripts/check-freyja-channels-readiness.py",
    "scripts/run-freyja-channels-telegram-pilot.py",
    "scripts/run-freyja-channels-signal-pilot.py",
    "scripts/check-freyja-proactive-readiness.py",
    "scripts/dry-run-freyja-proactive.py",
    "scripts/check-open-webui-tools-gateway.py",
    "scripts/export-open-webui-tools-openapi.py",
    "scripts/audit-open-webui-backup-rollback.py",
    "src/freyja/home_memory.py",
    "src/freyja/channels.py",
    "src/freyja/channel_transports.py",
    "src/freyja/proactive.py",
    "src/freyja/open_webui_tools.py",
)
JSON_REPORTS = (
    "certification/reports/open-webui-home-agent-live.json",
    "certification/reports/open-webui-backup-rollback-audit.json",
    "certification/reports/open-webui-home-agents-import.json",
    "certification/reports/open-webui-home-agents-offline-apply.json",
    "certification/reports/open-webui-home-agent-access-audit.json",
    "certification/reports/open-webui-home-agent-access-bind-dry-run.json",
    "certification/reports/open-webui-home-resources-export.json",
    "certification/reports/open-webui-home-resources-live-counts.json",
    "certification/reports/open-webui-home-resources-offline-dry-run.json",
    "certification/reports/open-webui-model-proxy-catalog.json",
    "certification/reports/freyja-channels-readiness.json",
    "certification/reports/freyja-channels-telegram-pilot.json",
    "certification/reports/freyja-channels-signal-pilot.json",
    "certification/reports/freyja-proactive-readiness.json",
    "certification/reports/freyja-proactive-dry-run.json",
    "certification/reports/freyja41-preservation-audit.json",
    "certification/reports/open-webui-home-agent-completion-audit.json",
    "certification/reports/open-webui-home-agent-platform-inventory.json",
    "certification/reports/open-webui-home-agent-post-auth-activation.json",
    "certification/reports/open-webui-inference-policy-audit.json",
    "certification/reports/open-webui-home-agent-chat-smoke.json",
    "certification/reports/open-webui-tools-gateway-readiness.json",
    "certification/reports/open-webui-tools-openapi.json",
    "certification/reports/open-webui-home-agent-deliverable.json",
)
SECRET_PATTERNS = {
    "private_key": re.compile(r"BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    "jwt_like": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
}
ALLOWED_LITERAL_MARKERS = (
    "OPEN_WEBUI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "SIGNAL_ACCOUNT_NUMBER",
    "SIGNAL_REST_API_URL",
    "FREYJA_CONNECTOR_TOKEN",
    "HOME_ASSISTANT_ACCESS_TOKEN",
    "MACAGENT_TOKEN",
    "<redacted>",
    "secret-token",
    "secret-free",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja Open WebUI home-agent artifacts for committed secret exposure.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json_secret_flags(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    flags = {
        "secrets_included": data.get("secrets_included"),
        "private_content_included": data.get("private_content_included"),
    }
    if data.get("schema", {}).get("x-freyja"):
        flags["schema_x_freyja_secrets_included"] = data["schema"]["x-freyja"].get("secrets_included")
        flags["schema_x_freyja_private_content_included"] = data["schema"]["x-freyja"].get("private_content_included")
    return flags


def _scan_text(path: Path, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    display_path = str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path)
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            findings.append({"path": display_path, "kind": label})
    lowered = text.lower()
    suspicious_pairs = ("api_key=", "token=", "password=", "authorization: bearer ")
    for marker in suspicious_pairs:
        if marker in lowered and not any(allowed.lower() in lowered for allowed in ALLOWED_LITERAL_MARKERS):
            findings.append({"path": display_path, "kind": f"literal_{marker.rstrip('= ')}"})
    return findings


def build_report() -> dict[str, Any]:
    missing: list[str] = []
    findings: list[dict[str, str]] = []
    json_flag_failures: list[dict[str, Any]] = []
    scanned: list[str] = []
    for rel in (*TEXT_ARTIFACTS, *JSON_REPORTS):
        path = REPO_ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        scanned.append(rel)
        text = _read(path)
        findings.extend(_scan_text(path, text))
        if rel.endswith(".json"):
            flags = _json_secret_flags(path)
            if flags.get("secrets_included") is not False:
                json_flag_failures.append({"path": rel, "field": "secrets_included", "value": flags.get("secrets_included")})
            if flags.get("private_content_included") not in {False, None}:
                json_flag_failures.append({"path": rel, "field": "private_content_included", "value": flags.get("private_content_included")})
            if flags.get("schema_x_freyja_secrets_included") not in {False, None}:
                json_flag_failures.append({"path": rel, "field": "schema.x-freyja.secrets_included", "value": flags.get("schema_x_freyja_secrets_included")})
            if flags.get("schema_x_freyja_private_content_included") not in {False, None}:
                json_flag_failures.append({"path": rel, "field": "schema.x-freyja.private_content_included", "value": flags.get("schema_x_freyja_private_content_included")})
    report = {
        "report_type": "open-webui-home-agent-secret-safety",
        "generated_at_unix": int(time.time()),
        "secrets_included": False,
        "private_content_included": False,
        "artifact_count": len(scanned),
        "missing_artifacts": missing,
        "secret_pattern_findings": findings,
        "json_flag_failures": json_flag_failures,
    }
    report["ok"] = not missing and not findings and not json_flag_failures
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
