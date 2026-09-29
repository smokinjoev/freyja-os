#!/usr/bin/env python3
"""Generate Freyja 6.0 acceptance status from scaffold and live evidence."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-acceptance-status.json")
SECRET_MARKERS = ("api_key", "apikey", "authorization", "bearer ", "password", "secret", "token")
REQUIRED_EVIDENCE_METADATA = ["captured_at", "source"]
TRACE_EVIDENCE_FIELDS = {"litellm_request_id", "discord_reply_after_reboot"}
CODING_WORKFLOW_RESULT_SUMMARY = "opencode status queried through Freyja Core"
EXPECTED_ACCEPTANCE_SOURCES = {
    "discord_reply": "freyja6-discord-smoke",
    "restart_identity_session": "freyja6-restart-evidence",
    "remember_fact": "freyja6-restart-evidence",
    "litellm_to_vulcan": "freyja6-litellm-smoke",
    "model_switch": "freyja6-litellm-smoke",
    "approved_file_read": "freyja6-tool-smoke",
    "safe_terminal": "freyja6-tool-smoke",
    "mcp_tool": "freyja6-tool-smoke",
    "calendar_read": "freyja6-tool-smoke",
    "calendar_create_event": "freyja6-calendar-write-smoke",
    "home_assistant_query": "freyja6-tool-smoke",
    "coding_workflow": "freyja6-tool-smoke",
    "atlas_reboot_return": "freyja6-restart-evidence",
}
TOOL_ACCEPTANCE_TRACE_FIELDS = {
    "approved_file_read": "tool_trace_id",
    "safe_terminal": "tool_trace_id",
    "mcp_tool": "tool_trace_id",
    "calendar_read": "tool_trace_id",
    "calendar_create_event": "tool_trace_id",
    "home_assistant_query": "tool_trace_id",
    "coding_workflow": "handoff_trace_id",
}
ACCEPTANCE_PRODUCER_TIMESTAMP_FIELDS = {
    "discord_reply": ("last_discord_smoke", "timestamp"),
    "restart_identity_session": ("last_restart_evidence", "timestamp"),
    "remember_fact": ("last_restart_evidence", "timestamp"),
    "litellm_to_vulcan": ("last_litellm_smoke", "timestamp"),
    "model_switch": ("last_litellm_smoke", "timestamp"),
    "approved_file_read": ("last_tool_smoke", "timestamp"),
    "safe_terminal": ("last_tool_smoke", "timestamp"),
    "mcp_tool": ("last_tool_smoke", "timestamp"),
    "calendar_read": ("last_tool_smoke", "timestamp"),
    "calendar_create_event": ("last_calendar_write_smoke", "timestamp"),
    "home_assistant_query": ("last_tool_smoke", "timestamp"),
    "coding_workflow": ("last_tool_smoke", "timestamp"),
    "atlas_reboot_return": ("last_restart_evidence", "timestamp"),
}


ACCEPTANCE_REQUIREMENTS = [
    {
        "id": "discord_reply",
        "description": "Reply through the dedicated Discord test channel.",
        "evidence_fields": ["discord_channel_id_redacted", "message_trace_id", "reply_trace_id", "verification_method"],
    },
    {
        "id": "restart_identity_session",
        "description": "Survive restart with identity and session intact.",
        "evidence_fields": ["restart_trace_id", "identity_before", "identity_after", "session_restored"],
    },
    {
        "id": "remember_fact",
        "description": "Remember an intentionally stored fact through Hermes native memory.",
        "evidence_fields": ["stored_fact_label", "recall_trace_id", "memory_provider"],
    },
    {
        "id": "litellm_to_vulcan",
        "description": "Use Vulcan models through LiteLLM.",
        "evidence_fields": ["litellm_request_id", "model", "response_model", "vulcan_backend"],
    },
    {
        "id": "model_switch",
        "description": "Switch models through the LiteLLM gateway.",
        "evidence_fields": ["models_tested", "response_models", "gateway_trace_ids"],
    },
    {
        "id": "approved_file_read",
        "description": "Read a file under the approved filesystem root.",
        "evidence_fields": ["approved_path", "tool_trace_id", "bytes_read"],
    },
    {
        "id": "safe_terminal",
        "description": "Execute a safe terminal command.",
        "evidence_fields": ["command", "tool_trace_id", "exit_code", "working_dir"],
    },
    {
        "id": "mcp_tool",
        "description": "Call an MCP tool.",
        "evidence_fields": ["server", "tool", "tool_trace_id", "status_code"],
    },
    {
        "id": "calendar_read",
        "description": "Read the family calendar through the tool boundary.",
        "evidence_fields": ["calendar_name_redacted", "tool_trace_id", "status_code"],
    },
    {
        "id": "calendar_create_event",
        "description": "Create an event from 'Add basement cleanup this Saturday'.",
        "evidence_fields": ["event_title", "event_date", "tool_trace_id", "created_event_id"],
    },
    {
        "id": "home_assistant_query",
        "description": "Query Home Assistant through the tool boundary.",
        "evidence_fields": ["entity_id_redacted", "tool_trace_id", "states_count"],
    },
    {
        "id": "coding_workflow",
        "description": "Invoke the coding workflow through OpenCode or the approved coding executor.",
        "evidence_fields": ["executor", "handoff_trace_id", "result_summary", "status_keys"],
    },
    {
        "id": "atlas_reboot_return",
        "description": "Return automatically after Atlas reboot.",
        "evidence_fields": [
            "reboot_window",
            "container_status_after",
            "discord_reply_after_reboot",
            "discord_reply_after_reboot_verification",
        ],
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Freyja 6.0 acceptance status.")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_status(evidence_path: Path) -> dict[str, Any]:
    scaffold = _scaffold_status()
    live_evidence = _load_json(evidence_path)
    evidence_contract = _live_evidence_contract(live_evidence)
    evidence_by_id = _evidence_by_id(live_evidence)
    secrets_detected = _contains_secret_marker(live_evidence)
    acceptance = [_acceptance_status(item, evidence_by_id.get(item["id"]), evidence_by_id, live_evidence) for item in ACCEPTANCE_REQUIREMENTS]
    remaining = [item["id"] for item in acceptance if item["status"] != "complete"]
    complete = scaffold["ok"] and evidence_contract["status"] == "pass" and not secrets_detected and not remaining
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-acceptance-status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        "scaffold": scaffold,
        "evidence_contract": evidence_contract,
        "evidence": str(evidence_path),
        "secrets_detected": secrets_detected,
        "remaining_acceptance": remaining,
        "acceptance": acceptance,
        "next_actions": _next_actions(scaffold, evidence_contract, acceptance, evidence_path, secrets_detected),
    }


def _scaffold_status() -> dict[str, Any]:
    agent_config = _load_yaml(REPO_ROOT / "config/freyja6/freyja-test.yaml")
    compose = _load_yaml(REPO_ROOT / "deploy/compose/freyja6/compose.yaml")
    litellm = _load_yaml(REPO_ROOT / "deploy/compose/freyja6/litellm.config.yaml")
    schedules = _load_yaml(REPO_ROOT / "config/freyja6/schedules.yaml")
    identity_template = REPO_ROOT / "config/freyja6/bootstrap/identity.md"
    approved_smoke = REPO_ROOT / "config/freyja6/bootstrap/approved-smoke.txt"
    failures: list[str] = []

    agents = agent_config.get("agents", [])
    if [agent.get("id") for agent in agents] != ["freyja-test"]:
        failures.append("Phase 1 must define exactly one live agent: freyja-test.")

    services = compose.get("services", {})
    if set(services) != {"litellm-db", "litellm", "hermes-freyja-test"}:
        failures.append("Compose must contain only litellm-db, litellm, and hermes-freyja-test.")

    agent = agents[0] if agents else {}
    if agent.get("models", {}).get("gateway_base_url") != "http://litellm:4000/v1":
        failures.append("freyja-test must access models through LiteLLM.")
    if agent.get("memory", {}).get("provider") != "hermes-native":
        failures.append("freyja-test must start with Hermes native memory.")
    if not identity_template.exists() or "freyja-test" not in identity_template.read_text(encoding="utf-8"):
        failures.append("freyja-test must have a tracked identity/personality seed.")
    if not approved_smoke.exists():
        failures.append("freyja-test must have a tracked approved-file smoke seed.")
    if agent.get("messaging", {}).get("gateway") != "discord":
        failures.append("Phase 1 must use one Discord messaging gateway.")
    if agent.get("schedules", {}).get("host_config_source") != "config/freyja6/schedules.yaml":
        failures.append("freyja-test must declare its Freyja 6 schedule config source.")

    model_names = [entry.get("model_name") for entry in litellm.get("model_list", [])]
    if model_names != ["vulcan-fast", "vulcan-general", "vulcan-code"]:
        failures.append("LiteLLM must expose only the Freyja 6 Vulcan validation aliases.")

    schedule_ids = [item.get("id") for item in schedules.get("schedules", [])]
    if schedules.get("agent_id") != "freyja-test":
        failures.append("Freyja 6 schedules must be scoped to freyja-test.")
    if schedule_ids != ["freyja-test-health-heartbeat", "freyja-test-daily-tool-smoke"]:
        failures.append("Freyja 6 schedules must include only the two freyja-test validation schedules.")

    guardrails = agent_config.get("guardrails", {})
    for key in (
        "local_private_data_default",
        "cloud_model_use_requires_explicit_approval",
        "do_not_modify_existing_bots_or_credentials",
        "do_not_migrate_existing_systems",
    ):
        if guardrails.get(key) is not True:
            failures.append(f"Missing guardrail: {key}.")

    return {
        "ok": not failures,
        "failures": failures,
        "source_files": [
            "config/freyja6/freyja-test.yaml",
            "deploy/compose/freyja6/compose.yaml",
            "deploy/compose/freyja6/litellm.config.yaml",
            "config/freyja6/schedules.yaml",
            "config/freyja6/bootstrap/identity.md",
            "config/freyja6/bootstrap/approved-smoke.txt",
        ],
    }


def _live_evidence_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "pass",
            "message": "No live evidence has been captured yet.",
        }
    failures: list[str] = []
    load_failure = payload.get("_load_failure")
    if isinstance(load_failure, str) and load_failure:
        failures.append(load_failure)
    if payload.get("report_type") != "freyja6-live-evidence":
        failures.append("Live evidence report_type must be freyja6-live-evidence.")
    if payload.get("schema_version") != "1.0":
        failures.append("Live evidence schema_version must be 1.0.")
    if "acceptance" in payload and not isinstance(payload.get("acceptance"), (dict, list)):
        failures.append("Live evidence acceptance must be an object or list.")
    unexpected_acceptance = _unexpected_acceptance_ids(payload.get("acceptance"))
    if unexpected_acceptance:
        failures.append("Live evidence acceptance contains unexpected ids: " + ", ".join(unexpected_acceptance) + ".")
    acceptance_shape_failures = _acceptance_shape_failures(payload.get("acceptance"))
    failures.extend(acceptance_shape_failures)
    return {
        "status": "pass" if not failures else "fail",
        "message": "Live evidence contract is valid." if not failures else "Live evidence contract is invalid.",
        "failures": failures,
    }


def _unexpected_acceptance_ids(raw: Any) -> list[str]:
    expected = {item["id"] for item in ACCEPTANCE_REQUIREMENTS}
    if isinstance(raw, dict):
        return sorted(str(key) for key in raw if str(key) not in expected)
    if isinstance(raw, list):
        ids = [str(item.get("id") or "") for item in raw if isinstance(item, dict) and item.get("id")]
        return sorted(item for item in ids if item not in expected)
    return []


def _acceptance_shape_failures(raw: Any) -> list[str]:
    failures: list[str] = []
    ids: list[str] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            ids.append(str(key))
            if not isinstance(value, dict):
                failures.append(f"Live evidence acceptance entry {key} must be an object.")
                continue
            if "evidence" in value and not isinstance(value.get("evidence"), dict):
                failures.append(f"Live evidence acceptance entry {key} evidence must be an object.")
            embedded_id = value.get("id")
            if embedded_id is not None and str(embedded_id) != str(key):
                failures.append(f"Live evidence acceptance entry {key} id must match its object key.")
    elif isinstance(raw, list):
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                failures.append(f"Live evidence acceptance entry {index} must be an object.")
                continue
            item_id = str(item.get("id") or "")
            if not item_id:
                failures.append(f"Live evidence acceptance entry {index} must include an id.")
                continue
            if "evidence" in item and not isinstance(item.get("evidence"), dict):
                failures.append(f"Live evidence acceptance entry {item_id} evidence must be an object.")
            ids.append(item_id)
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        failures.append("Live evidence acceptance contains duplicate ids: " + ", ".join(duplicates) + ".")
    return failures


def _acceptance_status(
    requirement: dict[str, Any],
    evidence: dict[str, Any] | None,
    evidence_by_id: dict[str, dict[str, Any]],
    live_evidence: dict[str, Any],
) -> dict[str, Any]:
    required = requirement["evidence_fields"]
    payload = evidence.get("evidence") if isinstance(evidence, dict) and isinstance(evidence.get("evidence"), dict) else {}
    missing = [field for field in required if not _present(payload.get(field))]
    missing_metadata = [field for field in REQUIRED_EVIDENCE_METADATA if not _present(evidence.get(field) if isinstance(evidence, dict) else None)]
    semantic_failures = [] if not evidence else _semantic_failures(requirement["id"], payload, evidence, evidence_by_id, live_evidence)
    explicit_status = str(evidence.get("status") or "") if isinstance(evidence, dict) else ""
    if not evidence:
        status = "missing"
    elif missing or missing_metadata or semantic_failures:
        status = "partial"
    elif explicit_status in {"failed", "blocked"}:
        status = explicit_status
    elif explicit_status != "complete":
        status = "partial"
    else:
        status = "complete"
    return {
        "id": requirement["id"],
        "description": requirement["description"],
        "status": status,
        "required_evidence": required,
        "required_metadata": REQUIRED_EVIDENCE_METADATA,
        "metadata": _acceptance_metadata(evidence),
        "present_evidence": [field for field in required if field not in missing],
        "missing_evidence": missing,
        "missing_metadata": missing_metadata,
        "semantic_failures": semantic_failures,
    }


def _acceptance_metadata(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    return {field: evidence[field] for field in REQUIRED_EVIDENCE_METADATA if _present(evidence.get(field))}


def _semantic_failures(
    requirement_id: str,
    payload: dict[str, Any],
    evidence: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    live_evidence: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    metadata_type_failures = _metadata_type_failures(evidence)
    failures.extend(metadata_type_failures)
    captured_at_failure = _captured_at_failure(evidence.get("captured_at"))
    if captured_at_failure:
        failures.append(captured_at_failure)
    producer_timestamp_failure = _producer_timestamp_failure(requirement_id, evidence, live_evidence)
    if producer_timestamp_failure:
        failures.append(producer_timestamp_failure)
    trace_failures = _trace_failures(payload)
    failures.extend(trace_failures)
    tool_trace_failure = _tool_acceptance_trace_reuse_failure(requirement_id, payload, evidence_by_id)
    if tool_trace_failure:
        failures.append(tool_trace_failure)
    expected_source = EXPECTED_ACCEPTANCE_SOURCES.get(requirement_id)
    if expected_source and evidence.get("source") and evidence.get("source") != expected_source:
        failures.append(f"source must be {expected_source}.")
    if requirement_id == "discord_reply":
        channel_type_failure = _string_field_failure("discord_channel_id_redacted", payload.get("discord_channel_id_redacted"))
        if channel_type_failure:
            failures.append(channel_type_failure)
        channel = str(payload.get("discord_channel_id_redacted") or "")
        if not channel.startswith("discord-channel-"):
            failures.append("discord_channel_id_redacted must be redacted.")
        if payload.get("message_trace_id") == payload.get("reply_trace_id"):
            failures.append("message_trace_id and reply_trace_id must be distinct.")
        if payload.get("verification_method") != "discord-api":
            failures.append("verification_method must be discord-api for final acceptance.")
        discord_failure = _discord_reply_producer_failure(payload, live_evidence)
        if discord_failure:
            failures.append(discord_failure)
    elif requirement_id == "restart_identity_session":
        if payload.get("session_restored") is not True:
            failures.append("session_restored must be true.")
        if _hash_has_placeholder(payload.get("identity_before")) or _hash_has_placeholder(payload.get("identity_after")):
            failures.append("identity hashes must not use placeholder ellipses.")
        if not _hash_is_sha256(payload.get("identity_before")) or not _hash_is_sha256(payload.get("identity_after")):
            failures.append("identity hashes must be sha256-prefixed 64-character hex values.")
        if _hash_value(payload.get("identity_before")) != _hash_value(payload.get("identity_after")):
            failures.append("identity_before and identity_after must match.")
        restart_failure = _restart_identity_producer_failure(payload, live_evidence)
        if restart_failure:
            failures.append(restart_failure)
    elif requirement_id == "remember_fact":
        if payload.get("memory_provider") != "hermes-native":
            failures.append("memory_provider must be hermes-native.")
        if not _safe_local_identifier(str(payload.get("stored_fact_label") or "")):
            failures.append("stored_fact_label must be a non-empty local identifier.")
        restart_trace_id = _acceptance_trace(evidence_by_id, "restart_identity_session", "restart_trace_id")
        if restart_trace_id and payload.get("recall_trace_id") == restart_trace_id:
            failures.append("recall_trace_id must be distinct from restart_trace_id.")
        memory_failure = _remember_fact_producer_failure(payload, live_evidence)
        if memory_failure:
            failures.append(memory_failure)
    elif requirement_id == "litellm_to_vulcan":
        if payload.get("model") not in {"vulcan-fast", "vulcan-general", "vulcan-code"}:
            failures.append("model must be one of the approved Vulcan aliases.")
        if payload.get("response_model") != payload.get("model"):
            failures.append("response_model must match model.")
        backend_type_failure = _string_field_failure("vulcan_backend", payload.get("vulcan_backend"))
        if backend_type_failure:
            failures.append(backend_type_failure)
        backend = str(payload.get("vulcan_backend") or "")
        if not _backend_is_redacted_local_gateway(backend):
            failures.append("vulcan_backend must be a redacted local LiteLLM/Vulcan endpoint.")
        litellm_failure = _litellm_to_vulcan_producer_failure(payload, live_evidence)
        if litellm_failure:
            failures.append(litellm_failure)
    elif requirement_id == "model_switch":
        models = payload.get("models_tested")
        if not isinstance(models, list) or len(set(models)) < 2:
            failures.append("models_tested must contain at least two distinct approved aliases.")
        elif any(model not in {"vulcan-fast", "vulcan-general", "vulcan-code"} for model in models):
            failures.append("models_tested contains an unapproved alias.")
        trace_ids = payload.get("gateway_trace_ids")
        if not isinstance(trace_ids, list) or len(trace_ids) < 2:
            failures.append("gateway_trace_ids must contain at least two traces.")
        elif len(set(str(trace_id) for trace_id in trace_ids)) < 2:
            failures.append("gateway_trace_ids must contain at least two distinct traces.")
        if isinstance(models, list) and isinstance(trace_ids, list) and len(models) != len(trace_ids):
            failures.append("gateway_trace_ids must contain exactly one trace per tested model.")
        elif isinstance(trace_ids, list) and len(trace_ids) != len(set(str(trace_id) for trace_id in trace_ids)):
            failures.append("gateway_trace_ids must not contain duplicate traces.")
        response_models = payload.get("response_models")
        if not isinstance(response_models, list) or len(response_models) < 2:
            failures.append("response_models must contain at least two returned aliases.")
        elif any(model not in {"vulcan-fast", "vulcan-general", "vulcan-code"} for model in response_models):
            failures.append("response_models contains an unapproved alias.")
        if isinstance(models, list) and isinstance(response_models, list) and response_models != models:
            failures.append("response_models must match models_tested.")
        model_switch_failure = _model_switch_producer_failure(payload, live_evidence)
        if model_switch_failure:
            failures.append(model_switch_failure)
    elif requirement_id == "safe_terminal":
        if payload.get("command") not in {"pwd", "date", "whoami", "ls", "rg"}:
            failures.append("command must be in the Freyja 6 safe terminal allowlist.")
        if payload.get("exit_code") != 0:
            failures.append("exit_code must be 0.")
        if payload.get("working_dir") != "freyja-os":
            failures.append("working_dir must be freyja-os.")
        tool_failure = _tool_smoke_producer_failure(requirement_id, payload, live_evidence)
        if tool_failure:
            failures.append(tool_failure)
    elif requirement_id == "approved_file_read":
        path_type_failure = _string_field_failure("approved_path", payload.get("approved_path"))
        if path_type_failure:
            failures.append(path_type_failure)
        approved_path = str(payload.get("approved_path") or "")
        if not approved_path.startswith("approved-files/"):
            failures.append("approved_path must be under approved-files.")
        if not isinstance(payload.get("bytes_read"), int) or payload.get("bytes_read") <= 0:
            failures.append("bytes_read must be a positive integer.")
        tool_failure = _tool_smoke_producer_failure(requirement_id, payload, live_evidence)
        if tool_failure:
            failures.append(tool_failure)
    elif requirement_id == "mcp_tool":
        if payload.get("server") not in {"freyja-core-gateway", "freyja-terminal"}:
            failures.append("server must be an approved Freyja 6 MCP server.")
        if payload.get("tool") != "status.check":
            failures.append("tool must be status.check.")
        status_code_failure = _tool_status_code_failure(payload.get("status_code"))
        if status_code_failure:
            failures.append(status_code_failure)
        tool_failure = _tool_smoke_producer_failure(requirement_id, payload, live_evidence)
        if tool_failure:
            failures.append(tool_failure)
    elif requirement_id == "calendar_read":
        if payload.get("calendar_name_redacted") != "configured-calendar":
            failures.append("calendar_name_redacted must be configured-calendar.")
        status_code_failure = _tool_status_code_failure(payload.get("status_code"))
        if status_code_failure:
            failures.append(status_code_failure)
        tool_failure = _tool_smoke_producer_failure(requirement_id, payload, live_evidence)
        if tool_failure:
            failures.append(tool_failure)
    elif requirement_id == "calendar_create_event":
        if payload.get("event_title") != "Basement cleanup":
            failures.append("event_title must be Basement cleanup.")
        event_date_value = payload.get("event_date")
        event_date_type_failure = _string_field_failure("event_date", event_date_value)
        if event_date_type_failure:
            failures.append(event_date_type_failure)
        event_date = event_date_value if isinstance(event_date_value, str) else ""
        if not _is_iso_date(event_date):
            failures.append("event_date must be an ISO date.")
        elif not _is_saturday(event_date):
            failures.append("event_date must be a Saturday.")
        calendar_producer_failure = _calendar_write_producer_failure(payload, live_evidence)
        if calendar_producer_failure:
            failures.append(calendar_producer_failure)
    elif requirement_id == "home_assistant_query":
        entity_type_failure = _string_field_failure("entity_id_redacted", payload.get("entity_id_redacted"))
        if entity_type_failure:
            failures.append(entity_type_failure)
        entity = str(payload.get("entity_id_redacted") or "")
        if not entity.startswith("domain:"):
            failures.append("entity_id_redacted must be domain-scoped.")
        elif not _home_assistant_domain_redaction_ok(entity):
            failures.append("entity_id_redacted must be a redacted Home Assistant domain.")
        if not isinstance(payload.get("states_count"), int) or payload.get("states_count") <= 0:
            failures.append("states_count must be a positive integer.")
        tool_failure = _tool_smoke_producer_failure(requirement_id, payload, live_evidence)
        if tool_failure:
            failures.append(tool_failure)
    elif requirement_id == "coding_workflow":
        if payload.get("executor") != "opencode":
            failures.append("executor must be opencode.")
        if payload.get("result_summary") != CODING_WORKFLOW_RESULT_SUMMARY:
            failures.append("result_summary must match the Freyja Core OpenCode status summary.")
        if not isinstance(payload.get("status_keys"), list) or not payload.get("status_keys"):
            failures.append("status_keys must be a non-empty list.")
        tool_failure = _tool_smoke_producer_failure(requirement_id, payload, live_evidence)
        if tool_failure:
            failures.append(tool_failure)
    elif requirement_id == "atlas_reboot_return":
        reboot_window_type_failure = _string_field_failure("reboot_window", payload.get("reboot_window"))
        if reboot_window_type_failure:
            failures.append(reboot_window_type_failure)
        reboot_window_value = payload.get("reboot_window") if isinstance(payload.get("reboot_window"), str) else ""
        reboot_window_failure = _reboot_window_failure(reboot_window_value)
        if reboot_window_failure:
            failures.append(reboot_window_failure)
        container_status_type_failure = _string_field_failure("container_status_after", payload.get("container_status_after"))
        if container_status_type_failure:
            failures.append(container_status_type_failure)
        container_status = payload.get("container_status_after") if isinstance(payload.get("container_status_after"), str) else ""
        if not _container_is_ok(container_status):
            failures.append("container_status_after must be running or healthy.")
        restart_trace_id = _acceptance_trace(evidence_by_id, "restart_identity_session", "restart_trace_id")
        if restart_trace_id and payload.get("discord_reply_after_reboot") == restart_trace_id:
            failures.append("discord_reply_after_reboot must be distinct from restart_trace_id.")
        initial_reply_trace_id = _acceptance_trace(evidence_by_id, "discord_reply", "reply_trace_id")
        if initial_reply_trace_id and payload.get("discord_reply_after_reboot") == initial_reply_trace_id:
            failures.append("discord_reply_after_reboot must be distinct from the initial Discord reply trace.")
        if payload.get("discord_reply_after_reboot_verification") != "discord-api":
            failures.append("discord_reply_after_reboot_verification must be discord-api.")
        reboot_failure = _reboot_return_producer_failure(payload, live_evidence)
        if reboot_failure:
            failures.append(reboot_failure)
    return failures


def _string_field_failure(field: str, value: Any) -> str:
    if not _present(value):
        return ""
    if not isinstance(value, str):
        return f"{field} must be a string."
    return ""


def _metadata_type_failures(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in REQUIRED_EVIDENCE_METADATA:
        value = evidence.get(field)
        if _present(value) and not isinstance(value, str):
            failures.append(f"{field} must be a string.")
    return failures


def _producer_timestamp_failure(requirement_id: str, evidence: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    if evidence.get("status") != "complete":
        return ""
    producer_ref = ACCEPTANCE_PRODUCER_TIMESTAMP_FIELDS.get(requirement_id)
    if not producer_ref:
        return ""
    producer_key, timestamp_key = producer_ref
    producer = live_evidence.get(producer_key)
    if not isinstance(producer, dict):
        return f"{requirement_id} must include matching {producer_key} producer evidence."
    captured_at = evidence.get("captured_at") if isinstance(evidence.get("captured_at"), str) else ""
    producer_timestamp_value = producer.get(timestamp_key)
    if not _present(producer_timestamp_value):
        return f"{producer_key}.{timestamp_key} must be present."
    if not isinstance(producer_timestamp_value, str):
        return f"{producer_key}.{timestamp_key} must be a string."
    producer_timestamp = producer_timestamp_value
    if captured_at != producer_timestamp:
        return f"captured_at must match {producer_key}.{timestamp_key}."
    return ""


def _calendar_write_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_calendar_write_smoke")
    if not isinstance(producer, dict):
        return ""
    create = producer.get("create")
    if not isinstance(create, dict):
        return "last_calendar_write_smoke.create must be present."
    if str(payload.get("tool_trace_id") or "") != str(create.get("trace_id") or ""):
        return "tool_trace_id must match last_calendar_write_smoke.create.trace_id."
    event = create.get("event")
    if isinstance(event, dict):
        title = str(event.get("title") or event.get("summary") or "")
        if title and title != "Basement cleanup":
            return "created event title must match Basement cleanup."
    if not _calendar_write_producer_verified(producer, create):
        return "tool_trace_id must reference a verified calendar.create_event producer result."
    if str(payload.get("event_title") or "") != str(producer.get("event_title") or ""):
        return "event_title must match last_calendar_write_smoke.event_title."
    if str(payload.get("event_date") or "") != str(producer.get("event_date") or ""):
        return "event_date must match last_calendar_write_smoke.event_date."
    event_id_failure = _calendar_created_event_id_failure(payload, create)
    if event_id_failure:
        return event_id_failure
    return ""


def _calendar_created_event_id_failure(payload: dict[str, Any], create: dict[str, Any]) -> str:
    event = create.get("event")
    if not isinstance(event, dict):
        return "last_calendar_write_smoke.create.event must be present."
    producer_identifier = _created_event_identifier(event)
    if not producer_identifier:
        return "created event must include an event identifier."
    if str(payload.get("created_event_id") or "") != _redact_event_id(producer_identifier):
        return "created_event_id must match the redacted created event identifier."
    return ""


def _calendar_write_producer_verified(producer: dict[str, Any], create: dict[str, Any]) -> bool:
    event = create.get("event")
    event_date = str(producer.get("event_date") or "")
    if (
        producer.get("ok") is not True
        or create.get("ok") is not True
        or create.get("tool") != "calendar.create_event"
        or _trace_value_failure("trace_id", create.get("trace_id"))
        or not isinstance(event, dict)
    ):
        return False
    title = str(event.get("title") or event.get("summary") or "")
    start = str(event.get("start") or event.get("start_time") or "")
    end = str(event.get("end") or event.get("end_time") or "")
    try:
        parsed_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return False
    duration_minutes = producer.get("duration_minutes", 60)
    if not isinstance(duration_minutes, int) or duration_minutes < 1 or duration_minutes > 240:
        duration_minutes = 60
    return (
        title == "Basement cleanup"
        and _is_iso_date(event_date)
        and parsed_start.tzinfo is not None
        and parsed_start.utcoffset() is not None
        and parsed_end.tzinfo is not None
        and parsed_end.utcoffset() is not None
        and parsed_start.date().isoformat() == event_date
        and parsed_end == parsed_start + timedelta(minutes=duration_minutes)
        and _created_event_has_identifier(event)
    )


def _created_event_has_identifier(event: dict[str, Any]) -> bool:
    return bool(_created_event_identifier(event))


def _created_event_identifier(event: dict[str, Any]) -> str:
    for key in ("event_id", "id", "uid"):
        value = event.get(key)
        if not isinstance(value, str):
            continue
        identifier = value.strip()
        if identifier and "..." not in identifier:
            return identifier
    return ""


def _redact_event_id(identifier: str) -> str:
    value = identifier.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return f"event-id-...{value}"
    return f"event-id-{value[:4]}...{value[-4:]}"


def _discord_reply_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_discord_smoke")
    if not isinstance(producer, dict):
        return ""
    expected = {
        "discord_channel_id_redacted": "channel_id_redacted",
        "message_trace_id": "message_trace_id",
        "reply_trace_id": "reply_trace_id",
        "verification_method": "verification",
    }
    for evidence_field, producer_field in expected.items():
        if payload.get(evidence_field) != producer.get(producer_field) or not isinstance(producer.get(producer_field), str):
            return f"{evidence_field} must match last_discord_smoke.{producer_field}."
    if not _discord_api_producer_verified(producer):
        return "discord_reply must reference an API-verified last_discord_smoke result."
    return ""


def _discord_api_producer_verified(producer: dict[str, Any]) -> bool:
    return (
        producer.get("ok") is True
        and producer.get("verification") == "discord-api"
        and isinstance(producer.get("channel_id_redacted"), str)
        and producer.get("channel_id_redacted", "").startswith("discord-channel-")
        and _trace_value_failure("message_trace_id", producer.get("message_trace_id")) == ""
        and _trace_value_failure("reply_trace_id", producer.get("reply_trace_id")) == ""
        and producer.get("message_trace_id") != producer.get("reply_trace_id")
        and producer.get("message_from_user") is True
        and producer.get("reply_from_bot") is True
        and producer.get("reply_references_message") is True
        and producer.get("chronological") is True
    )


def _litellm_to_vulcan_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_litellm_smoke")
    if not isinstance(producer, dict):
        return ""
    if payload.get("vulcan_backend") != producer.get("base_url_redacted") or not isinstance(producer.get("base_url_redacted"), str):
        return "vulcan_backend must match last_litellm_smoke.base_url_redacted."
    result = _litellm_result_by_trace(producer, str(payload.get("litellm_request_id") or ""))
    if not result:
        return "litellm_request_id must match a last_litellm_smoke result trace."
    if payload.get("model") != result.get("model") or not isinstance(result.get("model"), str):
        return "model must match the last_litellm_smoke result model."
    if payload.get("response_model") != result.get("response_model") or not isinstance(result.get("response_model"), str):
        return "response_model must match the last_litellm_smoke result response_model."
    if not _litellm_result_verified(result, producer):
        return "litellm_request_id must reference a verified LiteLLM gateway result."
    return ""


def _model_switch_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_litellm_smoke")
    if not isinstance(producer, dict):
        return ""
    models = payload.get("models_tested")
    response_models = payload.get("response_models")
    trace_ids = payload.get("gateway_trace_ids")
    if not isinstance(models, list) or not isinstance(trace_ids, list):
        return ""
    for index, (model, trace_id) in enumerate(zip(models, trace_ids)):
        result = _litellm_result_by_trace(producer, str(trace_id))
        if not result:
            return "gateway_trace_ids must match last_litellm_smoke result traces."
        if model != result.get("model") or not isinstance(result.get("model"), str):
            return "models_tested must align with last_litellm_smoke result models."
        if isinstance(response_models, list) and index < len(response_models):
            if response_models[index] != result.get("response_model") or not isinstance(result.get("response_model"), str):
                return "response_models must align with last_litellm_smoke result response_models."
        if not _litellm_result_verified(result, producer):
            return "gateway_trace_ids must reference verified LiteLLM gateway results."
    return ""


def _tool_smoke_producer_failure(requirement_id: str, payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_tool_smoke")
    if not isinstance(producer, dict):
        return ""
    smoke_key = {
        "approved_file_read": "approved_file",
        "safe_terminal": "safe_terminal",
        "mcp_tool": "mcp_discovery",
        "calendar_read": "calendar_read",
        "home_assistant_query": "home_assistant_query",
        "coding_workflow": "coding_workflow",
    }.get(requirement_id)
    if not smoke_key:
        return ""
    item = producer.get(smoke_key)
    if not isinstance(item, dict):
        return f"last_tool_smoke.{smoke_key} must be present."
    trace_field = "handoff_trace_id" if requirement_id == "coding_workflow" else "tool_trace_id"
    if payload.get(trace_field) != item.get("trace_id") or not isinstance(item.get("trace_id"), str):
        return f"{trace_field} must match last_tool_smoke.{smoke_key}.trace_id."
    if not _tool_smoke_item_verified(requirement_id, payload, item, producer):
        return f"{trace_field} must reference a verified last_tool_smoke.{smoke_key} result."
    return ""


def _tool_smoke_item_verified(requirement_id: str, payload: dict[str, Any], item: dict[str, Any], producer: dict[str, Any]) -> bool:
    if item.get("ok") is not True or _trace_value_failure("trace_id", item.get("trace_id")):
        return False
    if requirement_id == "approved_file_read":
        return (
            isinstance(item.get("path_redacted"), str)
            and item.get("path_redacted", "").startswith("approved-files/")
            and payload.get("approved_path") == item.get("path_redacted")
            and payload.get("bytes_read") == item.get("bytes")
            and isinstance(item.get("bytes"), int)
            and item["bytes"] > 0
        )
    if requirement_id == "safe_terminal":
        return (
            item.get("command") == payload.get("command")
            and item.get("exit_code") == payload.get("exit_code") == 0
            and item.get("command") in {"pwd", "date", "whoami", "ls", "rg"}
            and payload.get("working_dir") == item.get("working_dir") == "freyja-os"
        )
    if requirement_id == "mcp_tool":
        core_mcp_health = producer.get("core_mcp_health")
        return (
            isinstance(core_mcp_health, dict)
            and core_mcp_health.get("ok") is True
            and item.get("tool") == payload.get("tool") == "status.check"
            and payload.get("status_code") == item.get("status_code")
            and _status_code_is_2xx(item.get("status_code"))
        )
    if requirement_id == "calendar_read":
        return (
            item.get("tool") == "calendar.list_events"
            and payload.get("calendar_name_redacted") == "configured-calendar"
            and payload.get("status_code") == item.get("status_code")
            and _status_code_is_2xx(item.get("status_code"))
        )
    if requirement_id == "home_assistant_query":
        domain = item.get("domain")
        if not isinstance(domain, str):
            return False
        return (
            item.get("tool") == "home_assistant.list_states"
            and payload.get("entity_id_redacted") == "domain:" + domain
            and _home_assistant_domain_redaction_ok("domain:" + domain)
            and payload.get("states_count") == item.get("states_count")
            and isinstance(item.get("result_keys"), list)
            and ("states" in item["result_keys"] or "entities" in item["result_keys"])
            and isinstance(item.get("states_count"), int)
            and item["states_count"] > 0
        )
    if requirement_id == "coding_workflow":
        return (
            item.get("tool") == "opencode.status"
            and item.get("alias") == "freyja-core-coder"
            and payload.get("executor") == "opencode"
            and payload.get("result_summary") == item.get("result_summary") == CODING_WORKFLOW_RESULT_SUMMARY
            and item.get("status_payload_present") is True
            and isinstance(item.get("status_keys"), list)
            and bool(item["status_keys"])
            and all(isinstance(key, str) for key in item["status_keys"])
            and payload.get("status_keys") == item.get("status_keys")
        )
    return False


def _tool_status_code_failure(value: Any) -> str:
    if not isinstance(value, int):
        return "status_code must be an integer."
    if not _status_code_is_2xx(value):
        return "status_code must be 2xx."
    return ""


def _status_code_is_2xx(value: Any) -> bool:
    return isinstance(value, int) and 200 <= value < 300


def _restart_identity_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_restart_evidence")
    if not isinstance(producer, dict):
        return ""
    if payload.get("restart_trace_id") != producer.get("restart_trace_id") or not isinstance(producer.get("restart_trace_id"), str):
        return "restart_trace_id must match last_restart_evidence.restart_trace_id."
    if _hash_value(payload.get("identity_before")) != producer.get("identity_before_sha256") or not isinstance(producer.get("identity_before_sha256"), str):
        return "identity_before must match last_restart_evidence.identity_before_sha256."
    if _hash_value(payload.get("identity_after")) != producer.get("identity_after_sha256") or not isinstance(producer.get("identity_after_sha256"), str):
        return "identity_after must match last_restart_evidence.identity_after_sha256."
    if producer.get("identity_matches_before") is not True or producer.get("session_restored") is not True:
        return "restart_identity_session must reference verified restart identity/session evidence."
    return ""


def _remember_fact_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_restart_evidence")
    if not isinstance(producer, dict):
        return ""
    if payload.get("stored_fact_label") != producer.get("stored_fact_label") or not isinstance(producer.get("stored_fact_label"), str):
        return "stored_fact_label must match last_restart_evidence.stored_fact_label."
    if payload.get("recall_trace_id") != producer.get("memory_recall_trace_id") or not isinstance(producer.get("memory_recall_trace_id"), str):
        return "recall_trace_id must match last_restart_evidence.memory_recall_trace_id."
    if payload.get("memory_provider") != producer.get("memory_provider") or not isinstance(producer.get("memory_provider"), str):
        return "memory_provider must match last_restart_evidence.memory_provider."
    if producer.get("memory_fact_present") is not True or producer.get("memory_fact_recalled") is not True:
        return "remember_fact must reference verified memory fact and recall evidence."
    return ""


def _reboot_return_producer_failure(payload: dict[str, Any], live_evidence: dict[str, Any]) -> str:
    producer = live_evidence.get("last_restart_evidence")
    if not isinstance(producer, dict):
        return ""
    expected = {
        "reboot_window": "reboot_window",
        "container_status_after": "container_status_after",
        "discord_reply_after_reboot": "discord_reply_after_reboot",
        "discord_reply_after_reboot_verification": "discord_reply_after_reboot_verification",
    }
    for evidence_field, producer_field in expected.items():
        if payload.get(evidence_field) != producer.get(producer_field) or not isinstance(producer.get(producer_field), str):
            return f"{evidence_field} must match last_restart_evidence.{producer_field}."
    return ""


def _litellm_result_by_trace(producer: dict[str, Any], trace_id: str) -> dict[str, Any]:
    results = producer.get("results")
    if not isinstance(results, list):
        return {}
    for item in results:
        if isinstance(item, dict) and isinstance(item.get("trace_id"), str) and item.get("trace_id") == trace_id:
            return item
    return {}


def _litellm_result_verified(result: dict[str, Any], producer: dict[str, Any]) -> bool:
    listed = producer.get("listed_models")
    listed_models = {item for item in listed if isinstance(item, str)} if isinstance(listed, list) else set()
    model = result.get("model")
    status_code = result.get("status_code")
    return (
        result.get("ok") is True
        and isinstance(model, str)
        and model in {"vulcan-fast", "vulcan-general", "vulcan-code"}
        and model in listed_models
        and _trace_value_failure("trace_id", result.get("trace_id")) == ""
        and isinstance(status_code, int)
        and 200 <= status_code < 300
        and result.get("response_model") == model
        and result.get("finish_reason") == "stop"
        and str(result.get("response_text") or "").strip().lower() == "gateway ok"
    )


def _acceptance_trace(evidence_by_id: dict[str, dict[str, Any]], acceptance_id: str, field: str) -> str:
    evidence = evidence_by_id.get(acceptance_id)
    payload = evidence.get("evidence") if isinstance(evidence, dict) and isinstance(evidence.get("evidence"), dict) else {}
    return str(payload.get(field) or "")


def _tool_acceptance_trace_reuse_failure(
    requirement_id: str,
    payload: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> str:
    field = TOOL_ACCEPTANCE_TRACE_FIELDS.get(requirement_id)
    if not field:
        return ""
    current_trace = str(payload.get(field) or "")
    if not current_trace:
        return ""
    for other_id, other_field in TOOL_ACCEPTANCE_TRACE_FIELDS.items():
        if other_id == requirement_id:
            continue
        if _acceptance_trace(evidence_by_id, other_id, other_field) == current_trace:
            return f"{field} must be distinct from {other_id} trace."
    return ""


def _is_iso_date(value: str) -> bool:
    if len(value) != 10:
        return False
    try:
        datetime.fromisoformat(value + "T00:00:00+00:00")
    except ValueError:
        return False
    return bool(value)


def _is_saturday(value: str) -> bool:
    try:
        return datetime.fromisoformat(value + "T00:00:00+00:00").weekday() == 5
    except ValueError:
        return False


def _backend_is_redacted_local_gateway(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        return False
    if hostname in {"atlas-loopback", "vulcan-tailnet", "litellm", "vulcan"}:
        return True
    if hostname in {"atlas-private", "atlas-local", "litellm-private", "vulcan-private"}:
        return True
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return False


def _reboot_window_failure(value: str) -> str:
    if "/" not in value:
        return "reboot_window must include start/end timestamps."
    start_text, end_text = value.split("/", 1)
    try:
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_text.replace("Z", "+00:00"))
    except ValueError:
        return "reboot_window timestamps must be ISO timestamps."
    if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
        return "reboot_window timestamps must include timezone offsets."
    if end <= start:
        return "reboot_window end must be after start."
    now = datetime.now(timezone.utc)
    if start.astimezone(timezone.utc) > now or end.astimezone(timezone.utc) > now:
        return "reboot_window must not be in the future."
    return ""


def _home_assistant_domain_redaction_ok(value: str) -> bool:
    domain = value.removeprefix("domain:")
    return bool(domain) and domain.replace("_", "").isalnum()


def _safe_local_identifier(value: str) -> bool:
    text = value.strip()
    if not text or text in {".", ".."}:
        return False
    return all(character.isalnum() or character in "._-" for character in text)


def _captured_at_failure(value: Any) -> str:
    if not _present(value):
        return ""
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "captured_at must be an ISO timestamp."
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "captured_at must include a timezone offset."
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        return "captured_at must not be in the future."
    return ""


def _trace_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field, value in payload.items():
        if field in TRACE_EVIDENCE_FIELDS or field.endswith("_trace_id"):
            failure = _trace_value_failure(field, value)
            if failure:
                failures.append(failure)
        elif field.endswith("_trace_ids"):
            if not isinstance(value, list):
                failures.append(f"{field} must be a list.")
                continue
            for item in value:
                failure = _trace_value_failure(field, item)
                if failure:
                    failures.append(failure)
                    break
    return failures


def _trace_value_failure(field: str, value: Any) -> str:
    if not _present(value):
        return ""
    if not isinstance(value, str):
        return f"{field} must be a string."
    text = str(value).strip()
    if "..." in text:
        return f"{field} must not use placeholder ellipses."
    if not text.startswith("trace-") and not text.startswith("freyja6-"):
        return f"{field} must use a Freyja validation trace prefix."
    return ""


def _hash_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        return text.split(":", 1)[1]
    return text


def _hash_has_placeholder(value: Any) -> bool:
    return "..." in str(value or "")


def _hash_is_sha256(value: Any) -> bool:
    text = _hash_value(value)
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text.lower())


def _container_is_ok(status: str) -> bool:
    lowered = status.lower()
    if any(marker in lowered for marker in ("exited", "dead", "created", "paused", "restarting", "not running", "unhealthy")):
        return False
    return lowered in {"running", "healthy", "up"} or lowered.startswith("running ") or "running (" in lowered


def _next_actions(
    scaffold: dict[str, Any],
    evidence_contract: dict[str, Any],
    acceptance: list[dict[str, Any]],
    evidence_path: Path,
    secrets_detected: bool,
) -> list[str]:
    if not scaffold["ok"]:
        return ["Fix Freyja 6 scaffold failures before live validation."]
    if evidence_contract["status"] == "fail":
        return [f"Fix the live evidence file contract in {evidence_path}."]
    if secrets_detected:
        return [f"Remove secrets from {evidence_path}; store only redacted IDs, trace IDs, and summaries."]
    missing = [item for item in acceptance if item["status"] != "complete"]
    if not missing:
        return ["Repeat the full live acceptance run before considering migration."]
    first = missing[0]
    return [
        "Start the Freyja 6 compose stack on Atlas with a dedicated Discord test channel.",
        f"Capture live evidence for {first['id']}: {first['description']}",
        f"Record redacted evidence in {evidence_path}.",
    ]


def _evidence_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = payload.get("acceptance")
    if isinstance(raw, list):
        return {str(item["id"]): item for item in raw if isinstance(item, dict) and item.get("id")}
    if isinstance(raw, dict):
        return {str(key): {"id": str(key), **value} for key, value in raw.items() if isinstance(value, dict)}
    return {}


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {"_load_failure": "Live evidence file must not be a symlink."}
    if path.exists() and not path.is_file():
        return {"_load_failure": "Live evidence file must be a regular file."}
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_load_failure": "Live evidence file must contain valid JSON."}
    if not isinstance(payload, dict):
        return {"_load_failure": "Live evidence file must be a JSON object."}
    return payload


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-acceptance-status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "incomplete",
        "complete": False,
        "error": error,
    }


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _contains_secret_marker(value: Any, *, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if any(marker.strip() in lowered_key for marker in SECRET_MARKERS):
                return True
            if _contains_secret_marker(item, path=(*path, lowered_key)):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_marker(item, path=path) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in SECRET_MARKERS)
    return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = _error_report(output_failure) if output_failure else build_status(args.evidence)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
