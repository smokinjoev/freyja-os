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
DEFAULT_OUTPUT = REPORTS / "open-webui-home-agent-completion-audit.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja Open WebUI home-agent completion from generated evidence.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("secrets_included") is not False:
        raise ValueError(f"report is not marked secret-free: {path}")
    return data


def _exists(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _item(
    requirement_id: str,
    requirement: str,
    status: str,
    evidence: list[str],
    blocker: str | None = None,
    next_action: str | None = None,
    next_actions: list[str] | None = None,
    command: str | None = None,
    commands: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "requirement_id": requirement_id,
        "requirement": requirement,
        "status": status,
        "evidence": evidence,
        "blocker": blocker,
    }
    if next_action:
        item["next_action"] = next_action
    if next_actions:
        item["next_actions"] = next_actions
    if command:
        item["command"] = command
    if commands:
        item["commands"] = commands
    return item


def _completion_metrics(items: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, Any]:
    total = len(items)
    complete_count = counts.get("complete", 0)
    gated_count = counts.get("auth_gated", 0) + counts.get("credential_gated", 0)
    incomplete_count = total - complete_count
    return {
        "total_requirements": total,
        "complete_requirements": complete_count,
        "incomplete_requirements": incomplete_count,
        "auth_gated_requirements": counts.get("auth_gated", 0),
        "credential_gated_requirements": counts.get("credential_gated", 0),
        "partial_requirements": counts.get("partial", 0),
        "external_gated_requirements": gated_count,
        "verified_completion_percent": round((complete_count / total) * 100, 1) if total else 0.0,
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _canonical_action(value: str) -> str:
    if value == "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account.":
        return "Set OPEN_WEBUI_API_KEY outside source control."
    return value


def _required_next_actions(readiness_summary: dict[str, Any]) -> list[str]:
    explicit = readiness_summary.get("required_next_actions")
    if isinstance(explicit, list):
        return _dedupe([_canonical_action(str(action)) for action in explicit])
    actions: list[str] = []
    for gate in readiness_summary.get("gates") or []:
        if gate.get("ready") is True:
            continue
        if gate.get("next_action"):
            actions.append(str(gate["next_action"]))
        actions.extend(str(action) for action in gate.get("next_actions") or [])
    return _dedupe([_canonical_action(action) for action in actions])


def build_audit() -> dict[str, Any]:
    live = _load(REPORTS / "open-webui-home-agent-live.json")
    backup = _load(REPORTS / "open-webui-backup-rollback-audit.json")
    secret_safety = _load(REPORTS / "open-webui-home-agent-secret-safety.json")
    model_apply = _load(REPORTS / "open-webui-home-agents-offline-apply.json")
    db_verification = _load(REPORTS / "open-webui-home-agent-db-verification.json")
    access_audit = _load(REPORTS / "open-webui-home-agent-access-audit.json")
    access_bind = _load(REPORTS / "open-webui-home-agent-access-bind-dry-run.json")
    resources = _load(REPORTS / "open-webui-home-resources-export.json")
    resource_counts = _load(REPORTS / "open-webui-home-resources-live-counts.json")
    resource_import = _load(REPORTS / "open-webui-home-resources-offline-dry-run.json")
    channels = _load(REPORTS / "freyja-channels-readiness.json")
    proactive = _load(REPORTS / "freyja-proactive-readiness.json")
    proactive_dry_run = _load(REPORTS / "freyja-proactive-dry-run.json")
    freyja41 = _load(REPORTS / "freyja41-preservation-audit.json")
    proxy = _load(REPORTS / "open-webui-model-proxy-catalog.json")
    inventory = _load(REPORTS / "open-webui-home-agent-platform-inventory.json")
    inference = _load(REPORTS / "open-webui-inference-policy-audit.json")
    chat_smoke = _load(REPORTS / "open-webui-home-agent-chat-smoke.json")
    tools_gateway = _load(REPORTS / "open-webui-tools-gateway-readiness.json")
    tools_openapi = _load(REPORTS / "open-webui-tools-openapi.json")
    readiness_summary = _load(REPORTS / "open-webui-home-agent-readiness-summary.json")
    required_next_actions = _required_next_actions(readiness_summary)
    gates = {gate.get("gate_id"): gate for gate in readiness_summary.get("gates") or []}
    explicit_next_action = readiness_summary.get("exact_next_action")
    post_auth_gate = gates.get("post_auth_activation") or {}
    chat_gate = gates.get("authenticated_chat_smoke") or {}
    telegram_gate = gates.get("telegram_pilot") or {}
    signal_gate = gates.get("signal_pilot") or {}
    post_auth_next_actions = [str(action) for action in post_auth_gate.get("next_actions") or []]
    chat_next_actions = [str(action) for action in chat_gate.get("next_actions") or []]
    messaging_next_actions = _dedupe([
        *(str(action) for action in telegram_gate.get("next_actions") or []),
        *(str(action) for action in signal_gate.get("next_actions") or []),
    ])
    messaging_commands = _dedupe([
        str(command)
        for command in [telegram_gate.get("command"), signal_gate.get("command")]
        if command
    ])
    chat_ready = chat_smoke.get("status") == "complete"
    telegram_ready = telegram_gate.get("ready") is True
    signal_ready = signal_gate.get("ready") is True
    pending_messaging_channels = [
        channel
        for channel, ready in (("Telegram", telegram_ready), ("Signal", signal_ready))
        if not ready
    ]
    messaging_blocker = (
        f"{'/'.join(pending_messaging_channels)} live round trip is not yet proven with handled > 0."
        if pending_messaging_channels
        else None
    )
    db_models_ready = db_verification.get("ok") is True and all((db_verification.get("models_present") or {}).values())
    db_resources_ready = (
        db_verification.get("ok") is True
        and all((db_verification.get("knowledge_present") or {}).values())
        and all((db_verification.get("tools_present") or {}).values())
        and all((db_verification.get("memory_policies_present") or {}).values())
        and db_verification.get("managed_tool_specs_are_lists") is True
    )

    items = [
        _item(
            "preflight_inventory",
            "Inspect repository, running services, Docker stacks, endpoints, credentials locations, and Open WebUI config",
            "complete" if set((inventory.get("hosts") or {})) == {"atlas", "vulcan", "iris", "hera"} else "partial",
            [
                "logs/open-webui-diagnostics/home-agent-20260904T174214Z/",
                "docs/operations/open-webui-home-agent.md",
                "certification/reports/open-webui-home-agent-platform-inventory.json",
            ],
        ),
        _item(
            "open_webui_host_and_vulcan_path",
            "Identify Open WebUI host and Vulcan path",
            "complete" if inventory.get("open_webui_public_config", {}).get("reachable") is True and proxy.get("ok") is True and chat_ready else "partial",
            [
                "certification/reports/open-webui-home-agent-live.json",
                "certification/reports/open-webui-model-proxy-catalog.json",
                "certification/reports/open-webui-home-agent-chat-smoke.json",
            ],
        ),
        _item(
            "open_webui_backup_and_rollback",
            "Back up Open WebUI data/config/version/image/volumes/database and rollback",
            "complete" if backup.get("ok") else "partial",
            [
                "logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz",
                "docs/operations/open-webui-home-agent.md",
                "certification/reports/open-webui-backup-rollback-audit.json",
            ],
        ),
        _item(
            "git_checkpoint",
            "Create recoverable git checkpoint before repo modifications",
            "complete" if _exists(".codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch") else "missing",
            [".codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch"],
        ),
        _item(
            "secret_safety",
            "Never print or commit secrets, tokens, private messages, or private documents",
            "complete" if secret_safety.get("ok") else "partial",
            [
                "certification/reports/open-webui-home-agent-secret-safety.json",
                "logs/open-webui-diagnostics/home-agent-20260904T174214Z/env.redacted",
                "logs/open-webui-diagnostics/home-agent-20260904T174214Z/compose-config.redacted",
            ],
        ),
        _item(
            "local_inference",
            "Keep inference local by default and connect Open WebUI to Vulcan",
            "complete" if inference.get("ok") and chat_ready else "partial",
            [
                "deploy/compose/open-webui/model-proxy.py",
                "certification/reports/open-webui-home-agent-live.json",
                "certification/reports/open-webui-inference-policy-audit.json",
                "certification/reports/open-webui-home-agent-chat-smoke.json",
            ],
            None if inference.get("ok") and chat_ready else "Authenticated model/chat proof requires Open WebUI API key or session.",
            None if inference.get("ok") and chat_ready else chat_gate.get("next_action"),
            [] if inference.get("ok") and chat_ready else chat_next_actions,
            chat_gate.get("command"),
        ),
        _item(
            "model_profiles",
            "Define model profiles for fast chat, reasoning, vision/document analysis, and coding",
            "complete" if _exists("config/open-webui-home-agents.yaml") else "missing",
            ["config/open-webui-home-agents.yaml"],
        ),
        _item(
            "five_agents",
            "Create/import five Open WebUI agents",
            "complete" if db_models_ready and chat_smoke.get("status") == "complete" and access_audit.get("ok") else "partial",
            [
                "certification/reports/open-webui-home-agents-offline-apply.json",
                "certification/reports/open-webui-home-agent-db-verification.json",
                "certification/reports/open-webui-home-agent-chat-smoke.json",
                "certification/reports/open-webui-home-agent-access-audit.json",
            ],
            None if db_models_ready and chat_smoke.get("status") == "complete" else "Agent rows require live DB/API verification.",
            None if db_models_ready and chat_smoke.get("status") == "complete" else post_auth_gate.get("next_action"),
            [] if db_models_ready and chat_smoke.get("status") == "complete" else post_auth_next_actions,
            post_auth_gate.get("command"),
        ),
        _item(
            "memory_layers",
            "Implement three-layer memory with scoped freyja-home-memory service",
            "complete" if db_resources_ready and live.get("ok") else "partial",
            [
                "src/freyja/home_memory.py",
                "certification/reports/open-webui-home-resources-offline-dry-run.json",
                "certification/reports/open-webui-home-agent-db-verification.json",
                "certification/reports/open-webui-home-agent-live.json",
            ],
            None if db_resources_ready and live.get("ok") else "Native Open WebUI memory/Knowledge rows require live DB verification.",
            None if db_resources_ready and live.get("ok") else post_auth_gate.get("next_action"),
            [] if db_resources_ready and live.get("ok") else post_auth_next_actions,
            post_auth_gate.get("command"),
        ),
        _item(
            "tools",
            "Expose narrow MCP/OpenAPI tools and assign per agent",
            "complete" if resources.get("ok") and tools_gateway.get("ok") and tools_openapi.get("ok") and db_resources_ready else "partial",
            [
                "config/open-webui-home-resources.yaml",
                "src/freyja/open_webui_tools.py",
                "certification/reports/open-webui-home-resources-export.json",
                "certification/reports/open-webui-home-agent-db-verification.json",
                "certification/reports/open-webui-tools-gateway-readiness.json",
                "certification/reports/open-webui-tools-openapi.json",
            ],
            None if db_resources_ready else "Open WebUI tool rows/enablement require live DB verification.",
            None if db_resources_ready else post_auth_gate.get("next_action"),
            [] if db_resources_ready else post_auth_next_actions,
            post_auth_gate.get("command"),
        ),
        _item(
            "messaging_channels",
            "Implement deterministic Telegram/Signal channel gateway with WhatsApp disabled",
            "credential_gated" if pending_messaging_channels else ("complete" if channels.get("deterministic_gateway_only") else "partial"),
            [
                "src/freyja/channels.py",
                "certification/reports/freyja-channels-readiness.json",
                "certification/reports/freyja-channels-readiness-atlas.json",
                "certification/reports/freyja-channels-signal-pilot.json",
                "certification/reports/freyja-channels-atlas-deployment.json",
            ],
            messaging_blocker,
            "Complete the Telegram pilot." if pending_messaging_channels == ["Telegram"] else None,
            messaging_next_actions,
            messaging_commands[0] if messaging_commands else None,
            messaging_commands,
        ),
        _item(
            "proactive_behavior",
            "Add proactive behavior disabled by default",
            "complete" if proactive.get("all_disabled_by_default") and not proactive.get("ready_schedule_ids") and proactive_dry_run.get("all_sends_suppressed") else "partial",
            [
                "src/freyja/proactive.py",
                "certification/reports/freyja-proactive-readiness.json",
                "certification/reports/freyja-proactive-dry-run.json",
            ],
        ),
        _item(
            "verification",
            "Create repeatable verification",
            "complete" if readiness_summary.get("all_ready") is True else "partial",
            [
                "tests/",
                "certification/reports/open-webui-home-agent-live.json",
                "certification/reports/open-webui-home-agent-chat-smoke.json",
                "certification/reports/open-webui-home-agent-readiness-summary.json",
                "certification/reports/open-webui-home-agent-evidence-refresh.json",
            ],
            (
                f"{'/'.join(pending_messaging_channels)} round trip remains pending."
                if pending_messaging_channels
                else "One or more verification gates remain pending."
            )
            if readiness_summary.get("all_ready") is not True
            else None,
            "Clear all external readiness gates, then rerun the completion audit."
            if readiness_summary.get("all_ready") is not True
            else None,
            _dedupe([
                action
                for action in [
                    *post_auth_next_actions,
                    *chat_next_actions,
                    *messaging_next_actions,
                ]
            ])
            if readiness_summary.get("all_ready") is not True
            else None,
            "scripts/summarize-open-webui-home-agent-readiness.py && scripts/audit-open-webui-home-agent-completion.py"
            if readiness_summary.get("all_ready") is not True
            else None,
            [
                "scripts/summarize-open-webui-home-agent-readiness.py",
                "scripts/audit-open-webui-home-agent-completion.py",
            ]
            if readiness_summary.get("all_ready") is not True
            else None,
        ),
        _item(
            "freyja41_preservation",
            "Preserve Freyja 4.1 fallback",
            "partial" if freyja41.get("pending") else "complete",
            ["certification/reports/freyja41-preservation-audit.json"],
            "Dedicated Freyja 4.1 endpoint contract is not defined in current repo evidence." if freyja41.get("pending") else None,
        ),
        _item(
            "final_deliverable",
            "Deliver endpoint map, config inventory, test results, blockers, rollback, and exact next action",
            "complete",
            ["certification/reports/open-webui-home-agent-deliverable.json", "docs/operations/open-webui-home-agent.md"],
        ),
    ]
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    completion_metrics = _completion_metrics(items, counts)
    exact_next_action = explicit_next_action or (required_next_actions[0] if required_next_actions else None)
    return {
        "report_type": "open-webui-home-agent-completion-audit",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "items": items,
        "status_counts": counts,
        "completion_metrics": completion_metrics,
        "complete": counts.get("missing", 0) == 0 and counts.get("partial", 0) == 0 and counts.get("auth_gated", 0) == 0 and counts.get("credential_gated", 0) == 0,
        "exact_next_action": exact_next_action,
        "required_next_actions": required_next_actions,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
