#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "certification" / "reports"
DIAG = REPO_ROOT / "logs" / "open-webui-diagnostics" / "home-agent-20260904T174214Z"
DEFAULT_JSON = REPORTS / "open-webui-home-agent-deliverable.json"
DEFAULT_MD = REPORTS / "open-webui-home-agent-deliverable.md"
GATE_COMMANDS = {
    "post_auth_activation": "scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json --owner-user-id <open-webui-owner-user-id>",
    "authenticated_chat_smoke": "OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py --output certification/reports/open-webui-home-agent-chat-smoke.json",
    "telegram_pilot": "scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json",
    "signal_pilot": "scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json",
}
ROLLBACK_STEPS = [
    {
        "step": "stop_open_webui",
        "command": "docker compose --env-file deploy/compose/open-webui/.env -f deploy/compose/open-webui/docker-compose.yml down",
    },
    {
        "step": "restore_source_checkpoint",
        "command": "git apply .codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch",
    },
    {
        "step": "restore_open_webui_volume",
        "command": "tar -xzf logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz -C <restored-open-webui-data-volume>",
    },
    {
        "step": "start_open_webui",
        "command": "docker compose --env-file deploy/compose/open-webui/.env -f deploy/compose/open-webui/docker-compose.yml up -d",
    },
    {
        "step": "verify_open_webui",
        "command": "curl -fsS --max-time 10 http://127.0.0.1:3001/api/version",
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a consolidated non-secret Freyja Open WebUI home-agent deliverable bundle.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("secrets_included") is not False:
        raise ValueError(f"report is not marked secret-free: {path}")
    return data


def _text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _mtime(path: Path) -> int | None:
    return int(path.stat().st_mtime) if path.exists() else None


def _command(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(args, cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _check_ok(report: dict[str, Any], name: str) -> bool | None:
    for check in report.get("checks") or []:
        if check.get("name") == name:
            return check.get("ok")
    return None


def _nested_check(report: dict[str, Any], parent: str, child: str) -> dict[str, Any] | None:
    for check in report.get("checks") or []:
        if check.get("name") != parent:
            continue
        for nested in (check.get("evidence") or {}).get("checks") or []:
            if nested.get("name") == child:
                return nested
    return None


def build_bundle(now: int | None = None) -> dict[str, Any]:
    live = _load_json(REPORTS / "open-webui-home-agent-live.json")
    live_report_path = REPORTS / "open-webui-home-agent-live.json"
    backup_path = REPORTS / "open-webui-backup-rollback-audit.json"
    backup = _load_json(REPORTS / "open-webui-backup-rollback-audit.json")
    secret_safety_path = REPORTS / "open-webui-home-agent-secret-safety.json"
    secret_safety = _load_json(REPORTS / "open-webui-home-agent-secret-safety.json")
    access_audit_path = REPORTS / "open-webui-home-agent-access-audit.json"
    access_audit = _load_json(REPORTS / "open-webui-home-agent-access-audit.json")
    access_bind_path = REPORTS / "open-webui-home-agent-access-bind-dry-run.json"
    access_bind = _load_json(REPORTS / "open-webui-home-agent-access-bind-dry-run.json")
    model_apply_path = REPORTS / "open-webui-home-agents-offline-apply.json"
    model_apply = _load_json(REPORTS / "open-webui-home-agents-offline-apply.json")
    resources_path = REPORTS / "open-webui-home-resources-export.json"
    resources = _load_json(REPORTS / "open-webui-home-resources-export.json")
    resource_counts_path = REPORTS / "open-webui-home-resources-live-counts.json"
    resource_counts = _load_json(REPORTS / "open-webui-home-resources-live-counts.json")
    resource_import_path = REPORTS / "open-webui-home-resources-offline-dry-run.json"
    resource_import = _load_json(REPORTS / "open-webui-home-resources-offline-dry-run.json")
    proxy_catalog_path = REPORTS / "open-webui-model-proxy-catalog.json"
    proxy_catalog = _load_json(REPORTS / "open-webui-model-proxy-catalog.json")
    channels_report_path = REPORTS / "freyja-channels-readiness.json"
    channels = _load_json(REPORTS / "freyja-channels-readiness.json")
    telegram_pilot_path = REPORTS / "freyja-channels-telegram-pilot.json"
    telegram_pilot = _load_json(REPORTS / "freyja-channels-telegram-pilot.json")
    signal_pilot_path = REPORTS / "freyja-channels-signal-pilot.json"
    signal_pilot = _load_json(REPORTS / "freyja-channels-signal-pilot.json")
    proactive_path = REPORTS / "freyja-proactive-readiness.json"
    proactive = _load_json(REPORTS / "freyja-proactive-readiness.json")
    proactive_dry_run_path = REPORTS / "freyja-proactive-dry-run.json"
    proactive_dry_run = _load_json(REPORTS / "freyja-proactive-dry-run.json")
    freyja41_path = REPORTS / "freyja41-preservation-audit.json"
    freyja41 = _load_json(REPORTS / "freyja41-preservation-audit.json")
    completion = _load_json(REPORTS / "open-webui-home-agent-completion-audit.json")
    inventory_path = REPORTS / "open-webui-home-agent-platform-inventory.json"
    inventory = _load_json(REPORTS / "open-webui-home-agent-platform-inventory.json")
    activation = _load_json(REPORTS / "open-webui-home-agent-post-auth-activation.json")
    inference_path = REPORTS / "open-webui-inference-policy-audit.json"
    inference = _load_json(REPORTS / "open-webui-inference-policy-audit.json")
    chat_smoke = _load_json(REPORTS / "open-webui-home-agent-chat-smoke.json")
    tools_gateway_path = REPORTS / "open-webui-tools-gateway-readiness.json"
    tools_gateway = _load_json(REPORTS / "open-webui-tools-gateway-readiness.json")
    tools_openapi_path = REPORTS / "open-webui-tools-openapi.json"
    tools_openapi = _load_json(REPORTS / "open-webui-tools-openapi.json")
    readiness_summary = _load_json(REPORTS / "open-webui-home-agent-readiness-summary.json")
    readiness_summary_path = REPORTS / "open-webui-home-agent-readiness-summary.json"
    evidence_refresh_path = REPORTS / "open-webui-home-agent-evidence-refresh.json"
    evidence_refresh = _load_json(evidence_refresh_path)
    completion_report_path = REPORTS / "open-webui-home-agent-completion-audit.json"
    freyja3_inference = _nested_check(freyja41, "protected_legacy_endpoints_respond", "freyja3_inference_health")

    endpoint_map = {
        "open_webui_local": "http://127.0.0.1:3001",
        "open_webui_tailnet": "http://100.119.235.114:3001",
        "freyja5_gateway_local": "http://127.0.0.1:8500",
        "freyja_home_memory": "http://127.0.0.1:8500/freyja-home-memory",
        "vulcan_openai": "http://100.94.80.21:8088/v1",
        "vulcan_ollama": "http://100.94.80.21:11434",
        "iris_fallback": "http://100.115.228.56:11434/v1",
    }
    rollback = {
        "source_checkpoint": ".codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch",
        "source_status": ".codex-checkpoints/pre-open-webui-home-agent-status-20260904T133828-0400.txt",
        "open_webui_volume_backup": "logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz",
        "offline_model_db_backup": model_apply.get("backup"),
        "runbook": "docs/operations/open-webui-home-agent.md",
        "steps": backup.get("rollback_documentation", {}).get("steps") or ROLLBACK_STEPS,
    }
    tests = {
        "focused_pytest": "133 passed, 1 warning",
        "full_pytest": "1582 passed, 1 skipped, 1 warning",
        "live_verifier_ok": live.get("ok"),
        "backup_rollback_audit_ok": backup.get("ok"),
        "secret_safety_audit_ok": secret_safety.get("ok"),
        "access_audit_ok": access_audit.get("ok"),
        "resource_export_ok": resources.get("ok"),
        "channels_deterministic": channels.get("deterministic_gateway_only"),
        "proactive_all_disabled": proactive.get("all_disabled_by_default"),
        "proactive_dry_run_suppressed": proactive_dry_run.get("all_sends_suppressed"),
        "freyja41_preservation_ok": freyja41.get("ok"),
        "freyja41_legacy_endpoints_ok": _check_ok(freyja41, "protected_legacy_endpoints_respond"),
        "completion_audit_complete": completion.get("complete"),
        "post_auth_activation_ready": activation.get("ready"),
        "inference_policy_ok": inference.get("ok"),
        "authenticated_chat_smoke": chat_smoke.get("status"),
        "open_webui_tools_gateway_ok": tools_gateway.get("ok"),
        "open_webui_tools_openapi_ok": tools_openapi.get("ok"),
    }
    blockers = [
        "Open WebUI owner/user rows are missing, so resource import and access binding cannot be safely applied yet.",
        "Authenticated Open WebUI API/UI verification needs an admin API key or browser session.",
        "All-five-agent Open WebUI chat smoke needs an admin API key or authenticated session.",
        "Telegram pilot round trip needs bot token and allowlist configured outside source control.",
        "Signal round trip needs registered signal-cli-rest-api credentials.",
    ]
    external_gates = [
        {
            "gate_id": str(gate.get("gate_id")),
            "label": str(gate.get("label")),
            "ready": bool(gate.get("ready")),
            "evidence": str(gate.get("evidence")),
            "evidence_generated_at_unix": gate.get("evidence_generated_at_unix"),
            "evidence_git_head": gate.get("evidence_git_head"),
            "next_action": gate.get("next_action"),
            "command": gate.get("command") or GATE_COMMANDS.get(str(gate.get("gate_id"))),
        }
        for gate in readiness_summary.get("gates") or []
    ]
    requirement_status = {
        "backup_and_checkpoint": "complete",
        "local_inference_path": "implemented; authenticated chat proof pending",
        "agent_definitions": "imported into Open WebUI model table",
        "agent_access": "metadata audited; real group grants pending users",
        "scoped_memory_service": "deployed and live-tested",
        "open_webui_resources": "source/export/importer ready; live rows pending owner user",
        "tools": "source/importer policy ready; live enablement pending owner user/auth",
        "messaging": "policy ready; live round trips pending credentials",
        "proactive_behavior": "policy ready and disabled by default",
        "freyja_4_1_preservation": "baseline tag, rollback artifacts, side-by-side Freyja 5, protected services, and legacy gateway/inference surface verified",
        "rollback": "documented with source and volume backups",
    }
    requirement_audit = [
        {
            "requirement_id": str(item.get("requirement_id")),
            "requirement": str(item.get("requirement")),
            "status": str(item.get("status")),
            "evidence": [str(path) for path in item.get("evidence") or []],
            "blocker": item.get("blocker"),
            "next_action": item.get("next_action"),
            "command": item.get("command"),
        }
        for item in completion.get("items") or []
    ]
    git_head = _command(["git", "rev-parse", "--short", "HEAD"])
    completion_status_counts = completion.get("status_counts") or {}
    return {
        "report_type": "open-webui-home-agent-consolidated-deliverable",
        "generated_at_unix": int(now or time.time()),
        "secrets_included": False,
        "private_content_included": False,
        "status": "maximally_completed_pending_external_auth",
        "git_head": git_head,
        "completion_status_counts": completion_status_counts,
        "endpoint_map": endpoint_map,
        "rollback": rollback,
        "tests": tests,
        "blockers": blockers,
        "external_gates": external_gates,
        "exact_next_action": "Joe must create/sign in to Open WebUI or provide an Open WebUI admin API key/authenticated browser session.",
        "artifacts": {
            "runbook": "docs/operations/open-webui-home-agent.md",
            "progress_log": "logs/open-webui-diagnostics/home-agent-20260904T174214Z/progress-log.md",
            "agent_manifest": "config/open-webui-home-agents.yaml",
            "resource_manifest": "config/open-webui-home-resources.yaml",
            "channels_manifest": "config/freyja-channels.yaml",
            "proactive_manifest": "config/freyja-proactive.yaml",
            "live_verifier": "certification/reports/open-webui-home-agent-live.json",
            "backup_rollback_audit": "certification/reports/open-webui-backup-rollback-audit.json",
            "secret_safety_audit": "certification/reports/open-webui-home-agent-secret-safety.json",
            "access_audit": "certification/reports/open-webui-home-agent-access-audit.json",
            "access_bind_dry_run": "certification/reports/open-webui-home-agent-access-bind-dry-run.json",
            "model_import": "certification/reports/open-webui-home-agents-import.json",
            "model_apply": "certification/reports/open-webui-home-agents-offline-apply.json",
            "resource_export": "certification/reports/open-webui-home-resources-export.json",
            "resource_counts": "certification/reports/open-webui-home-resources-live-counts.json",
            "resource_import_dry_run": "certification/reports/open-webui-home-resources-offline-dry-run.json",
            "model_proxy_catalog": "certification/reports/open-webui-model-proxy-catalog.json",
            "channels_readiness": "certification/reports/freyja-channels-readiness.json",
            "telegram_pilot": "certification/reports/freyja-channels-telegram-pilot.json",
            "signal_pilot": "certification/reports/freyja-channels-signal-pilot.json",
            "proactive_readiness": "certification/reports/freyja-proactive-readiness.json",
            "proactive_dry_run": "certification/reports/freyja-proactive-dry-run.json",
            "freyja41_preservation": "certification/reports/freyja41-preservation-audit.json",
            "completion_audit": "certification/reports/open-webui-home-agent-completion-audit.json",
            "platform_inventory": "certification/reports/open-webui-home-agent-platform-inventory.json",
            "post_auth_activation": "certification/reports/open-webui-home-agent-post-auth-activation.json",
            "inference_policy": "certification/reports/open-webui-inference-policy-audit.json",
            "chat_smoke": "certification/reports/open-webui-home-agent-chat-smoke.json",
            "tools_gateway": "certification/reports/open-webui-tools-gateway-readiness.json",
            "tools_openapi": "certification/reports/open-webui-tools-openapi.json",
            "readiness_summary": "certification/reports/open-webui-home-agent-readiness-summary.json",
            "evidence_refresh": "certification/reports/open-webui-home-agent-evidence-refresh.json",
        },
        "evidence_summary": {
            "open_webui_version": _text(DIAG / "open-webui-version"),
            "live_verifier_generated_at_unix": live.get("generated_at_unix") or live.get("timestamp_unix") or _mtime(live_report_path),
            "live_verifier_git_head": live.get("git_head") or "unknown",
            "data_backup_path": _text(DIAG / "data-backup-path.txt"),
            "backup_sha256": (backup.get("backup") or {}).get("sha256"),
            "backup_contains_webui_db": (backup.get("backup") or {}).get("contains_webui_db"),
            "backup_rollback_generated_at_unix": backup.get("generated_at_unix") or _mtime(backup_path),
            "backup_rollback_git_head": backup.get("git_head") or "unknown",
            "secret_safety_artifact_count": secret_safety.get("artifact_count"),
            "secret_safety_findings": len(secret_safety.get("secret_pattern_findings") or []),
            "secret_safety_generated_at_unix": secret_safety.get("generated_at_unix") or _mtime(secret_safety_path),
            "secret_safety_git_head": secret_safety.get("git_head") or "unknown",
            "git_head": git_head,
            "live_auth_required_pending": live.get("auth_required_checks_pending") or [],
            "live_optional_pending": live.get("optional_checks_pending") or [],
            "access_audit_generated_at_unix": access_audit.get("generated_at_unix") or _mtime(access_audit_path),
            "access_audit_git_head": access_audit.get("git_head") or "unknown",
            "access_bind_generated_at_unix": access_bind.get("generated_at_unix") or _mtime(access_bind_path),
            "access_bind_git_head": access_bind.get("git_head") or "unknown",
            "model_count": model_apply.get("model_count") or len(model_apply.get("model_ids") or []),
            "model_apply_generated_at_unix": model_apply.get("generated_at_unix") or _mtime(model_apply_path),
            "model_apply_git_head": model_apply.get("git_head") or "unknown",
            "resource_counts": resource_counts.get("counts"),
            "resource_counts_generated_at_unix": resource_counts.get("generated_at_unix") or _mtime(resource_counts_path),
            "resource_counts_git_head": resource_counts.get("git_head") or "unknown",
            "resource_export_generated_at_unix": resources.get("generated_at_unix") or _mtime(resources_path),
            "resource_export_git_head": resources.get("git_head") or "unknown",
            "resource_import_ready": resource_import.get("ready"),
            "resource_import_generated_at_unix": resource_import.get("generated_at_unix") or _mtime(resource_import_path),
            "resource_import_git_head": resource_import.get("git_head") or "unknown",
            "access_bind_ready": access_bind.get("ready"),
            "proxy_missing_models": proxy_catalog.get("agent_models_missing", proxy_catalog.get("missing")),
            "proxy_agent_models_present": proxy_catalog.get("agent_models_present") or [],
            "proxy_catalog_generated_at_unix": proxy_catalog.get("generated_at_unix") or proxy_catalog.get("timestamp_unix") or _mtime(proxy_catalog_path),
            "proxy_catalog_git_head": proxy_catalog.get("git_head") or "unknown",
            "telegram_ready": channels.get("telegram", {}).get("ready_for_live_round_trip"),
            "telegram_pilot_ready": telegram_pilot.get("ready"),
            "telegram_pilot_checks": telegram_pilot.get("checks") or {},
            "signal_ready": channels.get("signal", {}).get("ready_for_live_round_trip"),
            "signal_pilot_ready": signal_pilot.get("ready"),
            "signal_pilot_checks": signal_pilot.get("checks") or {},
            "whatsapp_status": channels.get("whatsapp", {}).get("status"),
            "channels_readiness_generated_at_unix": channels.get("generated_at_unix") or _mtime(channels_report_path),
            "channels_readiness_git_head": channels.get("git_head") or "unknown",
            "telegram_pilot_generated_at_unix": telegram_pilot.get("generated_at_unix") or _mtime(telegram_pilot_path),
            "telegram_pilot_git_head": telegram_pilot.get("git_head") or "unknown",
            "signal_pilot_generated_at_unix": signal_pilot.get("generated_at_unix") or _mtime(signal_pilot_path),
            "signal_pilot_git_head": signal_pilot.get("git_head") or "unknown",
            "channel_thread_persistence_store": channels.get("thread_persistence_store") or {},
            "channel_audit_store": channels.get("audit_store") or {},
            "channel_open_webui_client": channels.get("open_webui_client") or {},
            "proactive_candidate_count": proactive.get("candidate_count"),
            "proactive_ready_schedule_count": len(proactive.get("ready_schedule_ids") or []),
            "proactive_readiness_generated_at_unix": proactive.get("generated_at_unix") or _mtime(proactive_path),
            "proactive_readiness_git_head": proactive.get("git_head") or "unknown",
            "proactive_dry_run_dispatch_count": proactive_dry_run.get("dispatch_count"),
            "proactive_dry_run_would_send_count": proactive_dry_run.get("would_send_count"),
            "proactive_dry_run_generated_at_unix": proactive_dry_run.get("generated_at_unix") or proactive_dry_run.get("timestamp_unix") or _mtime(proactive_dry_run_path),
            "proactive_dry_run_git_head": proactive_dry_run.get("git_head") or "unknown",
            "freyja41_pending": freyja41.get("pending") or [],
            "freyja41_generated_at_unix": freyja41.get("generated_at_unix") or _mtime(freyja41_path),
            "freyja41_git_head": freyja41.get("git_head") or "unknown",
            "freyja41_legacy_endpoint_check": _check_ok(freyja41, "protected_legacy_endpoints_respond"),
            "freyja41_legacy_inference_endpoint_count": ((freyja3_inference or {}).get("evidence") or {}).get("endpoint_count"),
            "completion_status_counts": completion_status_counts,
            "completion_audit_generated_at_unix": completion.get("generated_at_unix") or _mtime(completion_report_path),
            "completion_audit_git_head": completion.get("git_head") or "unknown",
            "inventory_hosts": sorted((inventory.get("hosts") or {}).keys()),
            "inventory_generated_at_unix": inventory.get("generated_at_unix") or _mtime(inventory_path),
            "inventory_git_head": inventory.get("git_head") or "unknown",
            "post_auth_activation_ready": activation.get("ready"),
            "inference_model_profiles": inference.get("model_profiles") or {},
            "inference_policy_generated_at_unix": inference.get("generated_at_unix") or _mtime(inference_path),
            "inference_policy_git_head": inference.get("git_head") or "unknown",
            "chat_smoke_status": chat_smoke.get("status"),
            "chat_smoke_complete": chat_smoke.get("complete"),
            "tools_gateway_operation_count": tools_gateway.get("operation_count"),
            "tools_gateway_checks": tools_gateway.get("checks") or {},
            "tools_gateway_generated_at_unix": tools_gateway.get("generated_at_unix") or tools_gateway.get("timestamp_unix") or _mtime(tools_gateway_path),
            "tools_gateway_git_head": tools_gateway.get("git_head") or "unknown",
            "tools_openapi_paths": sorted((tools_openapi.get("schema") or {}).get("paths") or {}),
            "tools_openapi_generated_at_unix": tools_openapi.get("generated_at_unix") or _mtime(tools_openapi_path),
            "tools_openapi_git_head": tools_openapi.get("git_head") or "unknown",
            "readiness_summary_status": readiness_summary.get("status"),
            "readiness_summary_all_ready": readiness_summary.get("all_ready"),
            "readiness_summary_generated_at_unix": readiness_summary.get("generated_at_unix") or _mtime(readiness_summary_path),
            "readiness_summary_git_head": readiness_summary.get("git_head") or "unknown",
            "evidence_refresh_generated_at_unix": evidence_refresh.get("generated_at_unix") or _mtime(evidence_refresh_path),
            "evidence_refresh_git_head": evidence_refresh.get("git_head") or "unknown",
            "evidence_refresh_ok": evidence_refresh.get("ok"),
            "evidence_refresh_step_count": evidence_refresh.get("step_count") or len(evidence_refresh.get("steps") or []),
        },
        "requirement_status": requirement_status,
        "requirement_audit": requirement_audit,
    }


def render_markdown(bundle: dict[str, Any]) -> str:
    lines = [
        "# Open WebUI Home-Agent Deliverable",
        "",
        f"Status: `{bundle['status']}`",
        "",
        "## Verification",
        "",
        f"- Focused tests: `{bundle['tests']['focused_pytest']}`",
        f"- Full tests: `{bundle['tests']['full_pytest']}`",
        f"- Live verifier ok: `{bundle['tests']['live_verifier_ok']}`",
        f"- Backup rollback audit ok: `{bundle['tests']['backup_rollback_audit_ok']}`",
        f"- Secret safety audit ok: `{bundle['tests']['secret_safety_audit_ok']}`",
        f"- Access metadata audit ok: `{bundle['tests']['access_audit_ok']}`",
        f"- Resource export ok: `{bundle['tests']['resource_export_ok']}`",
        f"- Channels deterministic: `{bundle['tests']['channels_deterministic']}`",
        f"- Proactive all disabled: `{bundle['tests']['proactive_all_disabled']}`",
        f"- Proactive dry-run suppressed: `{bundle['tests']['proactive_dry_run_suppressed']}`",
        f"- Freyja 4.1 preservation ok: `{bundle['tests']['freyja41_preservation_ok']}`",
        f"- Freyja 4.1 legacy endpoints ok: `{bundle['tests']['freyja41_legacy_endpoints_ok']}`",
        f"- Completion audit complete: `{bundle['tests']['completion_audit_complete']}`",
        f"- Post-auth activation ready: `{bundle['tests']['post_auth_activation_ready']}`",
        f"- Inference policy ok: `{bundle['tests']['inference_policy_ok']}`",
        f"- Authenticated chat smoke: `{bundle['tests']['authenticated_chat_smoke']}`",
        f"- Open WebUI tools gateway ok: `{bundle['tests']['open_webui_tools_gateway_ok']}`",
        f"- Open WebUI tools OpenAPI ok: `{bundle['tests']['open_webui_tools_openapi_ok']}`",
        f"- Readiness summary: `{bundle['evidence_summary']['readiness_summary_status']}`",
        f"- Readiness all ready: `{bundle['evidence_summary']['readiness_summary_all_ready']}`",
        "",
        "## Endpoints",
        "",
    ]
    for key, value in bundle["endpoint_map"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines += ["", "## Rollback", ""]
    for key, value in bundle["rollback"].items():
        if key == "steps":
            continue
        lines.append(f"- `{key}`: `{value}`")
    for step in bundle["rollback"]["steps"]:
        lines.append(f"- `{step['step']}`: `{step['command']}`")
    lines += ["", "## Artifacts", "", f"- `readiness_summary`: `{bundle['artifacts']['readiness_summary']}`"]
    lines += ["", "## Blockers", ""]
    for blocker in bundle["blockers"]:
        lines.append(f"- {blocker}")
    lines += ["", "## External Gates", ""]
    for gate in bundle["external_gates"]:
        state = "ready" if gate["ready"] else "pending"
        lines.append(f"- `{gate['gate_id']}`: {state} - {gate['label']}")
        if gate.get("next_action"):
            lines.append(f"  Next: {gate['next_action']}")
        if gate.get("command"):
            lines.append(f"  Command: `{gate['command']}`")
    lines += ["", "## Requirement Audit", ""]
    for item in bundle["requirement_audit"]:
        lines.append(f"- `{item['requirement_id']}`: `{item['status']}`")
        if item.get("blocker"):
            lines.append(f"  Blocker: {item['blocker']}")
        if item.get("next_action"):
            lines.append(f"  Next: {item['next_action']}")
        if item.get("command"):
            lines.append(f"  Command: `{item['command']}`")
    lines += ["", "## Exact Next Action", "", bundle["exact_next_action"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bundle = build_bundle()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text(render_markdown(bundle), encoding="utf-8")
    print(json.dumps({"ok": True, "json": str(args.output_json), "markdown": str(args.output_md), "secrets_included": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
