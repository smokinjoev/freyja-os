from pathlib import Path
import importlib.util
import json
import subprocess
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}


def _option_value(cmd: list[str], option: str) -> str:
    index = cmd.index(option)
    return cmd[index + 1]


def _write_cmd_output_report(cmd: list[str], payload: dict) -> None:
    output = Path(_option_value(cmd, "--output"))
    output.parent.mkdir(parents=True, exist_ok=True)
    versioned_payload = {"schema_version": "1.0", "timestamp": "2026-09-19T00:00:00+00:00", **payload}
    output.write_text(json.dumps(versioned_payload) + "\n", encoding="utf-8")


def _complete_acceptance_cmd_payload(cmd: list[str]) -> dict:
    payload = _complete_acceptance_status_payload()
    payload["evidence"] = _option_value(cmd, "--evidence")
    return payload


def _load_acceptance_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-acceptance-status.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_litellm_smoke_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-litellm-smoke.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_tool_smoke_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-tool-smoke.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_discord_smoke_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-discord-smoke.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_calendar_write_smoke_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-calendar-write-smoke.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_restart_evidence_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-restart-evidence.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_prepare_restart_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-prepare-restart-evidence.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_bootstrap_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-bootstrap-atlas.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_preflight_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-atlas-preflight.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_scaffold_verifier_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/verify-freyja6-scaffold.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_env_audit_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-env-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_hermes_image_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-hermes-image.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_hermes_contract_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-hermes-contract.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_model_privacy_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-model-privacy-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gateway_isolation_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-gateway-isolation-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_memory_boundary_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-memory-boundary-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_messaging_gateway_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-messaging-gateway-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_terminal_safety_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-terminal-safety-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_filesystem_boundary_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-filesystem-boundary-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_mcp_boundary_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-mcp-boundary-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_coding_workflow_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-coding-workflow-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_schedule_boundary_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-schedule-boundary-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_calendar_boundary_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-calendar-boundary-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_home_assistant_boundary_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-home-assistant-boundary-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_schedule_smoke_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-schedule-smoke.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_live_bundle_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-live-validation-bundle.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_stack_status_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-stack-status.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_log_audit_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-log-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_preservation_audit_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-preservation-audit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migration_readiness_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/freyja6-migration-readiness.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _complete_acceptance_status_payload() -> dict:
    acceptance_ids = [
        "discord_reply",
        "restart_identity_session",
        "remember_fact",
        "litellm_to_vulcan",
        "model_switch",
        "approved_file_read",
        "safe_terminal",
        "mcp_tool",
        "calendar_read",
        "calendar_create_event",
        "home_assistant_query",
        "coding_workflow",
        "atlas_reboot_return",
    ]
    evidence_fields_by_id = {
        "discord_reply": ["discord_channel_id_redacted", "message_trace_id", "reply_trace_id", "verification_method"],
        "restart_identity_session": ["restart_trace_id", "identity_before", "identity_after", "session_restored"],
        "remember_fact": ["stored_fact_label", "recall_trace_id", "memory_provider"],
        "litellm_to_vulcan": ["litellm_request_id", "model", "response_model", "vulcan_backend"],
        "model_switch": ["models_tested", "response_models", "gateway_trace_ids"],
        "approved_file_read": ["approved_path", "tool_trace_id", "bytes_read"],
        "safe_terminal": ["command", "tool_trace_id", "exit_code", "working_dir"],
        "mcp_tool": ["server", "tool", "tool_trace_id", "status_code"],
        "calendar_read": ["calendar_name_redacted", "tool_trace_id", "status_code"],
        "calendar_create_event": ["event_title", "event_date", "tool_trace_id", "created_event_id"],
        "home_assistant_query": ["entity_id_redacted", "tool_trace_id", "states_count"],
        "coding_workflow": ["executor", "handoff_trace_id", "result_summary", "status_keys"],
        "atlas_reboot_return": ["reboot_window", "container_status_after", "discord_reply_after_reboot", "discord_reply_after_reboot_verification"],
    }
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-acceptance-status",
        "timestamp": "2026-09-19T00:00:00+00:00",
        "status": "complete",
        "complete": True,
        "evidence": "certification/reports/freyja6-live-evidence.json",
        "remaining_acceptance": [],
        "secrets_detected": False,
        "evidence_contract": {"status": "pass"},
        "acceptance": [
            {
                "id": item_id,
                "status": "complete",
                "required_evidence": evidence_fields_by_id[item_id],
                "required_metadata": ["captured_at", "source"],
                "metadata": {
                    "captured_at": "2026-09-19T00:00:00+00:00",
                    "source": {
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
                    }[item_id],
                },
                "present_evidence": evidence_fields_by_id[item_id],
                "missing_evidence": [],
                "missing_metadata": [],
                "semantic_failures": [],
            }
            for item_id in acceptance_ids
        ],
    }


def _passing_preservation_payload() -> dict:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-preservation-audit",
        "ok": True,
        "status": "pass",
        "secrets_included": False,
        "checks": [
            {"id": "source_files", "status": "pass"},
            {"id": "guardrails", "status": "pass"},
            {"id": "phase_one_agent_scope", "status": "pass"},
            {"id": "compose_side_by_side", "status": "pass"},
            {"id": "legacy_runtime_coupling", "status": "pass"},
            {"id": "legacy_evidence_present", "status": "pass"},
        ],
        "failures": [],
    }


def _complete_live_bundle_payload(timestamp: str, *, evidence: str | None = None, run_id: str | None = None) -> dict:
    steps = [
        "preservation_audit",
        "env_audit",
        "hermes_contract",
        "model_privacy_audit",
        "gateway_isolation_audit",
        "memory_boundary_audit",
        "messaging_gateway_audit",
        "terminal_safety_audit",
        "filesystem_boundary_audit",
        "mcp_boundary_audit",
        "coding_workflow_audit",
        "schedule_boundary_audit",
        "calendar_boundary_audit",
        "home_assistant_boundary_audit",
        "hermes_image",
        "atlas_preflight",
        "bootstrap_atlas",
        "schedule_smoke",
        "stack_status",
        "discord_reply",
        "litellm_vulcan",
        "tool_smoke",
        "calendar_write",
        "restart_evidence",
        "log_audit",
        "acceptance_status",
    ]
    reportless_steps = {"discord_reply", "litellm_vulcan", "tool_smoke", "calendar_write", "restart_evidence"}
    results = []
    for step in steps:
        item = {
            "id": step,
            "required": True,
            "status": "pass",
            "exit_code": 0,
            "command": [".venv/bin/python", _migration_bundle_script_for_step(step)],
            "started_at": timestamp,
            "finished_at": timestamp,
        }
        if step not in reportless_steps:
            item["report"] = f"bundle-{step.replace('_', '-')}.json"
        results.append(item)
    payload = {
        "schema_version": "1.0",
        "report_type": "freyja6-live-validation-bundle",
        "run_id": run_id or f"freyja6-live-{uuid.uuid5(uuid.NAMESPACE_URL, timestamp)}",
        "timestamp": timestamp,
        "env_file": "deploy/compose/freyja6/.env",
        "log_root": "freyja6/logs",
        "live": True,
        "complete": True,
        "status": "complete",
        "evidence": evidence or "certification/reports/freyja6-live-evidence.json",
        "failed_required": [],
        "skipped_required": [],
        "results": results,
    }
    return payload


def _migration_bundle_script_for_step(step: str) -> str:
    overrides = {
        "discord_reply": "scripts/freyja6-discord-smoke.py",
        "litellm_vulcan": "scripts/freyja6-litellm-smoke.py",
        "tool_smoke": "scripts/freyja6-tool-smoke.py",
        "calendar_write": "scripts/freyja6-calendar-write-smoke.py",
        "restart_evidence": "scripts/freyja6-restart-evidence.py",
    }
    return overrides.get(step, f"scripts/freyja6-{step.replace('_', '-')}.py")


def _write_live_bundle(path: Path, payload: dict) -> None:
    timestamp = payload.get("timestamp")
    for item in payload.get("results", []):
        report = item.get("report") if isinstance(item, dict) else None
        step_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(report, str) or not isinstance(step_id, str):
            continue
        default_report_name = f"bundle-{step_id.replace('_', '-')}.json"
        report_path = Path(report)
        if report_path.name == default_report_name:
            item["report"] = str(report_path.with_name(f"{path.stem}-{step_id.replace('_', '-')}.json"))
            report = item["report"]
            report_path = Path(report)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    for item in payload.get("results", []):
        report = item.get("report") if isinstance(item, dict) else None
        step_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(report, str) or not isinstance(step_id, str):
            continue
        report_path = Path(report)
        if report_path.parent == Path("certification/reports"):
            side_report = ROOT / report_path
        else:
            side_report = path.parent / report_path.name
        side_report.parent.mkdir(parents=True, exist_ok=True)
        if step_id == "acceptance_status":
            side_payload = _complete_acceptance_status_payload()
            side_payload["timestamp"] = timestamp
            side_payload["evidence"] = payload.get("evidence", side_payload["evidence"])
        else:
            side_payload = {
                "schema_version": "1.0",
                "report_type": f"freyja6-{step_id.replace('_', '-')}",
                "timestamp": timestamp,
                "status": "pass",
                "ok": True,
            }
        side_report.write_text(
            json.dumps(side_payload) + "\n",
            encoding="utf-8",
        )


def _write_complete_log_audit_logs(path: Path) -> None:
    acceptance_source_by_id = {
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
    tool_entries = [
        ("trace-file", "filesystem.read", "freyja6-tool-smoke", None),
        ("trace-terminal", "terminal.safe_command", "freyja6-tool-smoke", None),
        ("trace-mcp", "status.check", "freyja6-tool-smoke", 200),
        ("trace-calendar-read", "calendar.list_events", "freyja6-tool-smoke", 200),
        ("trace-calendar-create", "calendar.create_event", "freyja6-calendar-write-smoke", 200),
        ("trace-home", "home_assistant.list_states", "freyja6-tool-smoke", 200),
        ("trace-code", "opencode.status", "freyja6-tool-smoke", 200),
    ]
    model_entries = [
        ("trace-vulcan", "vulcan-general", "freyja6-litellm-smoke"),
        ("trace-switch-fast", "vulcan-fast", "freyja6-litellm-smoke"),
        ("trace-switch-code", "vulcan-code", "freyja6-litellm-smoke"),
    ]
    acceptance_entries = [
        ("trace-discord", "discord_reply"),
        ("trace-restart", "restart_identity_session"),
        ("trace-memory", "remember_fact"),
        ("trace-vulcan", "litellm_to_vulcan"),
        ("trace-switch-fast", "model_switch"),
        ("trace-file", "approved_file_read"),
        ("trace-terminal", "safe_terminal"),
        ("trace-mcp", "mcp_tool"),
        ("trace-calendar-read", "calendar_read"),
        ("trace-calendar-create", "calendar_create_event"),
        ("trace-home", "home_assistant_query"),
        ("trace-code", "coding_workflow"),
        ("trace-reboot-discord", "atlas_reboot_return"),
    ]
    (path / "freyja-test-tools.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": f"2026-09-19T00:{index:02d}:00+00:00",
                    "event": "tool_call",
                    "trace_id": trace_id,
                    "tool": tool,
                    "status": "ok",
                    "source": source,
                    **({"status_code": status_code} if status_code is not None else {}),
                }
            )
            for index, (trace_id, tool, source, status_code) in enumerate(tool_entries)
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "freyja-test-model-calls.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": f"2026-09-19T00:{index:02d}:30+00:00",
                    "event": "model_call",
                    "trace_id": trace_id,
                    "model": model,
                    "status": "ok",
                    "status_code": 200,
                    "source": source,
                }
            )
            for index, (trace_id, model, source) in enumerate(model_entries)
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": f"2026-09-19T00:{index + 10:02d}:00+00:00",
                    "event": "acceptance",
                    "trace_id": trace_id,
                    "acceptance_id": acceptance_id,
                    "status": "ok",
                    "source": acceptance_source_by_id[acceptance_id],
                }
            )
            for index, (trace_id, acceptance_id) in enumerate(acceptance_entries)
        )
        + "\n",
        encoding="utf-8",
    )


def test_freyja6_phase_one_has_only_freyja_test_agent() -> None:
    config = _yaml("config/freyja6/freyja-test.yaml")

    assert [agent["id"] for agent in config["agents"]] == ["freyja-test"]
    assert config["future_agents"] == ["Freyja", "Cloyd", "Benedict", "Agent 44", "Agent Smith"]


def test_freyja6_future_agent_isolation_manifest_reserves_unique_boundaries() -> None:
    isolation = _yaml("config/freyja6/future-agent-isolation.yaml")
    future_agents = isolation["future_agents"]

    assert isolation["phase"] == "reservation_only"
    assert isolation["live_agents"] == ["freyja-test"]
    assert [agent["display_name"] for agent in future_agents] == ["Freyja", "Cloyd", "Benedict", "Agent 44", "Agent Smith"]
    assert {agent["status"] for agent in future_agents} == {"reserved"}
    for field in ("slug", "identity_file", "sessions_dir", "private_memory_dir", "credentials_env_prefix", "mcp_token_env"):
        values = [agent[field] for agent in future_agents]
        assert len(values) == len(set(values))
    token_envs = [agent["messaging"]["token_env"] for agent in future_agents]
    channel_envs = [agent["messaging"]["channel_env"] for agent in future_agents]
    assert len(token_envs) == len(set(token_envs))
    assert len(channel_envs) == len(set(channel_envs))
    for agent in future_agents:
        root = f"/var/lib/hermes/agents/{agent['slug']}/"
        assert agent["identity_file"].startswith(root)
        assert agent["sessions_dir"].startswith(root)
        assert agent["private_memory_dir"].startswith(root)
        assert agent["shared_memory"] == "authorized_household_only"


def test_freyja6_agent_routes_models_through_litellm() -> None:
    config = _yaml("config/freyja6/freyja-test.yaml")
    agent = config["agents"][0]

    assert agent["models"]["gateway_base_url"] == "http://litellm:4000/v1"
    assert agent["models"]["allowed_models"] == ["vulcan-fast", "vulcan-general", "vulcan-code"]
    assert agent["memory"]["provider"] == "hermes-native"
    assert agent["memory"]["private_dir"] == "/var/lib/hermes/agents/freyja-test/memory/private"
    assert agent["memory"]["shared_household_dir"] is None
    assert agent["identity_file"] == "/var/lib/hermes/agents/freyja-test/identity.md"
    assert agent["sessions_dir"] == "/var/lib/hermes/agents/freyja-test/sessions"
    assert agent["tools"]["filesystem"]["approved_roots"] == ["/workspace/approved"]
    assert agent["tools"]["filesystem"]["mode"] == "read-only"
    assert agent["tools"]["terminal"]["enabled"] is True
    assert agent["tools"]["terminal"]["safe_commands"] == ["pwd", "date", "whoami", "ls", "rg"]
    assert agent["messaging"]["gateway"] == "discord"
    assert agent["messaging"]["channel_scope"] == "dedicated-test-channel"
    assert agent["messaging"]["credentials_source"] == "environment"
    assert agent["messaging"]["env"] == {
        "token": "FREYJA6_DISCORD_BOT_TOKEN",
        "channel_id": "FREYJA6_DISCORD_CHANNEL_ID",
    }
    assert agent["tools"]["mcp"]["host_config_source"] == "config/freyja6/mcp/freyja-test.json"
    assert agent["logging"] == {
        "tool_log": "/var/log/freyja6/freyja-test-tools.jsonl",
        "model_log": "/var/log/freyja6/freyja-test-model-calls.jsonl",
        "acceptance_log": "/var/log/freyja6/freyja-test-acceptance.jsonl",
    }


def test_freyja6_compose_is_side_by_side_and_pinned() -> None:
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    services = compose["services"]

    assert set(services) == {"litellm-db", "litellm", "hermes-freyja-test"}
    assert services["litellm"]["image"] == "${LITELLM_IMAGE}"
    assert services["hermes-freyja-test"]["image"] == "${HERMES_AGENT_IMAGE}"
    assert services["litellm"]["ports"] == ["127.0.0.1:4600:4000"]
    assert services["hermes-freyja-test"]["labels"]["freyja.migration"] == "disabled"
    volumes = services["hermes-freyja-test"]["volumes"]
    assert "../../../config/freyja6/mcp/freyja-test.json:/etc/hermes/mcp/freyja-test.json:ro" in volumes
    assert "../../../config/freyja6/schedules.yaml:/etc/hermes/schedules/freyja-test.yaml:ro" in volumes


def test_freyja6_env_pins_verified_litellm_and_local_hermes_image() -> None:
    env = (ROOT / "deploy/compose/freyja6/.env.example").read_text(encoding="utf-8")

    assert "LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.89.0" in env
    assert "HERMES_AGENT_VERSION=v2026.9.14" in env
    assert "HERMES_AGENT_IMAGE=hermes-agent-local:${HERMES_AGENT_VERSION}" in env
    assert "HERMES_AGENT_SOURCE=/opt/hermes-agent" in env


def test_freyja6_scaffold_verifier_rejects_symlinked_source_file_before_loading(tmp_path, monkeypatch, capsys) -> None:
    module = _load_scaffold_verifier_module("verify_freyja6_scaffold_symlink_source")
    real_config = tmp_path / "real-freyja-test.yaml"
    real_config.write_text((ROOT / "config/freyja6/freyja-test.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    agent_config = tmp_path / "freyja-test.yaml"
    agent_config.symlink_to(real_config)
    sources = dict(module.SOURCE_FILES)
    sources["agent_config"] = agent_config

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("YAML should not be loaded for unsafe source files")))
    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    exit_code = module.main(sources)

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert rendered["ok"] is False
    assert rendered["failures"] == [f"Scaffold source file must not be a symlink: agent_config ({agent_config})."]


def test_freyja6_scaffold_verifier_rejects_directory_source_file_before_loading(tmp_path, monkeypatch, capsys) -> None:
    module = _load_scaffold_verifier_module("verify_freyja6_scaffold_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()
    sources = dict(module.SOURCE_FILES)
    sources["compose"] = compose

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("YAML should not be loaded for unsafe source files")))
    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    exit_code = module.main(sources)

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert rendered["ok"] is False
    assert rendered["failures"] == [f"Scaffold source file must be a regular file: compose ({compose})."]


def test_freyja6_litellm_exposes_vulcan_aliases_only() -> None:
    config = _yaml("deploy/compose/freyja6/litellm.config.yaml")
    names = [entry["model_name"] for entry in config["model_list"]]

    assert names == ["vulcan-fast", "vulcan-general", "vulcan-code"]
    expected_models = {
        "vulcan-fast": "ollama/qwen2.5:7b",
        "vulcan-general": "ollama/qwen3.8:27b",
        "vulcan-code": "ollama/qwen3-coder-next:q4_K_M",
    }
    for entry in config["model_list"]:
        params = entry["litellm_params"]
        assert params["model"] == expected_models[entry["model_name"]]
        assert params["api_base"] == "os.environ/VULCAN_OLLAMA_BASE_URL"


def test_freyja6_acceptance_status_starts_incomplete_without_live_evidence(tmp_path) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status")

    report = module.build_status(tmp_path / "missing-live-evidence.json")

    assert report["complete"] is False
    assert report["status"] == "incomplete"
    assert report["scaffold"]["ok"] is True
    assert "config/freyja6/bootstrap/identity.md" in report["scaffold"]["source_files"]
    assert report["remaining_acceptance"] == [
        "discord_reply",
        "restart_identity_session",
        "remember_fact",
        "litellm_to_vulcan",
        "model_switch",
        "approved_file_read",
        "safe_terminal",
        "mcp_tool",
        "calendar_read",
        "calendar_create_event",
        "home_assistant_query",
        "coding_workflow",
        "atlas_reboot_return",
    ]


def test_freyja6_acceptance_status_rejects_secret_markers(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "evidence": {
                "discord_channel_id_redacted": "ok",
                "message_trace_id": "trace-1",
                "reply_trace_id": "trace-2",
                "bot_token": "do-not-store"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_secret")

    report = module.build_status(evidence)

    assert report["secrets_detected"] is True
    assert report["complete"] is False


def test_freyja6_acceptance_status_requires_live_evidence_contract(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "0.9",
          "report_type": "notes",
          "acceptance": {}
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_contract")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert report["evidence_contract"]["failures"] == [
        "Live evidence report_type must be freyja6-live-evidence.",
        "Live evidence schema_version must be 1.0.",
    ]
    assert report["next_actions"] == [f"Fix the live evidence file contract in {evidence}."]


def test_freyja6_acceptance_status_rejects_symlinked_live_evidence(tmp_path) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence file must not be a symlink." in report["evidence_contract"]["failures"]
    assert report["next_actions"] == [f"Fix the live evidence file contract in {evidence}."]


def test_freyja6_acceptance_status_rejects_directory_live_evidence(tmp_path) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status_directory_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.mkdir()

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence file must be a regular file." in report["evidence_contract"]["failures"]
    assert report["next_actions"] == [f"Fix the live evidence file contract in {evidence}."]


def test_freyja6_acceptance_status_rejects_malformed_live_evidence_json(tmp_path) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status_malformed_evidence_json")
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":', encoding="utf-8")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence file must contain valid JSON." in report["evidence_contract"]["failures"]
    assert report["next_actions"] == [f"Fix the live evidence file contract in {evidence}."]


def test_freyja6_acceptance_status_rejects_non_object_live_evidence_json(tmp_path) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status_non_object_evidence_json")
    evidence = tmp_path / "evidence.json"
    evidence.write_text("[]\n", encoding="utf-8")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence file must be a JSON object." in report["evidence_contract"]["failures"]
    assert report["next_actions"] == [f"Fix the live evidence file contract in {evidence}."]


def test_freyja6_acceptance_status_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status_symlink_output")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    real_output = tmp_path / "real-acceptance.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "acceptance.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--evidence", str(evidence), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["complete"] is False
    assert rendered["status"] == "incomplete"
    assert rendered["error"] == "output path must not be a symlink: acceptance.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_acceptance_status_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_acceptance_module("freyja6_acceptance_status_directory_output")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    output = tmp_path / "acceptance-dir"
    output.mkdir()

    exit_code = module.main(["--evidence", str(evidence), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["complete"] is False
    assert rendered["status"] == "incomplete"
    assert rendered["error"] == "output path must be a regular file: acceptance-dir"


def test_freyja6_acceptance_status_rejects_unexpected_live_evidence_acceptance_ids(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": {
            "future_agent_ready": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "manual",
              "evidence": {
                "trace_id": "trace-future"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_unexpected_acceptance")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert report["evidence_contract"]["failures"] == [
        "Live evidence acceptance contains unexpected ids: future_agent_ready."
    ]


def test_freyja6_acceptance_status_rejects_duplicate_live_evidence_acceptance_ids(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": [
            {
              "id": "discord_reply",
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            },
            {
              "id": "discord_reply",
              "status": "complete",
              "captured_at": "2026-09-19T00:01:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message-2",
                "reply_trace_id": "trace-reply-2",
                "verification_method": "discord-api"
              }
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_duplicate_acceptance")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence acceptance contains duplicate ids: discord_reply." in report["evidence_contract"]["failures"]


def test_freyja6_acceptance_status_rejects_mismatched_object_acceptance_id(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": {
            "discord_reply": {
              "id": "model_switch",
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_mismatched_object_acceptance_id")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence acceptance entry discord_reply id must match its object key." in report["evidence_contract"]["failures"]


def test_freyja6_acceptance_status_rejects_malformed_live_evidence_acceptance_entries(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": [
            "not-an-object",
            {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_malformed_acceptance")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence acceptance entry 1 must be an object." in report["evidence_contract"]["failures"]
    assert "Live evidence acceptance entry 2 must include an id." in report["evidence_contract"]["failures"]


def test_freyja6_acceptance_status_rejects_non_object_acceptance_evidence_payloads(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": []
            },
            "safe_terminal": {
              "id": "safe_terminal",
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": "terminal-ok"
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_non_object_acceptance_evidence")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence acceptance entry discord_reply evidence must be an object." in report["evidence_contract"]["failures"]
    assert "Live evidence acceptance entry safe_terminal evidence must be an object." in report["evidence_contract"]["failures"]


def test_freyja6_acceptance_status_rejects_non_object_list_acceptance_evidence_payload(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": [
            {
              "id": "discord_reply",
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_non_object_list_acceptance_evidence")

    report = module.build_status(evidence)

    assert report["complete"] is False
    assert report["evidence_contract"]["status"] == "fail"
    assert "Live evidence acceptance entry discord_reply evidence must be an object." in report["evidence_contract"]["failures"]


def test_freyja6_acceptance_status_requires_evidence_metadata(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "evidence": {
                "discord_channel_id_redacted": "ok",
                "message_trace_id": "trace-1",
                "reply_trace_id": "trace-2",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_metadata")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert discord["missing_evidence"] == []
    assert discord["missing_metadata"] == ["captured_at", "source"]


def test_freyja6_acceptance_status_rejects_non_string_metadata(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": 44,
              "source": {"helper": "freyja6-discord-smoke"},
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_non_string_metadata")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert "captured_at must be a string." in discord["semantic_failures"]
    assert "source must be a string." in discord["semantic_failures"]


def test_freyja6_acceptance_status_requires_explicit_complete_status(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "discord_reply": {
              "status": "pending",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-...1234",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_explicit_complete")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert discord["missing_evidence"] == []
    assert discord["missing_metadata"] == []
    assert discord["metadata"] == {
        "captured_at": "2026-09-19T00:00:00+00:00",
        "source": "freyja6-discord-smoke",
    }
    assert discord["semantic_failures"] == []


def test_freyja6_acceptance_status_rejects_weak_discord_reply_evidence(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "raw-channel",
                "message_trace_id": "trace-same",
                "reply_trace_id": "trace-same",
                "verification_method": "unknown"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_discord_semantics")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert "discord_channel_id_redacted must be redacted." in discord["semantic_failures"]
    assert "message_trace_id and reply_trace_id must be distinct." in discord["semantic_failures"]
    assert "verification_method must be discord-api for final acceptance." in discord["semantic_failures"]


def test_freyja6_acceptance_status_rejects_manual_discord_for_final_acceptance(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-...1234",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "manual-confirmed"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_discord_manual_final")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert "verification_method must be discord-api for final acceptance." in discord["semantic_failures"]


def test_freyja6_acceptance_status_requires_discord_acceptance_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_discord_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "ok": true,
            "channel_id_redacted": "discord-channel-...1234",
            "message_trace_id": "trace-message",
            "reply_trace_id": "trace-reply",
            "verification": "discord-api",
            "message_from_user": true,
            "reply_from_bot": true,
            "reply_references_message": true,
            "chronological": true
          },
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-...1234",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-stale-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_discord_producer_trace")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert "reply_trace_id must match last_discord_smoke.reply_trace_id." in discord["semantic_failures"]


def test_freyja6_acceptance_status_rejects_type_corrupted_discord_producer_values(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-live-evidence",
                "last_discord_smoke": {
                    "timestamp": "2026-09-19T00:00:00+00:00",
                    "ok": True,
                    "channel_id_redacted": 1234,
                    "message_trace_id": "trace-message",
                    "reply_trace_id": ["trace-reply"],
                    "verification": "discord-api",
                    "message_from_user": True,
                    "reply_from_bot": True,
                    "reply_references_message": True,
                    "chronological": True,
                },
                "acceptance": {
                    "discord_reply": {
                        "status": "complete",
                        "captured_at": "2026-09-19T00:00:00+00:00",
                        "source": "freyja6-discord-smoke",
                        "evidence": {
                            "discord_channel_id_redacted": "1234",
                            "message_trace_id": "trace-message",
                            "reply_trace_id": "['trace-reply']",
                            "verification_method": "discord-api",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_discord_producer_types")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert "discord_channel_id_redacted must match last_discord_smoke.channel_id_redacted." in discord["semantic_failures"]


def test_freyja6_acceptance_status_requires_api_verified_discord_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_discord_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "ok": true,
            "channel_id_redacted": "discord-channel-...1234",
            "message_trace_id": "trace-message",
            "reply_trace_id": "trace-reply",
            "verification": "discord-api",
            "message_from_user": true,
            "reply_from_bot": false,
            "reply_references_message": true,
            "chronological": true
          },
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-...1234",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_discord_producer_api")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert discord["status"] == "partial"
    assert "discord_reply must reference an API-verified last_discord_smoke result." in discord["semantic_failures"]


def test_freyja6_acceptance_status_rejects_semantically_weak_evidence(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "restart_identity_session": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "restart_trace_id": "trace-restart",
                "identity_before": "sha256:before",
                "identity_after": "sha256:after",
                "session_restored": false
              }
            },
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-general"],
                "gateway_trace_ids": ["trace-one"]
              }
            },
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "rm",
                "tool_trace_id": "trace-terminal",
                "exit_code": 1
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_semantics")

    report = module.build_status(evidence)

    restart = next(item for item in report["acceptance"] if item["id"] == "restart_identity_session")
    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    assert restart["status"] == "partial"
    assert "session_restored must be true." in restart["semantic_failures"]
    assert "identity hashes must be sha256-prefixed 64-character hex values." in restart["semantic_failures"]
    assert "identity_before and identity_after must match." in restart["semantic_failures"]
    assert model_switch["status"] == "partial"
    assert "models_tested must contain at least two distinct approved aliases." in model_switch["semantic_failures"]
    assert "gateway_trace_ids must contain at least two traces." in model_switch["semantic_failures"]
    assert terminal["status"] == "partial"
    assert "command must be in the Freyja 6 safe terminal allowlist." in terminal["semantic_failures"]
    assert "exit_code must be 0." in terminal["semantic_failures"]


def test_freyja6_acceptance_status_rejects_matching_fake_identity_hashes(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "restart_identity_session": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "restart_trace_id": "trace-restart",
                "identity_before": "sha256:same",
                "identity_after": "sha256:same",
                "session_restored": true
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_fake_hash")

    report = module.build_status(evidence)

    restart = next(item for item in report["acceptance"] if item["id"] == "restart_identity_session")
    assert restart["status"] == "partial"
    assert "identity hashes must be sha256-prefixed 64-character hex values." in restart["semantic_failures"]


def test_freyja6_acceptance_status_rejects_weak_tool_acceptance_values(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "approved_file_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "approved_path": "../private.txt",
                "tool_trace_id": "trace-file",
                "bytes_read": 12
              }
            },
            "mcp_tool": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "server": "freyja-core-gateway",
                "tool": "calendar.delete_event",
                "tool_trace_id": "trace-mcp",
                "status_code": 200
              }
            },
            "calendar_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "calendar_name_redacted": "family-private-calendar",
                "tool_trace_id": "trace-calendar",
                "status_code": 200
              }
            },
            "home_assistant_query": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "entity_id_redacted": "domain:sensor.kitchen_motion",
                "tool_trace_id": "trace-home",
                "states_count": 1
              }
            },
            "coding_workflow": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "executor": "opencode",
                "handoff_trace_id": "trace-coding",
                "result_summary": "shell completed",
                "status_keys": ["alias", "state"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_tool_value_semantics")

    report = module.build_status(evidence)

    approved = next(item for item in report["acceptance"] if item["id"] == "approved_file_read")
    mcp = next(item for item in report["acceptance"] if item["id"] == "mcp_tool")
    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_read")
    home = next(item for item in report["acceptance"] if item["id"] == "home_assistant_query")
    coding = next(item for item in report["acceptance"] if item["id"] == "coding_workflow")
    assert "approved_path must be under approved-files." in approved["semantic_failures"]
    assert "tool must be status.check." in mcp["semantic_failures"]
    assert "calendar_name_redacted must be configured-calendar." in calendar["semantic_failures"]
    assert "entity_id_redacted must be a redacted Home Assistant domain." in home["semantic_failures"]
    assert "result_summary must match the Freyja Core OpenCode status summary." in coding["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_redacted_scalar_values(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "approved_file_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "approved_path": 42,
                "tool_trace_id": "trace-file",
                "bytes_read": 12
              }
            },
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": ["2026-09-19"],
                "tool_trace_id": "trace-calendar-create",
                "created_event_id": "event-id-created-1"
              }
            },
            "home_assistant_query": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "entity_id_redacted": true,
                "tool_trace_id": "trace-home",
                "states_count": 1
              }
            },
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": {"start": "2026-09-19T00:00:00+00:00"},
                "container_status_after": ["running"],
                "discord_reply_after_reboot": "trace-reboot-discord",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_non_string_redacted_scalars")

    report = module.build_status(evidence)

    approved = next(item for item in report["acceptance"] if item["id"] == "approved_file_read")
    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    home = next(item for item in report["acceptance"] if item["id"] == "home_assistant_query")
    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert "approved_path must be a string." in approved["semantic_failures"]
    assert "event_date must be a string." in calendar["semantic_failures"]
    assert "entity_id_redacted must be a string." in home["semantic_failures"]
    assert "reboot_window must be a string." in reboot["semantic_failures"]
    assert "container_status_after must be a string." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_requires_distinct_tool_acceptance_traces(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "pwd",
                "tool_trace_id": "trace-shared-tool",
                "exit_code": 0,
                "working_dir": "freyja-os"
              }
            },
            "calendar_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "calendar_name_redacted": "configured-calendar",
                "tool_trace_id": "trace-shared-tool"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_tool_trace_distinct")

    report = module.build_status(evidence)

    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_read")
    assert terminal["status"] == "partial"
    assert calendar["status"] == "partial"
    assert "tool_trace_id must be distinct from calendar_read trace." in terminal["semantic_failures"]
    assert "tool_trace_id must be distinct from safe_terminal trace." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_tool_acceptance_to_match_producer_trace(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "safe_terminal": {
              "ok": true,
              "command": "pwd",
              "trace_id": "trace-terminal",
              "exit_code": 0,
              "working_dir": "freyja-os"
            }
          },
          "acceptance": {
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "pwd",
                "tool_trace_id": "trace-terminal-stale",
                "exit_code": 0,
                "working_dir": "freyja-os"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_tool_producer_trace")

    report = module.build_status(evidence)

    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    assert terminal["status"] == "partial"
    assert "tool_trace_id must match last_tool_smoke.safe_terminal.trace_id." in terminal["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_tool_producer_trace(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "safe_terminal": {
              "ok": true,
              "command": "pwd",
              "trace_id": 44,
              "exit_code": 0,
              "working_dir": "freyja-os"
            }
          },
          "acceptance": {
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "pwd",
                "tool_trace_id": "44",
                "exit_code": 0,
                "working_dir": "freyja-os"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_tool_producer_trace_type")

    report = module.build_status(evidence)

    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    assert terminal["status"] == "partial"
    assert "tool_trace_id must match last_tool_smoke.safe_terminal.trace_id." in terminal["semantic_failures"]


def test_freyja6_acceptance_status_requires_safe_terminal_working_dir_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "safe_terminal": {
              "ok": true,
              "command": "pwd",
              "trace_id": "trace-terminal",
              "exit_code": 0,
              "working_dir": "freyja-os"
            }
          },
          "acceptance": {
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "pwd",
                "tool_trace_id": "trace-terminal",
                "exit_code": 0,
                "working_dir": "tmp"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_safe_terminal_working_dir")

    report = module.build_status(evidence)

    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    assert terminal["status"] == "partial"
    assert "working_dir must be freyja-os." in terminal["semantic_failures"]
    assert "tool_trace_id must reference a verified last_tool_smoke.safe_terminal result." in terminal["semantic_failures"]


def test_freyja6_acceptance_status_requires_mcp_producer_health_object(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "core_mcp_health": "ok",
            "mcp_discovery": {
              "ok": true,
              "tool": "status.check",
              "trace_id": "trace-mcp",
              "status_code": 200
            }
          },
          "acceptance": {
            "mcp_tool": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "server": "freyja-core-gateway",
                "tool": "status.check",
                "tool_trace_id": "trace-mcp",
                "status_code": 200
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_mcp_health_object")

    report = module.build_status(evidence)

    mcp = next(item for item in report["acceptance"] if item["id"] == "mcp_tool")
    assert mcp["status"] == "partial"
    assert "tool_trace_id must reference a verified last_tool_smoke.mcp_discovery result." in mcp["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_read_status_code_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "calendar_read": {
              "ok": true,
              "tool": "calendar.list_events",
              "trace_id": "trace-calendar",
              "status_code": 200
            }
          },
          "acceptance": {
            "calendar_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "calendar_name_redacted": "configured-calendar",
                "tool_trace_id": "trace-calendar",
                "status_code": 503
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_read_status_code")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_read")
    assert calendar["status"] == "partial"
    assert "status_code must be 2xx." in calendar["semantic_failures"]
    assert "tool_trace_id must reference a verified last_tool_smoke.calendar_read result." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_approved_file_bytes_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "approved_file": {
              "ok": true,
              "path_redacted": "approved-files/smoke.txt",
              "trace_id": "trace-file",
              "bytes": 42
            }
          },
          "acceptance": {
            "approved_file_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "approved_path": "approved-files/smoke.txt",
                "tool_trace_id": "trace-file",
                "bytes_read": 12
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_approved_file_bytes")

    report = module.build_status(evidence)

    approved = next(item for item in report["acceptance"] if item["id"] == "approved_file_read")
    assert approved["status"] == "partial"
    assert "tool_trace_id must reference a verified last_tool_smoke.approved_file result." in approved["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_approved_file_producer_path(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "approved_file": {
              "ok": true,
              "path_redacted": ["approved-files/smoke.txt"],
              "trace_id": "trace-file",
              "bytes": 12
            }
          },
          "acceptance": {
            "approved_file_read": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "approved_path": "['approved-files/smoke.txt']",
                "tool_trace_id": "trace-file",
                "bytes_read": 12
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_approved_file_path_type")

    report = module.build_status(evidence)

    approved = next(item for item in report["acceptance"] if item["id"] == "approved_file_read")
    assert approved["status"] == "partial"
    assert "approved_path must be under approved-files." in approved["semantic_failures"]
    assert "tool_trace_id must reference a verified last_tool_smoke.approved_file result." in approved["semantic_failures"]


def test_freyja6_acceptance_status_requires_home_assistant_verified_producer_result(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "home_assistant_query": {
              "ok": true,
              "tool": "home_assistant.list_states",
              "domain": "sensor",
              "trace_id": "trace-home",
              "result_keys": ["ok"],
              "states_count": 0
            }
          },
          "acceptance": {
            "home_assistant_query": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "entity_id_redacted": "domain:sensor",
                "tool_trace_id": "trace-home",
                "states_count": 1
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_home_producer_verified")

    report = module.build_status(evidence)

    home = next(item for item in report["acceptance"] if item["id"] == "home_assistant_query")
    assert home["status"] == "partial"
    assert "tool_trace_id must reference a verified last_tool_smoke.home_assistant_query result." in home["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_home_assistant_producer_domain(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "home_assistant_query": {
              "ok": true,
              "tool": "home_assistant.list_states",
              "domain": ["sensor"],
              "trace_id": "trace-home",
              "result_keys": ["states"],
              "states_count": 1
            }
          },
          "acceptance": {
            "home_assistant_query": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "entity_id_redacted": "domain:['sensor']",
                "tool_trace_id": "trace-home",
                "states_count": 1
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_home_domain_type")

    report = module.build_status(evidence)

    home = next(item for item in report["acceptance"] if item["id"] == "home_assistant_query")
    assert home["status"] == "partial"
    assert "entity_id_redacted must be a redacted Home Assistant domain." in home["semantic_failures"]
    assert "tool_trace_id must reference a verified last_tool_smoke.home_assistant_query result." in home["semantic_failures"]


def test_freyja6_acceptance_status_requires_home_assistant_states_count_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "home_assistant_query": {
              "ok": true,
              "tool": "home_assistant.list_states",
              "domain": "sensor",
              "trace_id": "trace-home",
              "result_keys": ["ok", "states"],
              "states_count": 3
            }
          },
          "acceptance": {
            "home_assistant_query": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "entity_id_redacted": "domain:sensor",
                "tool_trace_id": "trace-home",
                "states_count": 1
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_home_states_count")

    report = module.build_status(evidence)

    home = next(item for item in report["acceptance"] if item["id"] == "home_assistant_query")
    assert home["status"] == "partial"
    assert "tool_trace_id must reference a verified last_tool_smoke.home_assistant_query result." in home["semantic_failures"]


def test_freyja6_acceptance_status_requires_coding_workflow_status_payload(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "coding_workflow": {
              "ok": true,
              "tool": "opencode.status",
              "trace_id": "trace-coding",
              "alias": "freyja-core-coder"
            }
          },
          "acceptance": {
            "coding_workflow": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "executor": "opencode",
                "handoff_trace_id": "trace-coding",
                "result_summary": "opencode status queried through Freyja Core",
                "status_keys": ["alias", "state"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_coding_producer_status")

    report = module.build_status(evidence)

    coding = next(item for item in report["acceptance"] if item["id"] == "coding_workflow")
    assert coding["status"] == "partial"
    assert "handoff_trace_id must reference a verified last_tool_smoke.coding_workflow result." in coding["semantic_failures"]


def test_freyja6_acceptance_status_requires_coding_workflow_status_keys_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "coding_workflow": {
              "ok": true,
              "tool": "opencode.status",
              "trace_id": "trace-coding",
              "alias": "freyja-core-coder",
              "status_payload_present": true,
              "status_keys": ["alias", "state"]
            }
          },
          "acceptance": {
            "coding_workflow": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "executor": "opencode",
                "handoff_trace_id": "trace-coding",
                "result_summary": "opencode status queried through Freyja Core",
                "status_keys": ["alias"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_coding_status_keys")

    report = module.build_status(evidence)

    coding = next(item for item in report["acceptance"] if item["id"] == "coding_workflow")
    assert coding["status"] == "partial"
    assert "handoff_trace_id must reference a verified last_tool_smoke.coding_workflow result." in coding["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_coding_workflow_status_keys(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "coding_workflow": {
              "ok": true,
              "tool": "opencode.status",
              "trace_id": "trace-coding",
              "alias": "freyja-core-coder",
              "result_summary": "opencode status queried through Freyja Core",
              "status_payload_present": true,
              "status_keys": ["alias", 44]
            }
          },
          "acceptance": {
            "coding_workflow": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "executor": "opencode",
                "handoff_trace_id": "trace-coding",
                "result_summary": "opencode status queried through Freyja Core",
                "status_keys": ["alias", 44]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_coding_status_key_types")

    report = module.build_status(evidence)

    coding = next(item for item in report["acceptance"] if item["id"] == "coding_workflow")
    assert coding["status"] == "partial"
    assert "handoff_trace_id must reference a verified last_tool_smoke.coding_workflow result." in coding["semantic_failures"]


def test_freyja6_acceptance_status_requires_coding_workflow_summary_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_tool_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "coding_workflow": {
              "ok": true,
              "tool": "opencode.status",
              "trace_id": "trace-coding",
              "alias": "freyja-core-coder",
              "result_summary": "opencode status queried through Freyja Core",
              "status_payload_present": true,
              "status_keys": ["alias", "state"]
            }
          },
          "acceptance": {
            "coding_workflow": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "executor": "opencode",
                "handoff_trace_id": "trace-coding",
                "result_summary": "opencode shell completed",
                "status_keys": ["alias", "state"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_coding_result_summary")

    report = module.build_status(evidence)

    coding = next(item for item in report["acceptance"] if item["id"] == "coding_workflow")
    assert coding["status"] == "partial"
    assert "result_summary must match the Freyja Core OpenCode status summary." in coding["semantic_failures"]
    assert "handoff_trace_id must reference a verified last_tool_smoke.coding_workflow result." in coding["semantic_failures"]


def test_freyja6_acceptance_status_rejects_wrong_evidence_source(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "manual-note",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_wrong_source")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "source must be freyja6-litellm-smoke." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_stale_producer_timestamp(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_discord_smoke": {
            "timestamp": "2026-09-18T23:59:59+00:00",
            "ok": true
          },
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_stale_producer")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert report["complete"] is False
    assert discord["status"] == "partial"
    assert "captured_at must match last_discord_smoke.timestamp." in discord["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_producer_timestamp(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_discord_smoke": {
            "timestamp": 123,
            "ok": true
          },
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-reply",
                "verification_method": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_producer_timestamp_type")

    report = module.build_status(evidence)

    discord = next(item for item in report["acceptance"] if item["id"] == "discord_reply")
    assert report["complete"] is False
    assert discord["status"] == "partial"
    assert "last_discord_smoke.timestamp must be a string." in discord["semantic_failures"]


def test_freyja6_acceptance_status_requires_distinct_model_switch_traces(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-same", "trace-same"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_model_switch_distinct_traces")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must contain at least two distinct traces." in model_switch["semantic_failures"]
    assert "gateway_trace_ids must not contain duplicate traces." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_requires_model_switch_trace_per_model(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast", "vulcan-code"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_model_switch_trace_count")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must contain exactly one trace per tested model." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_extra_duplicate_model_switch_trace(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast", "vulcan-code"],
                "gateway_trace_ids": ["trace-general", "trace-fast", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_model_switch_duplicate_trace")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must not contain duplicate traces." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_invalid_calendar_and_reboot_dates(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "next Saturday",
                "tool_trace_id": "trace-calendar-create",
              "created_event_id": "event-id-crea...ed-1"
              }
            },
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:03:00+00:00/2026-09-19T10:00:00+00:00",
                "container_status_after": "running (healthy)",
                "discord_reply_after_reboot": "trace-discord-after-reboot",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_date_semantics")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert calendar["status"] == "partial"
    assert "event_date must be an ISO date." in calendar["semantic_failures"]
    assert reboot["status"] == "partial"
    assert "reboot_window end must be after start." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_date_not_datetime(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19T09:00:00+00:00",
                "tool_trace_id": "trace-calendar-create",
              "created_event_id": "event-id-crea...ed-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_date_only")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "event_date must be an ISO date." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_event_date_saturday(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-20",
                "tool_trace_id": "trace-calendar-create",
              "created_event_id": "event-id-crea...ed-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_saturday")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "event_date must be a Saturday." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_acceptance_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_calendar_write_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "event_title": "Basement cleanup",
            "event_date": "2026-09-19",
            "create": {
              "ok": true,
              "tool": "calendar.create_event",
              "trace_id": "trace-calendar-create",
              "event": {
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T10:00:00+00:00"
              }
            }
          },
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19",
                "tool_trace_id": "trace-calendar-stale",
              "created_event_id": "event-id-crea...ed-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_producer_trace")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "tool_trace_id must match last_calendar_write_smoke.create.trace_id." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_producer_create_success(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_calendar_write_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "ok": true,
            "event_title": "Basement cleanup",
            "event_date": "2026-09-19",
            "create": {
              "ok": false,
              "tool": "calendar.create_event",
              "trace_id": "trace-calendar-create",
              "event": {
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T10:00:00+00:00"
              }
            }
          },
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19",
                "tool_trace_id": "trace-calendar-create",
              "created_event_id": "event-id-crea...ed-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_producer_create_success")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "tool_trace_id must reference a verified calendar.create_event producer result." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_rejects_calendar_producer_event_drift(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_calendar_write_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "event_title": "Basement cleanup",
            "event_date": "2026-09-19",
            "create": {
              "ok": true,
              "tool": "calendar.create_event",
              "trace_id": "trace-calendar-create",
              "event": {
                "title": "Different event",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T10:00:00+00:00"
              }
            }
          },
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19",
                "tool_trace_id": "trace-calendar-create",
              "created_event_id": "event-id-crea...ed-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_producer_event")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "created event title must match Basement cleanup." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_producer_event_identifier(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_calendar_write_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "ok": true,
            "event_title": "Basement cleanup",
            "event_date": "2026-09-19",
            "duration_minutes": 60,
            "create": {
              "ok": true,
              "tool": "calendar.create_event",
              "trace_id": "trace-calendar-create",
              "event": {
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T10:00:00+00:00"
              }
            }
          },
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19",
                "tool_trace_id": "trace-calendar-create",
              "created_event_id": "event-id-crea...ed-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_producer_event_identifier")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "tool_trace_id must reference a verified calendar.create_event producer result." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_calendar_producer_event_identifier(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_calendar_write_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "ok": true,
            "event_title": "Basement cleanup",
            "event_date": "2026-09-19",
            "duration_minutes": 60,
            "create": {
              "ok": true,
              "tool": "calendar.create_event",
              "trace_id": "trace-calendar-create",
              "event": {
                "event_id": 123,
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T10:00:00+00:00"
              }
            }
          },
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19",
                "tool_trace_id": "trace-calendar-create",
                "created_event_id": "event-id-...123"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_producer_event_id_type")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "tool_trace_id must reference a verified calendar.create_event producer result." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_requires_calendar_created_event_id_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_calendar_write_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "ok": true,
            "event_title": "Basement cleanup",
            "event_date": "2026-09-19",
            "duration_minutes": 60,
            "create": {
              "ok": true,
              "tool": "calendar.create_event",
              "trace_id": "trace-calendar-create",
              "event": {
                "event_id": "created-1",
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T10:00:00+00:00"
              }
            }
          },
          "acceptance": {
            "calendar_create_event": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-calendar-write-smoke",
              "evidence": {
                "event_title": "Basement cleanup",
                "event_date": "2026-09-19",
                "tool_trace_id": "trace-calendar-create",
                "created_event_id": "event-id-stal...le-1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_calendar_event_id_match")

    report = module.build_status(evidence)

    calendar = next(item for item in report["acceptance"] if item["id"] == "calendar_create_event")
    assert calendar["status"] == "partial"
    assert "created_event_id must match the redacted created event identifier." in calendar["semantic_failures"]


def test_freyja6_acceptance_status_rejects_not_running_reboot_status(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                "container_status_after": "not running",
                "discord_reply_after_reboot": "trace-discord-after-reboot",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_reboot_not_running")

    report = module.build_status(evidence)

    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert reboot["status"] == "partial"
    assert "container_status_after must be running or healthy." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_requires_timezone_aware_reboot_window(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:00:00/2026-09-19T10:03:00",
                "container_status_after": "running (healthy)",
                "discord_reply_after_reboot": "trace-discord-after-reboot",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_reboot_window_timezone")

    report = module.build_status(evidence)

    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert reboot["status"] == "partial"
    assert "reboot_window timestamps must include timezone offsets." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_rejects_future_reboot_window(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2999-09-19T10:00:00+00:00/2999-09-19T10:03:00+00:00",
                "container_status_after": "running (healthy)",
                "discord_reply_after_reboot": "trace-discord-after-reboot",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_reboot_window_future")

    report = module.build_status(evidence)

    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert reboot["status"] == "partial"
    assert "reboot_window must not be in the future." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_requires_distinct_restart_recall_and_reboot_traces(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "discord_reply": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-discord-smoke",
              "evidence": {
                "discord_channel_id_redacted": "discord-channel-test",
                "message_trace_id": "trace-message",
                "reply_trace_id": "trace-initial-reply",
                "verification_method": "discord-api"
              }
            },
            "restart_identity_session": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "restart_trace_id": "trace-restart",
                "identity_before": "sha256:same",
                "identity_after": "sha256:same",
                "session_restored": true
              }
            },
            "remember_fact": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "stored_fact_label": "basement-cleanup-fact",
                "recall_trace_id": "trace-restart",
                "memory_provider": "hermes-native"
              }
            },
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                "container_status_after": "running (healthy)",
                "discord_reply_after_reboot": "trace-initial-reply",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_distinct_restart_traces")

    report = module.build_status(evidence)

    memory = next(item for item in report["acceptance"] if item["id"] == "remember_fact")
    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert memory["status"] == "partial"
    assert "recall_trace_id must be distinct from restart_trace_id." in memory["semantic_failures"]
    assert reboot["status"] == "partial"
    assert "discord_reply_after_reboot must be distinct from the initial Discord reply trace." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_rejects_unsafe_stored_fact_label(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "remember_fact": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "stored_fact_label": "../basement cleanup",
                "recall_trace_id": "trace-memory-recall",
                "memory_provider": "hermes-native"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_stored_fact_label")

    report = module.build_status(evidence)

    memory = next(item for item in report["acceptance"] if item["id"] == "remember_fact")
    assert memory["status"] == "partial"
    assert "stored_fact_label must be a non-empty local identifier." in memory["semantic_failures"]


def test_freyja6_acceptance_status_rejects_reboot_reply_reusing_restart_trace(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "restart_identity_session": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "restart_trace_id": "trace-restart",
                "identity_before": "sha256:same",
                "identity_after": "sha256:same",
                "session_restored": true
              }
            },
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                "container_status_after": "running (healthy)",
                "discord_reply_after_reboot": "trace-restart",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_reboot_restart_trace")

    report = module.build_status(evidence)

    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert reboot["status"] == "partial"
    assert "discord_reply_after_reboot must be distinct from restart_trace_id." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_requires_restart_identity_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    identity_hash = "a" * 64
    stale_hash = "b" * 64
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-live-evidence",
                "last_restart_evidence": {
                    "timestamp": "2026-09-19T00:00:00+00:00",
                    "restart_trace_id": "trace-restart",
                    "identity_before_sha256": identity_hash,
                    "identity_after_sha256": identity_hash,
                    "identity_matches_before": True,
                    "session_restored": True,
                },
                "acceptance": {
                    "restart_identity_session": {
                        "status": "complete",
                        "captured_at": "2026-09-19T00:00:00+00:00",
                        "source": "freyja6-restart-evidence",
                        "evidence": {
                            "restart_trace_id": "trace-restart",
                            "identity_before": "sha256:" + stale_hash,
                            "identity_after": "sha256:" + stale_hash,
                            "session_restored": True,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_restart_producer_identity")

    report = module.build_status(evidence)

    restart = next(item for item in report["acceptance"] if item["id"] == "restart_identity_session")
    assert restart["status"] == "partial"
    assert "identity_before must match last_restart_evidence.identity_before_sha256." in restart["semantic_failures"]


def test_freyja6_acceptance_status_rejects_type_corrupted_restart_producer_values(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    identity_hash = "a" * 64
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-live-evidence",
                "last_restart_evidence": {
                    "timestamp": "2026-09-19T00:00:00+00:00",
                    "restart_trace_id": 123,
                    "identity_before_sha256": identity_hash,
                    "identity_after_sha256": identity_hash,
                    "identity_matches_before": True,
                    "session_restored": True,
                    "stored_fact_label": "basement-cleanup-fact",
                    "memory_recall_trace_id": ["trace-memory-recall"],
                    "memory_provider": "hermes-native",
                    "memory_fact_present": True,
                    "memory_fact_recalled": True,
                    "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                    "container_status_after": {"status": "running"},
                    "discord_reply_after_reboot": "trace-discord-after-reboot",
                    "discord_reply_after_reboot_verification": "discord-api",
                },
                "acceptance": {
                    "restart_identity_session": {
                        "status": "complete",
                        "captured_at": "2026-09-19T00:00:00+00:00",
                        "source": "freyja6-restart-evidence",
                        "evidence": {
                            "restart_trace_id": "123",
                            "identity_before": "sha256:" + identity_hash,
                            "identity_after": "sha256:" + identity_hash,
                            "session_restored": True,
                        },
                    },
                    "remember_fact": {
                        "status": "complete",
                        "captured_at": "2026-09-19T00:00:00+00:00",
                        "source": "freyja6-restart-evidence",
                        "evidence": {
                            "stored_fact_label": "basement-cleanup-fact",
                            "recall_trace_id": "['trace-memory-recall']",
                            "memory_provider": "hermes-native",
                        },
                    },
                    "atlas_reboot_return": {
                        "status": "complete",
                        "captured_at": "2026-09-19T00:00:00+00:00",
                        "source": "freyja6-restart-evidence",
                        "evidence": {
                            "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                            "container_status_after": "{'status': 'running'}",
                            "discord_reply_after_reboot": "trace-discord-after-reboot",
                            "discord_reply_after_reboot_verification": "discord-api",
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_restart_producer_types")

    report = module.build_status(evidence)

    restart = next(item for item in report["acceptance"] if item["id"] == "restart_identity_session")
    memory = next(item for item in report["acceptance"] if item["id"] == "remember_fact")
    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert "restart_trace_id must match last_restart_evidence.restart_trace_id." in restart["semantic_failures"]
    assert "recall_trace_id must match last_restart_evidence.memory_recall_trace_id." in memory["semantic_failures"]
    assert "container_status_after must match last_restart_evidence.container_status_after." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_requires_memory_recall_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_restart_evidence": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "stored_fact_label": "basement-cleanup-fact",
            "memory_recall_trace_id": "trace-memory-recall",
            "memory_provider": "hermes-native",
            "memory_fact_present": true,
            "memory_fact_recalled": true
          },
          "acceptance": {
            "remember_fact": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "stored_fact_label": "basement-cleanup-fact",
                "recall_trace_id": "trace-stale-memory",
                "memory_provider": "hermes-native"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_memory_producer_recall")

    report = module.build_status(evidence)

    memory = next(item for item in report["acceptance"] if item["id"] == "remember_fact")
    assert memory["status"] == "partial"
    assert "recall_trace_id must match last_restart_evidence.memory_recall_trace_id." in memory["semantic_failures"]


def test_freyja6_acceptance_status_requires_reboot_return_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_restart_evidence": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
            "container_status_after": "running (healthy)",
            "discord_reply_after_reboot": "trace-discord-after-reboot",
            "discord_reply_after_reboot_verification": "discord-api"
          },
          "acceptance": {
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                "container_status_after": "running",
                "discord_reply_after_reboot": "trace-discord-after-reboot",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_reboot_producer")

    report = module.build_status(evidence)

    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert reboot["status"] == "partial"
    assert "container_status_after must match last_restart_evidence.container_status_after." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_rejects_public_litellm_backend_with_vulcan_name(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-general",
                "model": "vulcan-general",
                "vulcan_backend": "https://vulcan.example.com/v1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_public_litellm_backend")

    report = module.build_status(evidence)

    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    assert litellm["status"] == "partial"
    assert "vulcan_backend must be a redacted local LiteLLM/Vulcan endpoint." in litellm["semantic_failures"]


def test_freyja6_acceptance_status_rejects_raw_private_litellm_backend(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-general",
                "model": "vulcan-general",
                "vulcan_backend": "http://10.0.0.12:4600/v1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_raw_private_litellm_backend")

    report = module.build_status(evidence)

    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    assert litellm["status"] == "partial"
    assert "vulcan_backend must be a redacted local LiteLLM/Vulcan endpoint." in litellm["semantic_failures"]


def test_freyja6_acceptance_status_rejects_raw_trace_ids(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "pwd",
                "tool_trace_id": "terminal-123",
                "exit_code": 0,
                "working_dir": "freyja-os"
              }
            },
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "raw-fast"]
              }
            },
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "request-raw",
                "model": "vulcan-general",
                "vulcan_backend": "http://atlas-loopback:4600/v1"
              }
            },
            "atlas_reboot_return": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
                "container_status_after": "running (healthy)",
                "discord_reply_after_reboot": "reply-raw",
                "discord_reply_after_reboot_verification": "discord-api"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_trace_semantics")

    report = module.build_status(evidence)

    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    reboot = next(item for item in report["acceptance"] if item["id"] == "atlas_reboot_return")
    assert terminal["status"] == "partial"
    assert "tool_trace_id must use a Freyja validation trace prefix." in terminal["semantic_failures"]
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must use a Freyja validation trace prefix." in model_switch["semantic_failures"]
    assert litellm["status"] == "partial"
    assert "litellm_request_id must use a Freyja validation trace prefix." in litellm["semantic_failures"]
    assert reboot["status"] == "partial"
    assert "discord_reply_after_reboot must use a Freyja validation trace prefix." in reboot["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_string_trace_ids(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": {
            "safe_terminal": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-tool-smoke",
              "evidence": {
                "command": "pwd",
                "tool_trace_id": 44,
                "exit_code": 0,
                "working_dir": "freyja-os"
              }
            },
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "response_models": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", 44]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_non_string_trace_ids")

    report = module.build_status(evidence)

    terminal = next(item for item in report["acceptance"] if item["id"] == "safe_terminal")
    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert terminal["status"] == "partial"
    assert "tool_trace_id must be a string." in terminal["semantic_failures"]
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must be a string." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_example_placeholder_evidence(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "restart_identity_session": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-restart-evidence",
              "evidence": {
                "restart_trace_id": "trace-...",
                "identity_before": "sha256:...",
                "identity_after": "sha256:...",
                "session_restored": true
              }
            },
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-...",
                "model": "vulcan-general",
                "vulcan_backend": "http://atlas-loopback:4600/v1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_placeholder_evidence")

    report = module.build_status(evidence)

    restart = next(item for item in report["acceptance"] if item["id"] == "restart_identity_session")
    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    assert restart["status"] == "partial"
    assert "restart_trace_id must not use placeholder ellipses." in restart["semantic_failures"]
    assert "identity hashes must not use placeholder ellipses." in restart["semantic_failures"]
    assert litellm["status"] == "partial"
    assert "litellm_request_id must not use placeholder ellipses." in litellm["semantic_failures"]


def test_freyja6_acceptance_status_rejects_invalid_captured_at(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "after lunch",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_bad_timestamp")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "captured_at must be an ISO timestamp." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_non_list_trace_ids(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "response_models": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": "trace-general"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_non_list_trace_ids")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must be a list." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_requires_timezone_aware_captured_at(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T12:00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_naive_timestamp")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "captured_at must include a timezone offset." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_future_captured_at(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2999-09-19T12:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_future_timestamp")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "captured_at must not be in the future." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_requires_litellm_acceptance_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_litellm_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "base_url_redacted": "http://atlas-loopback:4600/v1",
            "listed_models": ["vulcan-fast", "vulcan-general"],
            "results": [
              {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": true,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop"
              }
            ]
          },
          "acceptance": {
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-stale",
                "model": "vulcan-general",
                "vulcan_backend": "http://atlas-loopback:4600/v1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_litellm_producer_trace")

    report = module.build_status(evidence)

    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    assert litellm["status"] == "partial"
    assert "litellm_request_id must match a last_litellm_smoke result trace." in litellm["semantic_failures"]


def test_freyja6_acceptance_status_requires_litellm_response_model_to_match_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_litellm_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "base_url_redacted": "http://atlas-loopback:4600/v1",
            "listed_models": ["vulcan-fast", "vulcan-general"],
            "results": [
              {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": true,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop"
              }
            ]
          },
          "acceptance": {
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-general",
                "model": "vulcan-general",
                "response_model": "vulcan-fast",
                "vulcan_backend": "http://atlas-loopback:4600/v1"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_litellm_producer_response_model")

    report = module.build_status(evidence)

    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    assert litellm["status"] == "partial"
    assert "response_model must match model." in litellm["semantic_failures"]
    assert "response_model must match the last_litellm_smoke result response_model." in litellm["semantic_failures"]


def test_freyja6_acceptance_status_rejects_type_corrupted_litellm_producer_results(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_litellm_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "base_url_redacted": "http://atlas-loopback:4600/v1",
            "listed_models": ["vulcan-fast", 42],
            "results": [
              {
                "model": 42,
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": true,
                "response_model": 42,
                "response_text": "gateway ok",
                "finish_reason": "stop"
              },
              {
                "model": "vulcan-fast",
                "trace_id": 123,
                "status_code": 200,
                "ok": true,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop"
              }
            ]
          },
          "acceptance": {
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-general",
                "model": "vulcan-general",
                "response_model": "vulcan-general",
                "vulcan_backend": "http://atlas-loopback:4600/v1"
              }
            },
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "response_models": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_litellm_producer_types")

    report = module.build_status(evidence)

    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert litellm["status"] == "partial"
    assert "model must match the last_litellm_smoke result model." in litellm["semantic_failures"]
    assert model_switch["status"] == "partial"
    assert "models_tested must align with last_litellm_smoke result models." in model_switch["semantic_failures"]


def test_freyja6_acceptance_status_rejects_type_corrupted_litellm_backend_producer(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_litellm_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "base_url_redacted": ["http://atlas-loopback:4600/v1"],
            "listed_models": ["vulcan-general"],
            "results": [
              {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": true,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop"
              }
            ]
          },
          "acceptance": {
            "litellm_to_vulcan": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "litellm_request_id": "trace-general",
                "model": "vulcan-general",
                "response_model": "vulcan-general",
                "vulcan_backend": "['http://atlas-loopback:4600/v1']"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_litellm_backend_type")

    report = module.build_status(evidence)

    litellm = next(item for item in report["acceptance"] if item["id"] == "litellm_to_vulcan")
    assert litellm["status"] == "partial"
    assert "vulcan_backend must match last_litellm_smoke.base_url_redacted." in litellm["semantic_failures"]


def test_freyja6_acceptance_status_requires_model_switch_verified_producer_results(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """
        {
          "schema_version": "1.0",
          "report_type": "freyja6-live-evidence",
          "last_litellm_smoke": {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "base_url_redacted": "http://atlas-loopback:4600/v1",
            "listed_models": ["vulcan-fast", "vulcan-general"],
            "results": [
              {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": true,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop"
              },
              {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": true,
                "response_model": "vulcan-fast",
                "response_text": "not the validation phrase",
                "finish_reason": "stop"
              }
            ]
          },
          "acceptance": {
            "model_switch": {
              "status": "complete",
              "captured_at": "2026-09-19T00:00:00+00:00",
              "source": "freyja6-litellm-smoke",
              "evidence": {
                "models_tested": ["vulcan-general", "vulcan-fast"],
                "gateway_trace_ids": ["trace-general", "trace-fast"]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_acceptance_module("freyja6_acceptance_status_model_switch_producer_verified")

    report = module.build_status(evidence)

    model_switch = next(item for item in report["acceptance"] if item["id"] == "model_switch")
    assert model_switch["status"] == "partial"
    assert "gateway_trace_ids must reference verified LiteLLM gateway results." in model_switch["semantic_failures"]


def test_freyja6_litellm_smoke_updates_redacted_acceptance_evidence(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke")
    evidence = tmp_path / "evidence.json"
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-code", "vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    payload = module.update_evidence(evidence, smoke)

    acceptance = payload["acceptance"]
    assert acceptance["litellm_to_vulcan"]["status"] == "complete"
    assert acceptance["litellm_to_vulcan"]["captured_at"] == "2026-09-19T00:00:00+00:00"
    assert acceptance["litellm_to_vulcan"]["source"] == "freyja6-litellm-smoke"
    assert acceptance["litellm_to_vulcan"]["evidence"] == {
        "litellm_request_id": "trace-general",
        "model": "vulcan-general",
        "response_model": "vulcan-general",
        "vulcan_backend": "http://atlas-loopback:4600/v1",
    }
    assert acceptance["model_switch"]["evidence"]["models_tested"] == ["vulcan-general", "vulcan-fast"]
    assert acceptance["model_switch"]["evidence"]["response_models"] == ["vulcan-general", "vulcan-fast"]
    assert acceptance["model_switch"]["evidence"]["listed_models"] == ["vulcan-code", "vulcan-fast", "vulcan-general"]


def test_freyja6_litellm_smoke_refuses_malformed_existing_evidence(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    try:
        module.update_evidence(evidence, smoke)
    except ValueError as exc:
        assert "acceptance must be an object" in str(exc)
    else:
        raise AssertionError("malformed evidence acceptance should be rejected before writing")


def test_freyja6_litellm_smoke_refuses_symlinked_existing_evidence(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    try:
        module.update_evidence(evidence, smoke)
    except ValueError as exc:
        assert "Live evidence file must not be a symlink." in str(exc)
    else:
        raise AssertionError("symlinked live evidence should be rejected before writing")

    assert json.loads(real_evidence.read_text(encoding="utf-8"))["acceptance"] == {}


def test_freyja6_litellm_smoke_cli_refuses_symlinked_evidence_before_gateway_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_cli_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("LiteLLM gateway client should not open for unsafe evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--api-key",
            "sk-test",
            "--base-url",
            "http://127.0.0.1:4600/v1",
            "--models",
            "vulcan-general",
            "vulcan-fast",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["error"] == "Live evidence file must not be a symlink."
    assert real_evidence.read_text(encoding="utf-8") == '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    assert not (tmp_path / "logs").exists()


def test_freyja6_litellm_smoke_cli_refuses_malformed_evidence_before_gateway_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_cli_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("LiteLLM gateway client should not open for malformed evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--api-key",
            "sk-test",
            "--base-url",
            "http://127.0.0.1:4600/v1",
            "--models",
            "vulcan-general",
            "vulcan-fast",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert "acceptance must be an object" in rendered["error"]
    assert not (tmp_path / "logs").exists()


def test_freyja6_litellm_smoke_cli_refuses_symlinked_log_before_gateway_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_cli_symlink_log")
    evidence = tmp_path / "evidence.json"
    evidence_payload = '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    evidence.write_text(evidence_payload, encoding="utf-8")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    real_log = tmp_path / "real-model-calls.jsonl"
    real_log.write_text("sentinel\n", encoding="utf-8")
    (log_root / "freyja-test-model-calls.jsonl").symlink_to(real_log)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("LiteLLM gateway client should not open for unsafe log path")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--api-key",
            "sk-test",
            "--base-url",
            "http://127.0.0.1:4600/v1",
            "--models",
            "vulcan-general",
            "vulcan-fast",
            "--evidence",
            str(evidence),
            "--log-root",
            str(log_root),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["error"] == "Log file must not be a symlink: freyja-test-model-calls.jsonl."
    assert evidence.read_text(encoding="utf-8") == evidence_payload
    assert real_log.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_litellm_smoke_requires_distinct_gateway_aliases() -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_distinct")

    try:
        module._validate_requested_models(["vulcan-general", "vulcan-general"])
    except ValueError as exc:
        assert "at least two distinct" in str(exc)
    else:
        raise AssertionError("duplicate model aliases should fail model switch validation")


def test_freyja6_litellm_smoke_rejects_unapproved_gateway_alias() -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_unapproved")

    try:
        module._validate_requested_models(["vulcan-general", "cloud-frontier"])
    except ValueError as exc:
        assert "Unexpected Freyja 6 LiteLLM aliases requested: cloud-frontier" in str(exc)
    else:
        raise AssertionError("unapproved model aliases should fail validation")


def test_freyja6_litellm_smoke_rejects_public_gateway_base_url() -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_public_gateway")

    try:
        module._validate_gateway_base_url("https://api.example.com/v1")
    except ValueError as exc:
        assert "must use Atlas loopback, private, tailnet, or explicitly LiteLLM-scoped host" in str(exc)
    else:
        raise AssertionError("public LiteLLM gateway URLs should fail validation")


def test_freyja6_litellm_smoke_allows_atlas_loopback_and_private_gateway_urls() -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_private_gateway")

    module._validate_gateway_base_url("http://127.0.0.1:4600/v1")
    module._validate_gateway_base_url("http://10.0.0.12:4600/v1")
    module._validate_gateway_base_url("http://100.94.80.21:4600/v1")
    module._validate_gateway_base_url("http://litellm.local:4600/v1")


def test_freyja6_litellm_smoke_redacts_private_gateway_urls() -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_gateway_redaction")

    assert module._redact_base_url("http://127.0.0.1:4600/v1") == "http://atlas-loopback:4600/v1"
    assert module._redact_base_url("http://10.0.0.12:4600/v1") == "http://atlas-private:4600/v1"
    assert module._redact_base_url("http://100.94.80.21:4600/v1") == "http://vulcan-tailnet:4600/v1"
    assert module._redact_base_url("http://litellm.local:4600/v1") == "http://atlas-local:4600/v1"


def test_freyja6_litellm_smoke_requires_explicit_matching_response_model(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_response_model")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": None,
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
            },
        ],
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)

    assert module._response_model_matches("vulcan-general", {"model": "vulcan-general"}) is True
    assert module._response_model_matches("vulcan-general", {}) is False
    assert "litellm_to_vulcan" not in payload["acceptance"]
    assert "model_switch" not in payload["acceptance"]


def test_freyja6_litellm_smoke_requires_expected_gateway_response_text(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_response_text")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "hello from somewhere else",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "length",
            },
        ],
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)
    model_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "freyja-test-model-calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert module._response_content_matches({"choices": [{"message": {"content": "gateway ok"}, "finish_reason": "stop"}]}) is True
    assert module._response_content_matches({"choices": [{"message": {"content": "not it"}, "finish_reason": "stop"}]}) is False
    assert "litellm_to_vulcan" not in payload["acceptance"]
    assert "model_switch" not in payload["acceptance"]
    assert {entry["trace_id"]: entry["status"] for entry in model_entries} == {
        "trace-general": "failed",
        "trace-fast": "failed",
    }
    assert {entry["trace_id"]: entry["error_summary"] for entry in model_entries} == {
        "trace-general": "response text did not match validation phrase",
        "trace-fast": "response did not finish with stop",
    }
    assert writes == [
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-general"},
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-fast"},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_litellm_smoke_rejects_placeholder_traces_for_acceptance(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_placeholder_trace_guard")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-...",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "freyja6-...",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)
    model_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "freyja-test-model-calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert module._verified_results(smoke) == []
    assert "litellm_to_vulcan" not in payload["acceptance"]
    assert "model_switch" not in payload["acceptance"]
    assert {entry["trace_id"]: entry["status"] for entry in model_entries} == {
        "trace-...": "failed",
        "freyja6-...": "failed",
    }
    assert {entry["trace_id"]: entry["error_summary"] for entry in model_entries} == {
        "trace-...": "trace id is not a Freyja validation trace",
        "freyja6-...": "trace id is not a Freyja validation trace",
    }
    assert writes == [
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-..."},
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "freyja6-..."},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_litellm_smoke_appends_structured_logs(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_logs")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    writes = module.append_logs(tmp_path, smoke)

    model_entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-model-calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    acceptance_entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-acceptance.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {entry["model"] for entry in model_entries} == {"vulcan-general", "vulcan-fast"}
    assert all(entry["event"] == "model_call" for entry in model_entries)
    assert {entry["acceptance_id"] for entry in acceptance_entries} == {"litellm_to_vulcan", "model_switch"}
    assert writes == [
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-general"},
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-fast"},
        {"log": "freyja6/logs/freyja-test-acceptance.jsonl", "trace_id": "trace-general"},
        {"log": "freyja6/logs/freyja-test-acceptance.jsonl", "trace_id": "trace-fast"},
    ]


def test_freyja6_litellm_smoke_requires_verified_gateway_results_for_acceptance(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_verified")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "external-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "cloud-frontier",
                "trace_id": "trace-cloud",
                "status_code": 200,
                "ok": True,
                "response_model": "cloud-frontier",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)
    model_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "freyja-test-model-calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert "litellm_to_vulcan" not in payload["acceptance"]
    assert "model_switch" not in payload["acceptance"]
    assert {entry["trace_id"]: entry["status"] for entry in model_entries} == {
        "external-general": "failed",
        "trace-fast": "failed",
        "trace-cloud": "failed",
    }
    assert {entry["trace_id"]: entry["error_summary"] for entry in model_entries} == {
        "external-general": "trace id is not a Freyja validation trace",
        "trace-fast": "response model did not match requested alias",
        "trace-cloud": "model alias is not approved for Freyja 6 validation",
    }
    assert writes == [
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "external-general"},
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-fast"},
        {"log": "freyja6/logs/freyja-test-model-calls.jsonl", "trace_id": "trace-cloud"},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_litellm_smoke_model_switch_uses_one_trace_per_model(tmp_path) -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_model_switch_trace_per_model")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast-a",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast-b",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-fast",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
        ],
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    model_switch = payload["acceptance"]["model_switch"]["evidence"]
    assert model_switch["models_tested"] == ["vulcan-general", "vulcan-fast"]
    assert model_switch["gateway_trace_ids"] == ["trace-general", "trace-fast-a"]
    assert {"log": "freyja6/logs/freyja-test-acceptance.jsonl", "trace_id": "trace-fast-a"} in writes
    assert {"log": "freyja6/logs/freyja-test-acceptance.jsonl", "trace_id": "trace-fast-b"} not in writes


def test_freyja6_litellm_smoke_reports_missing_requested_verified_models() -> None:
    module = _load_litellm_smoke_module("freyja6_litellm_smoke_missing_requested")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "base_url_redacted": "http://atlas-loopback:4600/v1",
        "listed_models": ["vulcan-code", "vulcan-fast", "vulcan-general"],
        "results": [
            {
                "model": "vulcan-general",
                "trace_id": "trace-general",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
                "response_text": "gateway ok",
                "finish_reason": "stop",
            },
            {
                "model": "vulcan-fast",
                "trace_id": "trace-fast",
                "status_code": 200,
                "ok": True,
                "response_model": "vulcan-general",
            },
        ],
    }

    assert module._missing_verified_models(smoke, ["vulcan-general", "vulcan-fast", "vulcan-code"]) == [
        "vulcan-fast",
        "vulcan-code",
    ]


def test_freyja6_tool_smoke_updates_non_mutating_acceptance_evidence(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke")
    evidence = tmp_path / "evidence.json"
    smoke = {
        "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-file", "bytes": 42},
        "safe_terminal": {"ok": True, "command": "pwd", "trace_id": "trace-terminal", "exit_code": 0, "working_dir": "freyja-os"},
        "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
        "mcp_discovery": {"ok": True, "tool": "status.check", "trace_id": "trace-mcp", "status_code": 200},
        "calendar_read": {"ok": True, "tool": "calendar.list_events", "trace_id": "trace-calendar", "status_code": 200},
        "home_assistant_query": {"ok": True, "tool": "home_assistant.list_states", "domain": "sensor", "trace_id": "trace-home", "status_code": 200, "result_keys": ["ok", "states"], "states_count": 1},
        "coding_workflow": {"ok": True, "tool": "opencode.status", "trace_id": "trace-coding", "status_code": 200, "alias": "freyja-core-coder", "result_summary": "opencode status queried through Freyja Core", "status_payload_present": True, "status_keys": ["alias", "state"]},
    }

    payload = module.update_evidence(evidence, smoke)
    acceptance = payload["acceptance"]

    assert acceptance["approved_file_read"]["evidence"]["approved_path"] == "approved-files/smoke.txt"
    assert acceptance["approved_file_read"]["source"] == "freyja6-tool-smoke"
    assert acceptance["approved_file_read"]["captured_at"]
    assert acceptance["approved_file_read"]["evidence"]["bytes_read"] == 42
    assert acceptance["safe_terminal"]["evidence"]["command"] == "pwd"
    assert acceptance["safe_terminal"]["evidence"]["tool_trace_id"] == "trace-terminal"
    assert acceptance["safe_terminal"]["evidence"]["exit_code"] == 0
    assert acceptance["safe_terminal"]["evidence"]["working_dir"] == "freyja-os"
    assert acceptance["mcp_tool"]["evidence"]["server"] == "freyja-core-gateway"
    assert acceptance["mcp_tool"]["evidence"]["status_code"] == 200
    assert acceptance["calendar_read"]["evidence"]["tool_trace_id"] == "trace-calendar"
    assert acceptance["calendar_read"]["evidence"]["status_code"] == 200
    assert acceptance["home_assistant_query"]["evidence"]["entity_id_redacted"] == "domain:sensor"
    assert acceptance["home_assistant_query"]["evidence"]["states_count"] == 1
    assert acceptance["coding_workflow"]["evidence"]["executor"] == "opencode"
    assert acceptance["coding_workflow"]["evidence"]["result_summary"] == "opencode status queried through Freyja Core"
    assert acceptance["coding_workflow"]["evidence"]["status_keys"] == ["alias", "state"]
    assert module._tool_smoke_ok(smoke) is True


def test_freyja6_tool_smoke_refuses_wrong_existing_evidence_artifact(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_wrong_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-acceptance-status","acceptance":{}}\n',
        encoding="utf-8",
    )

    try:
        module.update_evidence(evidence, {})
    except ValueError as exc:
        assert "freyja6-live-evidence schema_version 1.0" in str(exc)
    else:
        raise AssertionError("wrong evidence artifact type should be rejected before writing")


def test_freyja6_tool_smoke_refuses_symlinked_existing_evidence(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)

    try:
        module.update_evidence(evidence, {})
    except ValueError as exc:
        assert "Live evidence file must not be a symlink." in str(exc)
    else:
        raise AssertionError("symlinked live evidence should be rejected before writing")

    assert json.loads(real_evidence.read_text(encoding="utf-8"))["acceptance"] == {}


def test_freyja6_tool_smoke_cli_refuses_symlinked_evidence_before_tool_calls(tmp_path, monkeypatch, capsys) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_cli_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("core tool client should not open for unsafe evidence")

    def fail_run(*args, **kwargs):
        raise AssertionError("safe terminal command should not run for unsafe evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)
    monkeypatch.setattr(module.subprocess, "run", fail_run)

    exit_code = module.main(
        [
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["error"] == "Live evidence file must not be a symlink."
    assert real_evidence.read_text(encoding="utf-8") == '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    assert not (tmp_path / "logs").exists()


def test_freyja6_tool_smoke_cli_refuses_malformed_evidence_before_tool_calls(tmp_path, monkeypatch, capsys) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_cli_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("core tool client should not open for malformed evidence")

    def fail_run(*args, **kwargs):
        raise AssertionError("safe terminal command should not run for malformed evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)
    monkeypatch.setattr(module.subprocess, "run", fail_run)

    exit_code = module.main(
        [
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert "acceptance must be an object" in rendered["error"]
    assert not (tmp_path / "logs").exists()


def test_freyja6_tool_smoke_cli_refuses_symlinked_log_before_tool_calls(tmp_path, monkeypatch, capsys) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_cli_symlink_log")
    evidence = tmp_path / "evidence.json"
    evidence_payload = '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    evidence.write_text(evidence_payload, encoding="utf-8")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    real_log = tmp_path / "real-tools.jsonl"
    real_log.write_text("sentinel\n", encoding="utf-8")
    (log_root / "freyja-test-tools.jsonl").symlink_to(real_log)
    approved = tmp_path / "freyja6/approved-files/smoke.txt"
    approved.parent.mkdir(parents=True)
    approved.write_text("approved\n", encoding="utf-8")

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("core tool client should not open for unsafe log path")

    def fail_get(*args, **kwargs):
        raise AssertionError("health check should not run for unsafe log path")

    def fail_run(*args, **kwargs):
        raise AssertionError("safe terminal command should not run for unsafe log path")

    monkeypatch.setattr(module.httpx, "Client", FailClient)
    monkeypatch.setattr(module.httpx, "get", fail_get)
    monkeypatch.setattr(module.subprocess, "run", fail_run)

    exit_code = module.main(
        [
            "--approved-file",
            str(approved),
            "--evidence",
            str(evidence),
            "--log-root",
            str(log_root),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["error"] == "Log file must not be a symlink: freyja-test-tools.jsonl."
    assert evidence.read_text(encoding="utf-8") == evidence_payload
    assert real_log.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_tool_smoke_requires_expected_core_tool_names(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_expected_tools")
    evidence = tmp_path / "evidence.json"
    smoke = {
        "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-file", "bytes": 42},
        "safe_terminal": {"ok": True, "command": "pwd", "trace_id": "trace-terminal", "exit_code": 0, "working_dir": "freyja-os"},
        "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
        "mcp_discovery": {"ok": True, "tool": "calendar.delete_event", "trace_id": "trace-mcp"},
        "calendar_read": {"ok": True, "tool": "calendar.delete_event", "trace_id": "trace-calendar"},
        "home_assistant_query": {"ok": True, "tool": "home_assistant.service_call", "domain": "sensor", "trace_id": "trace-home"},
        "coding_workflow": {"ok": True, "tool": "shell.exec", "trace_id": "trace-coding"},
    }

    payload = module.update_evidence(evidence, smoke)
    acceptance = payload["acceptance"]

    assert "approved_file_read" in acceptance
    assert "safe_terminal" in acceptance
    assert "mcp_tool" not in acceptance
    assert "calendar_read" not in acceptance
    assert "home_assistant_query" not in acceptance
    assert "coding_workflow" not in acceptance


def test_freyja6_tool_smoke_requires_coding_workflow_alias(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_coding_alias_guard")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "coding_workflow": {
            "ok": True,
            "tool": "opencode.status",
            "trace_id": "trace-coding",
            "alias": "other-coder",
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)
    tool_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert "coding_workflow" not in payload["acceptance"]
    assert module._coding_workflow_result_ok(smoke["coding_workflow"]) is False
    assert tool_entries == [
        {
            "timestamp": "2026-09-19T00:00:00+00:00",
            "event": "tool_call",
            "trace_id": "trace-coding",
            "tool": "opencode.status",
            "status": "failed",
            "source": "freyja6-tool-smoke",
            "error_summary": "coding workflow must target freyja-core-coder",
        }
    ]
    assert writes == [
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-coding"},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_tool_smoke_requires_coding_workflow_status_payload(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_coding_status_guard")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "coding_workflow": {
            "ok": True,
            "tool": "opencode.status",
            "trace_id": "trace-coding",
            "alias": "freyja-core-coder",
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))

    assert "coding_workflow" not in payload["acceptance"]
    assert module._coding_workflow_result_ok(smoke["coding_workflow"]) is False
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "coding workflow status payload was missing"
    assert writes == [
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-coding"},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_tool_smoke_requires_strict_file_and_terminal_evidence(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_file_terminal_guard")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "approved_file": {"ok": True, "path_redacted": "private.txt", "trace_id": "trace-file"},
        "safe_terminal": {"ok": True, "command": "rm", "trace_id": "trace-terminal", "exit_code": 0},
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)
    tool_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert module._approved_file_result_ok(smoke["approved_file"]) is False
    assert module._safe_terminal_result_ok(smoke["safe_terminal"]) is False
    assert "approved_file_read" not in payload["acceptance"]
    assert "safe_terminal" not in payload["acceptance"]
    assert {entry["trace_id"]: entry["status"] for entry in tool_entries} == {
        "trace-file": "failed",
        "trace-terminal": "failed",
    }
    assert {entry["trace_id"]: entry["error_summary"] for entry in tool_entries} == {
        "trace-file": "approved file path was outside approved-files",
        "trace-terminal": "command is not in safe allowlist",
    }
    assert writes == [
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-file"},
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-terminal"},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_tool_smoke_requires_validation_traces_for_core_tool_evidence(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_trace_guard")
    smoke = {
        "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
        "mcp_discovery": {"ok": True, "tool": "status.check", "trace_id": "external-mcp"},
        "calendar_read": {"ok": True, "tool": "calendar.list_events", "trace_id": "external-calendar"},
        "home_assistant_query": {
            "ok": True,
            "tool": "home_assistant.list_states",
            "domain": "sensor",
            "trace_id": "external-home",
            "result_keys": ["ok", "states"],
            "states_count": 1,
        },
        "coding_workflow": {"ok": True, "tool": "opencode.status", "trace_id": "external-coding", "alias": "freyja-core-coder", "result_summary": "opencode status queried through Freyja Core", "status_payload_present": True, "status_keys": ["alias", "state"]},
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    acceptance = payload["acceptance"]

    assert "mcp_tool" not in acceptance
    assert "calendar_read" not in acceptance
    assert "home_assistant_query" not in acceptance
    assert "coding_workflow" not in acceptance


def test_freyja6_tool_smoke_rejects_placeholder_validation_traces(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_placeholder_trace_guard")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-..."},
        "safe_terminal": {"ok": True, "command": "pwd", "trace_id": "trace-...", "exit_code": 0},
        "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
        "mcp_discovery": {"ok": True, "tool": "status.check", "trace_id": "trace-..."},
        "calendar_read": {"ok": True, "tool": "calendar.list_events", "trace_id": "trace-..."},
        "home_assistant_query": {
            "ok": True,
            "tool": "home_assistant.list_states",
            "domain": "sensor",
            "trace_id": "trace-...",
            "result_keys": ["ok", "states"],
            "states_count": 1,
        },
        "coding_workflow": {"ok": True, "tool": "opencode.status", "trace_id": "trace-...", "alias": "freyja-core-coder", "result_summary": "opencode status queried through Freyja Core", "status_payload_present": True, "status_keys": ["alias", "state"]},
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._tool_smoke_ok(smoke) is False
    assert payload["acceptance"] == {}
    tool_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {entry["status"] for entry in tool_entries} == {"failed"}
    assert {entry["error_summary"] for entry in tool_entries} == {"trace id is not a Freyja validation trace"}
    assert writes == [
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."},
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."},
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."},
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."},
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."},
        {"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."},
    ]
    assert not (tmp_path / "logs" / "freyja-test-acceptance.jsonl").exists()


def test_freyja6_tool_smoke_requires_home_assistant_domain_scope(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_home_domain_guard")
    smoke = {
        "home_assistant_query": {
            "ok": True,
            "tool": "home_assistant.list_states",
            "domain": "sensor.kitchen_motion",
            "trace_id": "trace-home",
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)

    assert "home_assistant_query" not in payload["acceptance"]
    assert module._tool_smoke_ok(
        {
            "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-file", "bytes": 42},
            "safe_terminal": {"ok": True, "command": "pwd", "trace_id": "trace-terminal", "exit_code": 0, "working_dir": "freyja-os"},
            "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
            "mcp_discovery": {"ok": True, "tool": "status.check", "trace_id": "trace-mcp", "status_code": 200},
            "calendar_read": {"ok": True, "tool": "calendar.list_events", "trace_id": "trace-calendar", "status_code": 200},
            "home_assistant_query": smoke["home_assistant_query"],
            "coding_workflow": {"ok": True, "tool": "opencode.status", "trace_id": "trace-coding", "alias": "freyja-core-coder", "result_summary": "opencode status queried through Freyja Core", "status_payload_present": True, "status_keys": ["alias", "state"]},
        }
    ) is False


def test_freyja6_tool_smoke_requires_home_assistant_states_payload(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_home_states_guard")
    smoke = {
        "home_assistant_query": {
            "ok": True,
            "tool": "home_assistant.list_states",
            "domain": "sensor",
            "trace_id": "trace-home",
            "result_keys": ["ok"],
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)

    assert "home_assistant_query" not in payload["acceptance"]


def test_freyja6_tool_smoke_requires_nonempty_home_assistant_states(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_home_empty_states_guard")
    smoke = {
        "home_assistant_query": {
            "ok": True,
            "tool": "home_assistant.list_states",
            "domain": "sensor",
            "trace_id": "trace-home",
            "result_keys": ["ok", "states"],
            "states_count": 0,
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert "home_assistant_query" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "Home Assistant result was not domain-scoped with states"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-home"}]


def test_freyja6_tool_smoke_requires_explicit_core_ok_true() -> None:
    import httpx

    module = _load_tool_smoke_module("freyja6_tool_smoke_core_ok_true")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://core")

    result = module._core_tool_call(client, "calendar.list_events", {}, trace_id="trace-calendar")

    assert result["ok"] is False
    assert result["result_keys"] == ["status"]

    home_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True, "states": [{"entity_id": "sensor.kitchen"}]})),
        base_url="http://core",
    )
    home_result = module._core_tool_call(home_client, "home_assistant.list_states", {"domain": "sensor"}, trace_id="trace-home")
    assert home_result["ok"] is True
    assert home_result["result_keys"] == ["ok", "states"]
    assert home_result["states_count"] == 1


def test_freyja6_tool_smoke_health_requires_explicit_ok_true(monkeypatch) -> None:
    import httpx

    module = _load_tool_smoke_module("freyja6_tool_smoke_health_ok_true")
    responses = [
        httpx.Response(200, json={"service": "freyja-core-mcp"}),
        httpx.Response(200, json={"ok": True, "service": "freyja-core-mcp"}),
    ]

    def fake_get(url, timeout):
        return responses.pop(0)

    monkeypatch.setattr(module.httpx, "get", fake_get)

    ambiguous = module._http_health("http://127.0.0.1:8766/healthz", timeout=1)
    explicit = module._http_health("http://127.0.0.1:8766/healthz", timeout=1)

    assert ambiguous["ok"] is False
    assert ambiguous["service"] == "freyja-core-mcp"
    assert explicit["ok"] is True


def test_freyja6_tool_smoke_rejects_approved_file_outside_roots(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_approved_file_roots")
    private_file = tmp_path / "private.txt"
    private_file.write_text("do not read me", encoding="utf-8")

    result = module._read_approved_file(str(private_file), trace_id="trace-file")

    assert result["ok"] is False
    assert result["error"] == "Approved file must be under a Freyja 6 approved read-only root."
    assert result["path_redacted"] == "private.txt"


def test_freyja6_tool_smoke_accepts_only_configured_approved_file_roots() -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_approved_file_root_check")

    assert module._approved_file_path_allowed(Path("/srv/freyja6/approved-files/smoke.txt")) is True
    assert module._approved_file_path_allowed(Path("/workspace/approved/smoke.txt")) is True
    assert module._approved_file_path_allowed(Path("/srv/freyja6/private/smoke.txt")) is False
    assert module._approved_file_path_allowed(Path("relative/smoke.txt")) is False


def test_freyja6_tool_smoke_rejects_approved_root_symlink_escape(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_approved_file_symlink_escape")
    approved = tmp_path / "approved-files"
    approved.mkdir()
    private = tmp_path / "private.txt"
    private.write_text("do not read me", encoding="utf-8")
    link = approved / "escape.txt"
    link.symlink_to(private)
    module.APPROVED_FILE_ROOTS = (approved,)

    result = module._read_approved_file(str(link), trace_id="trace-file")

    assert result["ok"] is False
    assert result["error"] == "Approved file must be under a Freyja 6 approved read-only root."
    assert module._approved_file_path_allowed(link) is False


def test_freyja6_tool_smoke_appends_structured_logs(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_logs")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-file", "bytes": 42},
        "safe_terminal": {"ok": True, "command": "pwd", "trace_id": "trace-terminal", "exit_code": 0, "working_dir": "freyja-os"},
        "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
        "mcp_discovery": {"ok": True, "tool": "status.check", "trace_id": "trace-mcp", "status_code": 200},
        "calendar_read": {"ok": True, "tool": "calendar.list_events", "trace_id": "trace-calendar", "status_code": 200},
        "home_assistant_query": {"ok": True, "tool": "home_assistant.list_states", "domain": "sensor", "trace_id": "trace-home", "status_code": 200, "result_keys": ["ok", "states"], "states_count": 1},
        "coding_workflow": {"ok": True, "tool": "opencode.status", "trace_id": "trace-coding", "status_code": 200, "alias": "freyja-core-coder", "result_summary": "opencode status queried through Freyja Core", "status_payload_present": True, "status_keys": ["alias", "state"]},
    }

    module.append_logs(tmp_path, smoke)

    tool_entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-tools.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    acceptance_entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-acceptance.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {entry["tool"] for entry in tool_entries} == {
        "filesystem.read",
        "terminal.safe_command",
        "status.check",
        "calendar.list_events",
        "home_assistant.list_states",
        "opencode.status",
    }
    assert all(entry["event"] == "tool_call" for entry in tool_entries)
    assert {
        entry["tool"]: entry["status_code"]
        for entry in tool_entries
        if entry["tool"] in {"status.check", "calendar.list_events", "home_assistant.list_states", "opencode.status"}
    } == {
        "status.check": 200,
        "calendar.list_events": 200,
        "home_assistant.list_states": 200,
        "opencode.status": 200,
    }
    assert {entry["acceptance_id"] for entry in acceptance_entries} == {
        "approved_file_read",
        "safe_terminal",
        "mcp_tool",
        "calendar_read",
        "home_assistant_query",
        "coding_workflow",
    }


def test_freyja6_tool_smoke_refuses_symlinked_log_file(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_symlink_log")
    real_log = tmp_path / "real-tools.jsonl"
    real_log.write_text("", encoding="utf-8")
    tool_log = tmp_path / "freyja-test-tools.jsonl"
    tool_log.symlink_to(real_log)
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-file", "bytes": 42},
    }

    try:
        module.append_logs(tmp_path, smoke)
    except ValueError as exc:
        assert "Log file must not be a symlink: freyja-test-tools.jsonl." in str(exc)
    else:
        raise AssertionError("symlinked tool log should be rejected before writing")

    assert real_log.read_text(encoding="utf-8") == ""


def test_freyja6_tool_smoke_does_not_log_acceptance_for_weak_home_assistant_payload(tmp_path) -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_log_home_guard")
    smoke = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "trace_prefix": "trace-tools",
        "approved_file": {"ok": True, "path_redacted": "approved-files/smoke.txt", "trace_id": "trace-file", "bytes": 42},
        "safe_terminal": {"ok": True, "command": "pwd", "trace_id": "trace-terminal", "exit_code": 0, "working_dir": "freyja-os"},
        "core_mcp_health": {"ok": True, "service": "freyja-core-mcp"},
        "mcp_discovery": {"ok": True, "tool": "status.check", "trace_id": "trace-mcp", "status_code": 200},
        "calendar_read": {"ok": True, "tool": "calendar.list_events", "trace_id": "trace-calendar", "status_code": 200},
        "home_assistant_query": {"ok": True, "tool": "home_assistant.list_states", "domain": "sensor", "trace_id": "trace-home", "result_keys": ["ok"]},
        "coding_workflow": {"ok": True, "tool": "opencode.status", "trace_id": "trace-coding", "alias": "freyja-core-coder", "result_summary": "opencode status queried through Freyja Core", "status_payload_present": True, "status_keys": ["alias", "state"]},
    }

    module.append_logs(tmp_path, smoke)

    tool_entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-tools.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    acceptance_entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-acceptance.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(entry["tool"] == "home_assistant.list_states" and entry["status"] == "failed" for entry in tool_entries)
    assert any(entry["tool"] == "home_assistant.list_states" and entry["error_summary"] == "Home Assistant result was not domain-scoped with states" for entry in tool_entries)
    assert "home_assistant_query" not in {entry["acceptance_id"] for entry in acceptance_entries}


def test_freyja6_discord_smoke_updates_redacted_acceptance_evidence(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "channel_id_redacted": "discord-channel-...5678",
        "message_trace_id": "trace-message",
        "reply_trace_id": "trace-reply",
        "verification": "discord-api",
        "message_from_user": True,
        "reply_from_bot": True,
        "reply_references_message": True,
        "chronological": True,
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)

    assert smoke["ok"] is True
    discord = payload["acceptance"]["discord_reply"]
    assert discord["status"] == "complete"
    assert discord["captured_at"] == smoke["timestamp"]
    assert discord["source"] == "freyja6-discord-smoke"
    assert discord["evidence"]["discord_channel_id_redacted"] == "discord-channel-...5678"
    assert discord["evidence"]["message_trace_id"] == "trace-message"
    assert discord["evidence"]["reply_trace_id"] == "trace-reply"
    assert discord["evidence"]["verification_method"] == "discord-api"


def test_freyja6_discord_smoke_does_not_promote_manual_confirmation(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_manual_not_final")
    smoke = module.run_smoke(
        bot_token="",
        channel_id="123456789012345678",
        message_id="",
        reply_id="",
        message_trace_id="trace-message",
        reply_trace_id="trace-reply",
        manual_confirmation="DISCORD_REPLY_VERIFIED",
        timeout=1,
    )

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert smoke["ok"] is True
    assert smoke["verification"] == "manual-confirmed"
    assert module._discord_reply_ok(smoke) is False
    assert "discord_reply" not in payload["acceptance"]
    assert writes == []


def test_freyja6_discord_smoke_refuses_malformed_existing_evidence(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "channel_id_redacted": "discord-channel-...5678",
        "message_trace_id": "trace-message",
        "reply_trace_id": "trace-reply",
        "verification": "manual-confirmed",
    }

    try:
        module.update_evidence(evidence, smoke)
    except ValueError as exc:
        assert "acceptance must be an object" in str(exc)
    else:
        raise AssertionError("malformed evidence acceptance should be rejected before writing")


def test_freyja6_discord_smoke_cli_reports_malformed_evidence_as_json(tmp_path, capsys) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_bad_evidence_cli")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--channel-id",
            "123456789012345678",
            "--message-trace-id",
            "trace-message",
            "--reply-trace-id",
            "trace-reply",
            "--manual-confirmation",
            "DISCORD_REPLY_VERIFIED",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert "acceptance must be an object" in output["error"]


def test_freyja6_discord_smoke_cli_refuses_symlinked_evidence_before_api_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_cli_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Discord API client should not open for unsafe evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--bot-token",
            "discord-token",
            "--channel-id",
            "123456789012345678",
            "--message-id",
            "message-1",
            "--reply-id",
            "reply-1",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert output["error"] == "Live evidence file must not be a symlink."
    assert real_evidence.read_text(encoding="utf-8") == '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    assert not (tmp_path / "logs").exists()


def test_freyja6_discord_smoke_cli_refuses_malformed_evidence_before_api_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_cli_bad_evidence_api")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Discord API client should not open for malformed evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--bot-token",
            "discord-token",
            "--channel-id",
            "123456789012345678",
            "--message-id",
            "message-1",
            "--reply-id",
            "reply-1",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert "acceptance must be an object" in output["error"]
    assert not (tmp_path / "logs").exists()


def test_freyja6_discord_smoke_cli_refuses_symlinked_log_before_api_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_cli_symlink_log")
    evidence = tmp_path / "evidence.json"
    evidence_payload = '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    evidence.write_text(evidence_payload, encoding="utf-8")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    real_log = tmp_path / "real-acceptance.jsonl"
    real_log.write_text("sentinel\n", encoding="utf-8")
    (log_root / "freyja-test-acceptance.jsonl").symlink_to(real_log)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Discord API client should not open for unsafe log path")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--bot-token",
            "discord-token",
            "--channel-id",
            "123456789012345678",
            "--message-id",
            "message-1",
            "--reply-id",
            "reply-1",
            "--evidence",
            str(evidence),
            "--log-root",
            str(log_root),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert output["error"] == "Log file must not be a symlink: freyja-test-acceptance.jsonl."
    assert evidence.read_text(encoding="utf-8") == evidence_payload
    assert real_log.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_discord_smoke_appends_structured_acceptance_log(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_logs")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "channel_id_redacted": "discord-channel-...5678",
        "message_trace_id": "trace-message",
        "reply_trace_id": "trace-reply",
        "verification": "discord-api",
        "message_from_user": True,
        "reply_from_bot": True,
        "reply_references_message": True,
        "chronological": True,
    }

    writes = module.append_logs(tmp_path, smoke)

    entry = json.loads((tmp_path / "freyja-test-acceptance.jsonl").read_text(encoding="utf-8"))
    assert entry["acceptance_id"] == "discord_reply"
    assert entry["trace_id"] == "trace-reply"
    assert entry["source"] == "freyja6-discord-smoke"
    assert writes == [{"log": "freyja6/logs/freyja-test-acceptance.jsonl", "trace_id": "trace-reply"}]


def test_freyja6_discord_smoke_requires_distinct_reply_evidence_for_writes(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_write_guard")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "channel_id_redacted": "discord-channel-...5678",
        "message_trace_id": "trace-same",
        "reply_trace_id": "trace-same",
        "verification": "manual-confirmed",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert "discord_reply" not in payload["acceptance"]
    assert writes == []


def test_freyja6_discord_smoke_requires_validation_trace_ids_for_writes(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_trace_guard")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "channel_id_redacted": "discord-channel-...5678",
        "message_trace_id": "discord-message-...1111",
        "reply_trace_id": "discord-reply-...2222",
        "verification": "manual-confirmed",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert "discord_reply" not in payload["acceptance"]
    assert writes == []


def test_freyja6_discord_smoke_rejects_placeholder_trace_ids_for_writes(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_placeholder_trace_guard")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "channel_id_redacted": "discord-channel-...5678",
        "message_trace_id": "trace-...",
        "reply_trace_id": "freyja6-...",
        "verification": "manual-confirmed",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._discord_reply_ok(smoke) is False
    assert "discord_reply" not in payload["acceptance"]
    assert writes == []


def test_freyja6_discord_smoke_top_level_ok_matches_acceptance_guard(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_top_level_guard")
    smoke = module.run_smoke(
        bot_token="",
        channel_id="123456789012345678",
        message_id="",
        reply_id="",
        message_trace_id="trace-same",
        reply_trace_id="trace-same",
        manual_confirmation="DISCORD_REPLY_VERIFIED",
        timeout=1,
    )

    assert smoke["ok"] is True
    assert module._discord_reply_ok(smoke) is False
    assert (
        module.main(
            [
                "--channel-id",
                "123456789012345678",
                "--message-trace-id",
                "trace-same",
                "--reply-trace-id",
                "trace-same",
                "--manual-confirmation",
                "DISCORD_REPLY_VERIFIED",
                "--evidence",
                str(tmp_path / "evidence.json"),
                "--log-root",
                str(tmp_path / "logs"),
            ]
        )
        == 2
    )


def test_freyja6_discord_smoke_manual_confirmation_requires_explicit_traces(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_manual_trace_required")
    smoke = module.run_smoke(
        bot_token="",
        channel_id="123456789012345678",
        message_id="111122223333444455",
        reply_id="555544443333222211",
        message_trace_id="",
        reply_trace_id="",
        manual_confirmation="DISCORD_REPLY_VERIFIED",
        timeout=1,
    )

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert smoke["ok"] is False
    assert smoke["error"] == "Manual Discord confirmation requires explicit --message-trace-id and --reply-trace-id values."
    assert "discord_reply" not in payload["acceptance"]
    assert writes == []


def test_freyja6_discord_smoke_api_requires_reply_reference(monkeypatch) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_api_reference")

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path):
            if path.endswith("/111122223333444455"):
                return FakeResponse({"id": "111122223333444455", "timestamp": "2026-09-19T00:00:00+00:00"})
            return FakeResponse(
                {
                    "id": "555544443333222211",
                    "timestamp": "2026-09-19T00:01:00+00:00",
                    "author": {"bot": True},
                }
            )

    monkeypatch.setattr(module.httpx, "Client", FakeClient)

    smoke = module.run_smoke(
        bot_token="bot-token",
        channel_id="123456789012345678",
        message_id="111122223333444455",
        reply_id="555544443333222211",
        message_trace_id="",
        reply_trace_id="",
        manual_confirmation="",
        timeout=1,
    )

    assert smoke["ok"] is False
    assert smoke["reply_references_message"] is False
    assert smoke["message_trace_id"].startswith("freyja6-discord-")
    assert smoke["reply_trace_id"].startswith("freyja6-discord-")


def test_freyja6_discord_smoke_api_parses_reply_timestamp_order(monkeypatch) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_api_timestamp_order")

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path):
            if path.endswith("/111122223333444455"):
                return FakeResponse(
                    {
                        "id": "111122223333444455",
                        "timestamp": "2026-09-19T23:00:00+00:00",
                        "author": {"bot": False},
                    }
                )
            return FakeResponse(
                {
                    "id": "555544443333222211",
                    "timestamp": "2026-09-19T19:30:00-04:00",
                    "author": {"bot": True},
                    "referenced_message": {"id": "111122223333444455"},
                }
            )

    monkeypatch.setattr(module.httpx, "Client", FakeClient)

    smoke = module.run_smoke(
        bot_token="bot-token",
        channel_id="123456789012345678",
        message_id="111122223333444455",
        reply_id="555544443333222211",
        message_trace_id="",
        reply_trace_id="",
        manual_confirmation="",
        timeout=1,
    )

    assert module._reply_is_chronological("2026-09-19T23:00:00+00:00", "2026-09-19T19:30:00-04:00") is True
    assert module._reply_is_chronological("2026-09-19T23:00:00+00:00", "2026-09-19T18:30:00-04:00") is False
    assert smoke["ok"] is True
    assert smoke["message_from_user"] is True
    assert smoke["chronological"] is True
    assert module._discord_reply_ok(smoke) is True


def test_freyja6_discord_smoke_api_requires_original_message_from_user(monkeypatch) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_api_user_message")

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path):
            if path.endswith("/111122223333444455"):
                return FakeResponse(
                    {
                        "id": "111122223333444455",
                        "timestamp": "2026-09-19T00:00:00+00:00",
                        "author": {"bot": True},
                    }
                )
            return FakeResponse(
                {
                    "id": "555544443333222211",
                    "timestamp": "2026-09-19T00:01:00+00:00",
                    "author": {"bot": True},
                    "referenced_message": {"id": "111122223333444455"},
                }
            )

    monkeypatch.setattr(module.httpx, "Client", FakeClient)

    smoke = module.run_smoke(
        bot_token="bot-token",
        channel_id="123456789012345678",
        message_id="111122223333444455",
        reply_id="555544443333222211",
        message_trace_id="",
        reply_trace_id="",
        manual_confirmation="",
        timeout=1,
    )

    assert smoke["ok"] is False
    assert smoke["message_from_user"] is False
    assert smoke["reply_from_bot"] is True
    assert smoke["reply_references_message"] is True


def test_freyja6_discord_smoke_requires_verification_or_manual_confirmation(tmp_path) -> None:
    module = _load_discord_smoke_module("freyja6_discord_smoke_guard")
    smoke = module.run_smoke(
        bot_token="",
        channel_id="123456789012345678",
        message_id="111122223333444455",
        reply_id="555544443333222211",
        message_trace_id="",
        reply_trace_id="",
        manual_confirmation="",
        timeout=1,
    )

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)

    assert smoke["ok"] is False
    assert "discord_reply" not in payload["acceptance"]


def test_freyja6_tool_smoke_redacts_approved_paths() -> None:
    module = _load_tool_smoke_module("freyja6_tool_smoke_redaction")

    assert module._redact_path(Path("/srv/freyja6/approved-files/smoke.txt")) == "approved-files/smoke.txt"
    assert module._redact_path(Path("/Users/freyja/private.txt")) == "private.txt"


def test_freyja6_calendar_write_smoke_requires_explicit_approval() -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_approval")

    result = module.run_smoke(
        core_url="http://127.0.0.1:8510",
        calendar_id="family-redacted",
        base_date="2026-09-19",
        start_time="09:00:00",
        duration_minutes=60,
        approval="",
        timeout=1,
    )

    assert result["ok"] is False
    assert "approval" in result["error"]


def test_freyja6_calendar_write_smoke_rejects_invalid_inputs_before_core_call() -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_input_guard")

    bad_base_date = module.run_smoke(
        core_url="http://127.0.0.1:8510",
        calendar_id="family-redacted",
        base_date="09/19/2026",
        start_time="09:00:00",
        duration_minutes=60,
        approval="CREATE_BASEMENT_CLEANUP_TEST_EVENT",
        timeout=1,
    )
    bad_start = module.run_smoke(
        core_url="http://127.0.0.1:8510",
        calendar_id="family-redacted",
        base_date="2026-09-19",
        start_time="9:00",
        duration_minutes=60,
        approval="CREATE_BASEMENT_CLEANUP_TEST_EVENT",
        timeout=1,
    )
    bad_duration = module.run_smoke(
        core_url="http://127.0.0.1:8510",
        calendar_id="family-redacted",
        base_date="2026-09-19",
        start_time="09:00:00",
        duration_minutes=1440,
        approval="CREATE_BASEMENT_CLEANUP_TEST_EVENT",
        timeout=1,
    )

    assert bad_base_date == {"ok": False, "error": "--base-date must be an ISO date in YYYY-MM-DD form."}
    assert bad_start == {"ok": False, "error": "--start-time must use HH:MM:SS."}
    assert bad_duration == {"ok": False, "error": "--duration-minutes must be between 1 and 240."}


def test_freyja6_calendar_write_smoke_requires_resolved_saturday() -> None:
    import httpx

    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_resolved_saturday")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["tool"])
        return httpx.Response(200, json={"ok": True, "date": "2026-09-20"})

    original_client = module.httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    module.httpx.Client = fake_client
    try:
        result = module.run_smoke(
            core_url="http://127.0.0.1:8510",
            calendar_id="family-redacted",
            base_date="2026-09-19",
            start_time="09:00:00",
            duration_minutes=60,
            approval="CREATE_BASEMENT_CLEANUP_TEST_EVENT",
            timeout=1,
        )
    finally:
        module.httpx.Client = original_client

    assert result["ok"] is False
    assert result["error"] == "Resolved date must be an ISO Saturday."
    assert calls == ["calendar.resolve_date"]


def test_freyja6_calendar_write_smoke_updates_acceptance_evidence(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_evidence")
    evidence = tmp_path / "evidence.json"
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "status_code": 200,
            "event": {"event_id": "created-1", "title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00"},
        },
    }

    payload = module.update_evidence(evidence, smoke)

    calendar = payload["acceptance"]["calendar_create_event"]
    assert calendar["status"] == "complete"
    assert calendar["source"] == "freyja6-calendar-write-smoke"
    assert calendar["captured_at"]
    assert calendar["evidence"] == {
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "tool_trace_id": "trace-create",
        "created_event_id": "event-id-crea...ed-1",
    }


def test_freyja6_calendar_write_smoke_refuses_malformed_existing_evidence(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "status_code": 200,
            "event": {"event_id": "created-1", "title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00"},
        },
    }

    try:
        module.update_evidence(evidence, smoke)
    except ValueError as exc:
        assert "acceptance must be an object" in str(exc)
    else:
        raise AssertionError("malformed evidence acceptance should be rejected before writing")


def test_freyja6_calendar_write_smoke_cli_refuses_symlinked_evidence_before_core_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_cli_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("calendar core client should not open for unsafe evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--calendar-id",
            "family-calendar",
            "--base-date",
            "2026-09-17",
            "--approval",
            "CREATE_BASEMENT_CLEANUP_TEST_EVENT",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["error"] == "Live evidence file must not be a symlink."
    assert real_evidence.read_text(encoding="utf-8") == '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    assert not (tmp_path / "logs").exists()


def test_freyja6_calendar_write_smoke_cli_refuses_malformed_evidence_before_core_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_cli_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("calendar core client should not open for malformed evidence")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--calendar-id",
            "family-calendar",
            "--base-date",
            "2026-09-17",
            "--approval",
            "CREATE_BASEMENT_CLEANUP_TEST_EVENT",
            "--evidence",
            str(evidence),
            "--log-root",
            str(tmp_path / "logs"),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert "acceptance must be an object" in rendered["error"]
    assert not (tmp_path / "logs").exists()


def test_freyja6_calendar_write_smoke_cli_refuses_symlinked_log_before_core_call(tmp_path, monkeypatch, capsys) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_cli_symlink_log")
    evidence = tmp_path / "evidence.json"
    evidence_payload = '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    evidence.write_text(evidence_payload, encoding="utf-8")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    real_log = tmp_path / "real-tools.jsonl"
    real_log.write_text("sentinel\n", encoding="utf-8")
    (log_root / "freyja-test-tools.jsonl").symlink_to(real_log)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("calendar core client should not open for unsafe log path")

    monkeypatch.setattr(module.httpx, "Client", FailClient)

    exit_code = module.main(
        [
            "--calendar-id",
            "family-calendar",
            "--base-date",
            "2026-09-17",
            "--approval",
            "CREATE_BASEMENT_CLEANUP_TEST_EVENT",
            "--evidence",
            str(evidence),
            "--log-root",
            str(log_root),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["error"] == "Log file must not be a symlink: freyja-test-tools.jsonl."
    assert evidence.read_text(encoding="utf-8") == evidence_payload
    assert real_log.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_calendar_write_smoke_requires_create_tool_result_for_evidence(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_tool_guard")
    evidence = tmp_path / "evidence.json"
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {"ok": True, "tool": "calendar.delete_event", "trace_id": "trace-create"},
    }

    payload = module.update_evidence(evidence, smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "calendar write smoke used unexpected tool"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]


def test_freyja6_calendar_write_smoke_requires_created_event_to_match_resolved_date(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_date_guard")
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "event": {"title": "Basement cleanup", "start": "2026-09-20T09:00:00+00:00"},
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "created event did not match the resolved acceptance date"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]
    assert module._calendar_create_ok(smoke) is False


def test_freyja6_calendar_write_smoke_rejects_wrong_returned_calendar(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_calendar_guard")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "calendar_id_redacted": "calendar-...1234",
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "event": {
                "event_id": "created-1",
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00",
                "calendar_id": "family-calendar-9999",
            },
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._created_event_matches_date(
        {"event_id": "created-1", "title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00", "calendar_id": "family-calendar-1234"},
        "2026-09-19",
        "calendar-...1234",
    ) is True
    assert module._calendar_create_ok(smoke) is False
    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "created event did not match the resolved acceptance date"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]


def test_freyja6_calendar_write_smoke_requires_timezone_aware_created_event_start(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_event_start_timezone")
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "event": {"title": "Basement cleanup", "start": "2026-09-19T09:00:00"},
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._created_event_matches_date({"event_id": "created-1", "title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00"}, "2026-09-19") is True
    assert module._created_event_matches_date(smoke["create"]["event"], "2026-09-19") is False
    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "created event did not match the resolved acceptance date"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]


def test_freyja6_calendar_write_smoke_requires_created_event_duration(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_event_duration")
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "duration_minutes": 60,
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "event": {
                "title": "Basement cleanup",
                "start": "2026-09-19T09:00:00+00:00",
                "end": "2026-09-19T12:00:00+00:00",
            },
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._created_event_matches_date(
        {
            "event_id": "created-1",
            "title": "Basement cleanup",
            "start": "2026-09-19T09:00:00+00:00",
            "end": "2026-09-19T10:00:00+00:00",
        },
        "2026-09-19",
        duration_minutes=60,
    ) is True
    assert module._created_event_matches_date(smoke["create"]["event"], "2026-09-19", duration_minutes=60) is False
    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "created event did not match the resolved acceptance date"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]


def test_freyja6_calendar_write_smoke_requires_created_event_payload(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_event_payload_guard")
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "created event did not match the resolved acceptance date"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]


def test_freyja6_calendar_write_smoke_requires_created_event_identifier(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_event_identifier_guard")
    smoke = {
        "ok": True,
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "event": {"title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00"},
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._created_event_matches_date(smoke["create"]["event"], "2026-09-19") is False
    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "created event did not match the resolved acceptance date"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-create"}]


def test_freyja6_calendar_write_smoke_rejects_placeholder_trace(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_placeholder_trace")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-...",
            "event": {"event_id": "created-1", "title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00"},
        },
    }

    payload = module.update_evidence(tmp_path / "evidence.json", smoke)
    writes = module.append_logs(tmp_path / "logs", smoke)

    assert module._calendar_create_ok(smoke) is False
    assert "calendar_create_event" not in payload["acceptance"]
    tool_entry = json.loads((tmp_path / "logs" / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["status"] == "failed"
    assert tool_entry["error_summary"] == "trace id is not a Freyja validation trace"
    assert writes == [{"log": "freyja6/logs/freyja-test-tools.jsonl", "trace_id": "trace-..."}]


def test_freyja6_calendar_write_smoke_requires_explicit_core_ok_true() -> None:
    import httpx

    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_core_ok_true")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"date": "2026-09-19"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://core")

    result = module._core_tool_call(client, "calendar.resolve_date", {"phrase": "this Saturday"}, trace_id="trace-calendar")

    assert result["ok"] is False
    assert result["date"] == "2026-09-19"


def test_freyja6_calendar_write_smoke_appends_structured_logs(tmp_path) -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_logs")
    smoke = {
        "ok": True,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "event_title": "Basement cleanup",
        "event_date": "2026-09-19",
        "create": {
            "ok": True,
            "tool": "calendar.create_event",
            "trace_id": "trace-create",
            "status_code": 200,
            "event": {"event_id": "created-1", "title": "Basement cleanup", "start": "2026-09-19T09:00:00+00:00", "end": "2026-09-19T10:00:00+00:00"},
        },
    }

    module.append_logs(tmp_path, smoke)

    tool_entry = json.loads((tmp_path / "freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    acceptance_entry = json.loads((tmp_path / "freyja-test-acceptance.jsonl").read_text(encoding="utf-8"))
    assert tool_entry["tool"] == "calendar.create_event"
    assert tool_entry["trace_id"] == "trace-create"
    assert tool_entry["status_code"] == 200
    assert acceptance_entry["acceptance_id"] == "calendar_create_event"
    assert acceptance_entry["source"] == "freyja6-calendar-write-smoke"


def test_freyja6_calendar_write_smoke_computes_event_end_time() -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_end_time")

    assert module._end_time("2026-09-19T09:00:00+00:00", 60) == "2026-09-19T10:00:00+00:00"


def test_freyja6_calendar_write_smoke_uses_local_calendar_time() -> None:
    module = _load_calendar_write_smoke_module("freyja6_calendar_write_smoke_local_time")

    start, end = module._event_window("2026-09-26", "09:00:00", 60)

    assert start == "2026-09-26T09:00:00-04:00"
    assert end == "2026-09-26T10:00:00-04:00"


def test_freyja6_prepare_restart_evidence_seeds_session_fact_and_redacted_metadata(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")

    report = module.prepare(
        hermes_data=hermes,
        session_id="session-validation",
        stored_fact_label="basement-cleanup-fact",
    )
    payload = module.update_evidence(tmp_path / "evidence.json", report)

    assert module._prepare_report_ok(report) is True
    assert report["identity_sha256_before"] == module._sha256_file(identity)
    assert (hermes / "agents/freyja-test/sessions/session-validation").exists()
    fact = hermes / "agents/freyja-test/memory/private/freyja6-validation-fact.json"
    assert "basement-cleanup-fact" in fact.read_text(encoding="utf-8")
    prepared = payload["restart_validation_prepared"]
    assert prepared["identity_before"] == "sha256:" + report["identity_sha256_before"]
    assert prepared["session_id"] == "session-validation"
    rendered = str(payload)
    assert str(tmp_path) not in rendered
    assert "hermes/agents/freyja-test/memory/private/freyja6-validation-fact.json" in rendered


def test_freyja6_prepare_restart_evidence_refuses_wrong_existing_evidence_artifact(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_wrong_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-acceptance-status","acceptance":{}}\n',
        encoding="utf-8",
    )
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "identity_sha256_before": "a" * 64,
        "session_id": "session-validation",
        "stored_fact_label": "basement-cleanup-fact",
        "memory_fact_file_redacted": "hermes/agents/freyja-test/memory/private/freyja6-validation-fact.json",
    }

    try:
        module.update_evidence(evidence, report)
    except ValueError as exc:
        assert "freyja6-live-evidence schema_version 1.0" in str(exc)
    else:
        raise AssertionError("wrong evidence artifact type should be rejected before writing")


def test_freyja6_prepare_restart_evidence_refuses_symlinked_existing_evidence(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_symlink_evidence")
    real_evidence = tmp_path / "real-evidence.json"
    real_evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n',
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(real_evidence)
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "identity_sha256_before": "a" * 64,
        "session_id": "session-validation",
        "stored_fact_label": "basement-cleanup-fact",
        "memory_fact_file_redacted": "hermes/agents/freyja-test/memory/private/freyja6-validation-fact.json",
    }

    try:
        module.update_evidence(evidence, report)
    except ValueError as exc:
        assert "Live evidence file must not be a symlink." in str(exc)
    else:
        raise AssertionError("symlinked live evidence should be rejected before writing")

    assert json.loads(real_evidence.read_text(encoding="utf-8"))["acceptance"] == {}


def test_freyja6_prepare_restart_evidence_cli_reports_bad_evidence_as_json(tmp_path, capsys) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_bad_evidence_cli")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--hermes-data",
            str(hermes),
            "--evidence",
            str(evidence),
            "--session-id",
            "session-validation",
            "--stored-fact-label",
            "basement-cleanup-fact",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert output["evidence_updated"] is False
    assert "acceptance must be an object" in output["error"]
    assert not (hermes / "agents/freyja-test/sessions/session-validation").exists()
    assert not (hermes / "agents/freyja-test/memory/private/freyja6-validation-fact.json").exists()


def test_freyja6_prepare_restart_evidence_requires_memory_fact_label(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_requires_fact_label")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")

    report = module.prepare(
        hermes_data=hermes,
        session_id="session-validation",
        stored_fact_label="",
    )

    assert report["identity_sha256_before"]
    assert module._prepare_report_ok(report) is False


def test_freyja6_prepare_restart_evidence_rejects_unsafe_identifiers_before_writes(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_unsafe_identifier")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")

    report = module.prepare(
        hermes_data=hermes,
        session_id="../escaped-session",
        stored_fact_label="basement cleanup; reboot",
    )

    assert module._prepare_report_ok(report) is False
    assert report["writes"] == []
    assert "session_id must be a non-empty local identifier" in report["input_failures"][0]
    assert "stored_fact_label must be a non-empty local identifier" in report["input_failures"][1]
    assert not (hermes / "agents/freyja-test/sessions").exists()
    assert not (hermes / "agents/freyja-test/memory").exists()
    assert not (tmp_path / "escaped-session").exists()
    assert report["next_restart_command"] == ""


def test_freyja6_prepare_restart_evidence_rejects_symlinked_marker_even_with_force(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_symlink_marker")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    session = hermes / "agents/freyja-test/sessions/session-validation"
    identity.parent.mkdir(parents=True)
    session.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")
    real_session = tmp_path / "legacy-session.json"
    real_session.write_text("legacy session\n", encoding="utf-8")
    session.symlink_to(real_session)

    report = module.prepare(
        hermes_data=hermes,
        session_id="session-validation",
        stored_fact_label="basement-cleanup-fact",
        force=True,
    )

    assert module._prepare_report_ok(report) is False
    assert report["writes"] == []
    assert {"label": "session_marker", "path_redacted": "hermes/agents/freyja-test/sessions/session-validation", "reason": "must not be a symlink"} in report["marker_failures"]
    assert real_session.read_text(encoding="utf-8") == "legacy session\n"


def test_freyja6_prepare_restart_evidence_rejects_memory_fact_directory(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_memory_fact_directory")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    fact = hermes / "agents/freyja-test/memory/private/freyja6-validation-fact.json"
    identity.parent.mkdir(parents=True)
    fact.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")

    report = module.prepare(
        hermes_data=hermes,
        session_id="session-validation",
        stored_fact_label="basement-cleanup-fact",
    )

    assert module._prepare_report_ok(report) is False
    assert report["writes"] == []
    assert {"label": "memory_fact", "path_redacted": "hermes/agents/freyja-test/memory/private/freyja6-validation-fact.json", "reason": "must be a regular file"} in report["marker_failures"]


def test_freyja6_prepare_restart_evidence_does_not_update_evidence_when_not_ready(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_no_bad_evidence")
    hermes = tmp_path / "hermes"
    evidence = tmp_path / "evidence.json"
    identity = hermes / "agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")

    exit_code = module.main(
        [
            "--hermes-data",
            str(hermes),
            "--evidence",
            str(evidence),
            "--session-id",
            "session-validation",
            "--stored-fact-label",
            "",
        ]
    )

    assert exit_code == 2
    assert not evidence.exists()


def test_freyja6_prepare_restart_evidence_preserves_existing_markers_without_force(tmp_path) -> None:
    module = _load_prepare_restart_module("freyja6_prepare_restart_preserve")
    hermes = tmp_path / "hermes"
    identity = hermes / "agents/freyja-test/identity.md"
    session = hermes / "agents/freyja-test/sessions/session-validation"
    fact = hermes / "agents/freyja-test/memory/private/freyja6-validation-fact.json"
    identity.parent.mkdir(parents=True)
    session.parent.mkdir(parents=True)
    fact.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")
    session.write_text("existing session\n", encoding="utf-8")
    fact.write_text('{"label":"existing-fact"}\n', encoding="utf-8")

    report = module.prepare(
        hermes_data=hermes,
        session_id="session-validation",
        stored_fact_label="basement-cleanup-fact",
    )

    assert session.read_text(encoding="utf-8") == "existing session\n"
    assert fact.read_text(encoding="utf-8") == '{"label":"existing-fact"}\n'
    assert {write["action"] for write in report["writes"]} == {"preserved"}


def test_freyja6_restart_evidence_updates_persistence_memory_and_reboot(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence")
    hermes = tmp_path / "hermes"
    log_root = tmp_path / "logs"
    agent = hermes / "agents/freyja-test"
    identity = agent / "identity.md"
    session = agent / "sessions/session-1"
    fact = agent / "memory/private/freyja6-validation-fact.json"
    identity.parent.mkdir(parents=True)
    session.parent.mkdir(parents=True)
    fact.parent.mkdir(parents=True)
    log_root.mkdir()
    identity.write_text("# Freyja Test\n", encoding="utf-8")
    session.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "type": "freyja6-validation-session-marker",
                "agent_id": "freyja-test",
                "session_id": "session-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fact.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "type": "freyja6-validation-memory-fact",
                "agent_id": "freyja-test",
                "label": "basement-cleanup-fact",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (log_root / "freyja-test-tools.jsonl").write_text("", encoding="utf-8")
    (log_root / "freyja-test-model-calls.jsonl").write_text("", encoding="utf-8")
    before_hash = module._sha256_file(identity)

    report = module.collect_evidence(
        hermes_data=hermes,
        log_root=log_root,
        before_identity_sha256="sha256:" + before_hash,
        session_id="session-1",
        stored_fact_label="basement-cleanup-fact",
        memory_recall_trace_id="trace-memory-recall",
        container_status="running (healthy)",
        reboot_start="2026-09-19T10:00:00+00:00",
        reboot_end="2026-09-19T10:03:00+00:00",
        discord_reply_trace_id="trace-discord-after-reboot",
        discord_reply_verification="discord-api",
    )
    payload = module.update_evidence(tmp_path / "evidence.json", report)

    acceptance = payload["acceptance"]
    assert acceptance["restart_identity_session"]["evidence"]["identity_before"] == "sha256:" + before_hash
    assert acceptance["restart_identity_session"]["evidence"]["session_restored"] is True
    assert acceptance["restart_identity_session"]["source"] == "freyja6-restart-evidence"
    assert acceptance["restart_identity_session"]["captured_at"] == report["timestamp"]
    assert acceptance["remember_fact"]["evidence"]["stored_fact_label"] == "basement-cleanup-fact"
    assert acceptance["remember_fact"]["evidence"]["recall_trace_id"] == "trace-memory-recall"
    assert acceptance["remember_fact"]["evidence"]["memory_provider"] == "hermes-native"
    assert acceptance["remember_fact"]["source"] == "freyja6-restart-evidence"
    assert acceptance["atlas_reboot_return"]["evidence"] == {
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-discord-after-reboot",
        "discord_reply_after_reboot_verification": "discord-api",
    }
    assert acceptance["atlas_reboot_return"]["captured_at"] == report["timestamp"]


def test_freyja6_restart_evidence_refuses_malformed_existing_evidence(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_before_sha256": "a" * 64,
        "identity_after_sha256": "a" * 64,
        "identity_matches_before": True,
        "session_restored": True,
    }

    try:
        module.update_evidence(evidence, report)
    except ValueError as exc:
        assert "acceptance must be an object" in str(exc)
    else:
        raise AssertionError("malformed evidence acceptance should be rejected before writing")


def test_freyja6_restart_evidence_cli_refuses_malformed_evidence_before_collection(tmp_path, monkeypatch, capsys) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_cli_bad_evidence")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":[]}\n',
        encoding="utf-8",
    )

    def fail_collect(**kwargs):
        raise AssertionError("restart evidence collection should not run for malformed evidence")

    monkeypatch.setattr(module, "collect_evidence", fail_collect)

    exit_code = module.main(["--evidence", str(evidence), "--log-root", str(tmp_path / "logs")])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert "acceptance must be an object" in output["error"]
    assert not (tmp_path / "logs").exists()


def test_freyja6_restart_evidence_cli_refuses_symlinked_log_before_collection(tmp_path, monkeypatch, capsys) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_cli_symlink_log")
    evidence = tmp_path / "evidence.json"
    evidence_payload = '{"schema_version":"1.0","report_type":"freyja6-live-evidence","acceptance":{}}\n'
    evidence.write_text(evidence_payload, encoding="utf-8")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    real_log = tmp_path / "real-acceptance.jsonl"
    real_log.write_text("sentinel\n", encoding="utf-8")
    (log_root / "freyja-test-acceptance.jsonl").symlink_to(real_log)

    def fail_collect(**kwargs):
        raise AssertionError("restart evidence collection should not run for unsafe log path")

    monkeypatch.setattr(module, "collect_evidence", fail_collect)

    exit_code = module.main(["--evidence", str(evidence), "--log-root", str(log_root)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert output["error"] == "Log file must not be a symlink: freyja-test-acceptance.jsonl."
    assert evidence.read_text(encoding="utf-8") == evidence_payload
    assert real_log.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_restart_evidence_appends_structured_acceptance_logs(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_logs")
    identity_hash = "a" * 64
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_before_sha256": identity_hash,
        "identity_after_sha256": identity_hash,
        "identity_matches_before": True,
        "session_restored": True,
        "stored_fact_label": "basement-cleanup-fact",
        "memory_provider": "hermes-native",
        "memory_fact_present": True,
        "memory_fact_recalled": True,
        "memory_recall_trace_id": "trace-memory-recall",
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-discord-after-reboot",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    writes = module.append_logs(tmp_path, report)

    entries = [
        json.loads(line)
        for line in (tmp_path / "freyja-test-acceptance.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {entry["acceptance_id"] for entry in entries} == {
        "restart_identity_session",
        "remember_fact",
        "atlas_reboot_return",
    }
    assert {entry["acceptance_id"]: entry["trace_id"] for entry in entries} == {
        "restart_identity_session": "trace-restart",
        "remember_fact": "trace-memory-recall",
        "atlas_reboot_return": "trace-discord-after-reboot",
    }
    assert {write["acceptance_id"] for write in writes} == {entry["acceptance_id"] for entry in entries}


def test_freyja6_restart_evidence_does_not_log_boolean_only_restart_identity(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_no_boolean_restart")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": True,
        "session_restored": True,
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert module._restart_identity_ok(report) is False
    assert "restart_identity_session" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_top_level_ok_requires_all_restart_acceptance_items() -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_top_level_ok")
    identity_hash = "a" * 64
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_before_sha256": identity_hash,
        "identity_after_sha256": identity_hash,
        "identity_matches_before": True,
        "session_restored": True,
        "stored_fact_label": "basement-cleanup-fact",
        "memory_provider": "hermes-native",
        "memory_fact_present": True,
        "memory_fact_recalled": True,
        "memory_recall_trace_id": "trace-memory-recall",
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-discord-after-reboot",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    assert module._restart_report_ok(report, {}) is True

    report["memory_fact_recalled"] = False
    assert module._restart_report_ok(report, {}) is False


def test_freyja6_restart_evidence_requires_api_verified_reboot_reply(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_reboot_reply_api")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "memory_fact_present": False,
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-discord-after-reboot",
        "discord_reply_after_reboot_verification": "manual-confirmed",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert module._reboot_return_ok(report) is False
    assert "atlas_reboot_return" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_requires_matching_identity_and_session(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_guard")
    agent = tmp_path / "hermes/agents/freyja-test"
    identity = agent / "identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("# Changed Identity\n", encoding="utf-8")

    report = module.collect_evidence(
        hermes_data=tmp_path / "hermes",
        log_root=tmp_path / "logs",
        before_identity_sha256="0" * 64,
    )
    payload = module.update_evidence(tmp_path / "evidence.json", report)

    assert report["identity_matches_before"] is False
    assert report["session_restored"] is False
    assert "restart_identity_session" not in payload["acceptance"]


def test_freyja6_restart_evidence_rejects_loose_session_and_fact_markers(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_strict_markers")
    agent = tmp_path / "hermes/agents/freyja-test"
    identity = agent / "identity.md"
    session = agent / "sessions/session-1"
    fact = agent / "memory/private/freyja6-validation-fact.json"
    identity.parent.mkdir(parents=True)
    session.parent.mkdir(parents=True)
    fact.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")
    session.write_text("session restored\n", encoding="utf-8")
    fact.write_text('{"label":"basement-cleanup-fact"}\n', encoding="utf-8")
    before_hash = module._sha256_file(identity)

    report = module.collect_evidence(
        hermes_data=tmp_path / "hermes",
        log_root=tmp_path / "logs",
        before_identity_sha256=before_hash,
        session_id="session-1",
        stored_fact_label="basement-cleanup-fact",
        reboot_start="2026-09-19T10:03:00+00:00",
        reboot_end="2026-09-19T10:00:00+00:00",
        container_status="running (healthy)",
        discord_reply_trace_id="trace-discord-after-reboot",
    )
    payload = module.update_evidence(tmp_path / "evidence.json", report)

    assert report["identity_matches_before"] is True
    assert report["session_restored"] is False
    assert report["memory_fact_present"] is False
    assert report["reboot_window"] == ""
    assert "restart_identity_session" not in payload["acceptance"]
    assert "remember_fact" not in payload["acceptance"]
    assert "atlas_reboot_return" not in payload["acceptance"]


def test_freyja6_restart_evidence_requires_memory_recall_trace(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_memory_recall")
    agent = tmp_path / "hermes/agents/freyja-test"
    identity = agent / "identity.md"
    fact = agent / "memory/private/freyja6-validation-fact.json"
    identity.parent.mkdir(parents=True)
    fact.parent.mkdir(parents=True)
    identity.write_text("# Freyja Test\n", encoding="utf-8")
    fact.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "type": "freyja6-validation-memory-fact",
                "agent_id": "freyja-test",
                "label": "basement-cleanup-fact",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.collect_evidence(
        hermes_data=tmp_path / "hermes",
        log_root=tmp_path / "logs",
        stored_fact_label="basement-cleanup-fact",
        memory_recall_trace_id="raw-recall",
    )
    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert report["memory_fact_present"] is True
    assert report["memory_fact_recalled"] is False
    assert "remember_fact" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_rejects_unsafe_memory_fact_label(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_unsafe_fact_label")
    agent = tmp_path / "hermes/agents/freyja-test"
    fact = agent / "memory/private/freyja6-validation-fact.json"
    fact.parent.mkdir(parents=True)
    fact.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "type": "freyja6-validation-memory-fact",
                "agent_id": "freyja-test",
                "label": "../basement cleanup",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.collect_evidence(
        hermes_data=tmp_path / "hermes",
        log_root=tmp_path / "logs",
        stored_fact_label="../basement cleanup",
        memory_recall_trace_id="trace-memory-recall",
    )
    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert report["memory_fact_present"] is False
    assert module._remember_fact_ok(report) is False
    assert "remember_fact" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_rejects_memory_recall_reusing_restart_trace(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_memory_restart_trace")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "stored_fact_label": "basement-cleanup-fact",
        "memory_provider": "hermes-native",
        "memory_fact_present": True,
        "memory_fact_recalled": True,
        "memory_recall_trace_id": "trace-restart",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert "remember_fact" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_requires_validation_trace_for_reboot_return(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_reboot_trace")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "memory_fact_present": False,
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "reply-raw",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert "atlas_reboot_return" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_rejects_placeholder_traces(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_placeholder_trace_guard")
    identity_hash = "a" * 64
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-...",
        "identity_before_sha256": identity_hash,
        "identity_after_sha256": identity_hash,
        "identity_matches_before": True,
        "session_restored": True,
        "stored_fact_label": "basement-cleanup-fact",
        "memory_provider": "hermes-native",
        "memory_fact_present": True,
        "memory_fact_recalled": True,
        "memory_recall_trace_id": "freyja6-...",
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-...",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert module._restart_identity_ok(report) is False
    assert module._remember_fact_ok(report) is False
    assert module._reboot_return_ok(report) is False
    assert payload["acceptance"] == {}
    assert writes == []


def test_freyja6_restart_evidence_rejects_reboot_reply_reusing_restart_trace(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_reboot_restart_trace")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "memory_fact_present": False,
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-restart",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert "atlas_reboot_return" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_rejects_reboot_reply_reusing_initial_discord_trace(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_reboot_initial_discord_trace")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-live-evidence",
                "acceptance": {
                    "discord_reply": {
                        "status": "complete",
                        "captured_at": "2026-09-19T00:00:00+00:00",
                        "source": "freyja6-discord-smoke",
                        "evidence": {
                            "discord_channel_id_redacted": "discord-channel-test",
                            "message_trace_id": "trace-message",
                            "reply_trace_id": "trace-initial-reply",
                            "verification_method": "discord-api",
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "memory_fact_present": False,
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-initial-reply",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    payload = module.update_evidence(evidence, report)
    writes = module.append_logs(tmp_path / "logs", report, json.loads(evidence.read_text(encoding="utf-8")))

    assert "atlas_reboot_return" not in payload["acceptance"]
    assert all(write.get("acceptance_id") != "atlas_reboot_return" for write in writes)


def test_freyja6_restart_evidence_rejects_negative_container_health(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_negative_health")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "memory_fact_present": False,
        "memory_fact_recalled": False,
        "reboot_window": "2026-09-19T10:00:00+00:00/2026-09-19T10:03:00+00:00",
        "container_status_after": "not healthy",
        "discord_reply_after_reboot": "trace-discord-after-reboot",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert module._container_is_ok("not healthy") is False
    assert module._container_is_ok("running (healthy)") is True
    assert "atlas_reboot_return" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_requires_timezone_aware_reboot_window(tmp_path) -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_reboot_window_timezone")
    report = {
        "timestamp": "2026-09-19T00:00:00+00:00",
        "restart_trace_id": "trace-restart",
        "identity_matches_before": False,
        "session_restored": False,
        "memory_fact_present": False,
        "memory_fact_recalled": False,
        "reboot_window": module._reboot_window("2026-09-19T10:00:00", "2026-09-19T10:03:00"),
        "container_status_after": "running (healthy)",
        "discord_reply_after_reboot": "trace-discord-after-reboot",
        "discord_reply_after_reboot_verification": "discord-api",
    }

    payload = module.update_evidence(tmp_path / "evidence.json", report)
    writes = module.append_logs(tmp_path / "logs", report)

    assert report["reboot_window"] == ""
    assert module._reboot_window("2026-09-19T10:00:00+00:00", "2026-09-19T10:03:00+00:00")
    assert "atlas_reboot_return" not in payload["acceptance"]
    assert writes == []


def test_freyja6_restart_evidence_rejects_future_reboot_window() -> None:
    module = _load_restart_evidence_module("freyja6_restart_evidence_future_reboot_window")

    assert module._reboot_window("2999-09-19T10:00:00+00:00", "2999-09-19T10:03:00+00:00") == ""


def test_freyja6_bootstrap_creates_identity_memory_logs_and_approved_file(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.bootstrap(env_file=env_file)

    identity = root / "hermes/agents/freyja-test/identity.md"
    assert report["ok"] is True
    assert report["status"] == "pass"
    assert identity.read_text(encoding="utf-8").startswith("# Freyja Test")
    assert (root / "hermes/agents/freyja-test/sessions").is_dir()
    assert (root / "hermes/agents/freyja-test/memory/private").is_dir()
    assert (root / "approved/smoke.txt").read_text(encoding="utf-8").startswith("Freyja 6 approved")
    assert (root / "logs/freyja-test-tools.jsonl").exists()
    assert report["identity_file"] == str(identity)


def test_freyja6_bootstrap_preserves_existing_identity_without_force(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_preserve")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    identity = root / "hermes/agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    identity.write_text("existing identity\n", encoding="utf-8")

    module.bootstrap(env_file=env_file)

    assert identity.read_text(encoding="utf-8") == "existing identity\n"


def test_freyja6_bootstrap_rejects_symlinked_seed_target_even_with_force(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_symlink_seed")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    identity = root / "hermes/agents/freyja-test/identity.md"
    identity.parent.mkdir(parents=True)
    real_identity = tmp_path / "legacy-identity.md"
    real_identity.write_text("legacy identity\n", encoding="utf-8")
    identity.symlink_to(real_identity)

    report = module.bootstrap(env_file=env_file, force=True)

    seed_check = next(check for check in report["checks"] if check["id"] == "seed_targets")
    assert report["ok"] is False
    assert report["writes"] == []
    assert {"label": "identity", "path": str(identity), "reason": "must not be a symlink"} in seed_check["failures"]
    assert real_identity.read_text(encoding="utf-8") == "legacy identity\n"


def test_freyja6_bootstrap_rejects_log_seed_directory(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_log_seed_directory")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    log_path = root / "logs/freyja-test-tools.jsonl"
    log_path.mkdir(parents=True)

    report = module.bootstrap(env_file=env_file)

    seed_check = next(check for check in report["checks"] if check["id"] == "seed_targets")
    assert report["ok"] is False
    assert report["writes"] == []
    assert {"label": "freyja-test-tools.jsonl", "path": str(log_path), "reason": "must be a regular file"} in seed_check["failures"]


def test_freyja6_bootstrap_requires_explicit_env_file_before_host_writes(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_requires_env")
    output = tmp_path / "bootstrap.json"

    exit_code = module.main(["--env-file", str(tmp_path / "missing.env"), "--output", str(output)])
    report = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert report["ok"] is False
    assert report["status"] == "fail"
    assert report["created_dirs"] == []
    assert report["writes"] == []
    assert next(check for check in report["checks"] if check["id"] == "env_file")["status"] == "fail"


def test_freyja6_bootstrap_has_no_example_env_fallback() -> None:
    source = (ROOT / "scripts/freyja6-bootstrap-atlas.py").read_text(encoding="utf-8")

    assert "EXAMPLE_ENV_FILE" not in source
    assert "env_path if env_path.exists()" not in source


def test_freyja6_bootstrap_rejects_unsafe_or_placeholder_roots(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_unsafe_roots")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FREYJA6_APPROVED_FILES_ROOT=/srv",
                "FREYJA6_LOG_ROOT=/tmp/logs",
                "FREYJA6_HERMES_DATA=replace-with-hermes-data-root",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.bootstrap(env_file=env_file)

    root_check = next(check for check in report["checks"] if check["id"] == "required_roots")
    assert report["ok"] is False
    assert root_check["status"] == "fail"
    assert "FREYJA6_HERMES_DATA" in root_check["placeholders"]
    assert {"key": "FREYJA6_APPROVED_FILES_ROOT", "path": "/srv", "reason": "must not point at a broad host root"} in root_check["unsafe"]
    assert any(item["key"] == "FREYJA6_LOG_ROOT" and item["reason"] == "must stay under a freyja6-specific host path" for item in root_check["unsafe"])


def test_freyja6_bootstrap_rejects_symlinked_host_root(tmp_path) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_symlink_roots")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    root.mkdir()
    real_logs = tmp_path / "legacy-logs"
    real_logs.mkdir()
    log_link = root / "logs"
    log_link.symlink_to(real_logs)
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved-files'}",
                f"FREYJA6_LOG_ROOT={log_link}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.bootstrap(env_file=env_file)

    root_check = next(check for check in report["checks"] if check["id"] == "required_roots")
    assert report["ok"] is False
    assert root_check["status"] == "fail"
    assert {"key": "FREYJA6_LOG_ROOT", "path": str(log_link), "reason": "must not be a symlink"} in root_check["unsafe"]
    assert report["created_dirs"] == []
    assert report["writes"] == []


def test_freyja6_bootstrap_cli_refuses_symlinked_output_before_host_writes(tmp_path, capsys) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_symlink_output")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    real_output = tmp_path / "real-bootstrap.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "bootstrap.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--env-file", str(env_file), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: bootstrap.json"
    assert rendered["created_dirs"] == []
    assert rendered["writes"] == []
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"
    assert not root.exists()


def test_freyja6_bootstrap_cli_refuses_directory_output_before_host_writes(tmp_path, capsys) -> None:
    module = _load_bootstrap_module("freyja6_bootstrap_directory_output")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "bootstrap-dir"
    output.mkdir()

    exit_code = module.main(["--env-file", str(env_file), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: bootstrap-dir"
    assert rendered["created_dirs"] == []
    assert rendered["writes"] == []
    assert not root.exists()


def test_freyja6_atlas_preflight_flags_example_placeholders() -> None:
    module = _load_preflight_module("freyja6_atlas_preflight")

    report = module.build_report(env_file=ROOT / "deploy/compose/freyja6/.env.example")

    assert report["ready"] is False
    required_env = next(check for check in report["checks"] if check["id"] == "required_env")
    assert required_env["status"] == "fail"
    assert "LITELLM_MASTER_KEY" in required_env["placeholders"]
    assert "FREYJA6_DISCORD_BOT_TOKEN" in required_env["placeholders"]
    assert "FREYJA6_CORE_MCP_TOKEN" in required_env["placeholders"]
    hermes_source = next(check for check in report["checks"] if check["id"] == "hermes_source")
    assert hermes_source["status"] == "fail"


def test_freyja6_atlas_preflight_rejects_example_style_placeholders(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_example_style_placeholders")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        .replace("discord-local-secret", "example-discord-token")
        .replace("core-mcp-local-secret", "<core-mcp-token>")
        .replace("terminal-mcp-local-secret", "terminal-placeholder-token"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    required_env = next(check for check in report["checks"] if check["id"] == "required_env")
    assert report["ready"] is False
    assert required_env["status"] == "fail"
    assert "FREYJA6_DISCORD_BOT_TOKEN" in required_env["placeholders"]
    assert "FREYJA6_CORE_MCP_TOKEN" in required_env["placeholders"]
    assert "FREYJA6_TERMINAL_MCP_TOKEN" in required_env["placeholders"]


def test_freyja6_atlas_preflight_rejects_symlinked_env_file_before_loading(tmp_path, monkeypatch) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_symlink_env_source")
    real_env = tmp_path / "real.env"
    real_env.write_text(_freyja6_complete_env(tmp_path), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.symlink_to(real_env)

    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.build_report(env_file=env_file, create_dirs=True)

    assert report["ready"] is False
    assert report["checks"] == report["blockers"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(env_file)]


def test_freyja6_atlas_preflight_rejects_directory_env_file_before_loading(tmp_path, monkeypatch) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_directory_env_source")
    env_file = tmp_path / ".env"
    env_file.mkdir()

    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.build_report(env_file=env_file, create_dirs=True)

    assert report["ready"] is False
    assert report["checks"] == report["blockers"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(env_file)]


def test_freyja6_atlas_preflight_does_not_create_dirs_from_example_env(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_no_example_create")

    report = module.build_report(env_file=tmp_path / "missing.env", create_dirs=True)

    host_dirs = next(check for check in report["checks"] if check["id"] == "host_directories")
    assert report["ready"] is False
    assert host_dirs["status"] == "fail"
    assert host_dirs["created"] == []
    assert host_dirs["missing"] == ["env_file"]


def test_freyja6_atlas_preflight_rejects_symlinked_host_root(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_symlink_roots")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    root = tmp_path / "srv" / "freyja6"
    root.mkdir(parents=True)
    real_approved = tmp_path / "legacy-approved"
    real_approved.mkdir()
    approved_link = root / "approved-files"
    approved_link.symlink_to(real_approved)
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved-files'}",
            f"FREYJA6_APPROVED_FILES_ROOT={approved_link}",
        ),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    host_dirs = next(check for check in report["checks"] if check["id"] == "host_directories")
    assert report["ready"] is False
    assert host_dirs["status"] == "fail"
    assert {
        "key": "FREYJA6_APPROVED_FILES_ROOT",
        "path": "freyja6/approved-files",
        "reason": "must not be a symlink",
    } in host_dirs["unsafe"]


def test_freyja6_atlas_preflight_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_symlink_output")
    real_output = tmp_path / "real-preflight.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "preflight.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--env-file", str(tmp_path / "missing.env"), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: preflight.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_atlas_preflight_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_directory_output")
    output = tmp_path / "preflight-dir"
    output.mkdir()

    exit_code = module.main(["--env-file", str(tmp_path / "missing.env"), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: preflight-dir"


def test_freyja6_atlas_preflight_requires_all_vulcan_model_aliases(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_models")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(_freyja6_complete_env(tmp_path).replace("VULCAN_CODE_MODEL=qwen2.5-coder:32b-instruct\n", ""), encoding="utf-8")

    report = module.build_report(env_file=env_file, create_dirs=True)

    assert report["ready"] is False
    required_env = next(check for check in report["checks"] if check["id"] == "required_env")
    assert "VULCAN_CODE_MODEL" in required_env["missing"]


def test_freyja6_atlas_preflight_rejects_wrong_compose_project(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_compose_project")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace("COMPOSE_PROJECT_NAME=freyja6", "COMPOSE_PROJECT_NAME=freyja"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    compose_project = next(check for check in report["checks"] if check["id"] == "compose_project")
    assert report["ready"] is False
    assert compose_project["status"] == "fail"


def test_freyja6_atlas_preflight_rejects_image_pin_drift(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_image_pins")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        .replace("LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.89.0", "LITELLM_IMAGE=ghcr.io/berriai/litellm:latest")
        .replace("HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14", "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14-extra"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    image_pins = next(check for check in report["checks"] if check["id"] == "image_pins")
    assert report["ready"] is False
    assert image_pins["status"] == "fail"
    assert "LITELLM_IMAGE must use an immutable validation tag." in image_pins["failures"]
    assert f"LITELLM_IMAGE must remain pinned to {module.EXPECTED_LITELLM_IMAGE}." in image_pins["failures"]
    assert "HERMES_AGENT_IMAGE tag must exactly match HERMES_AGENT_VERSION." in image_pins["failures"]


def test_freyja6_atlas_preflight_rejects_local_hermes_image_label_drift(tmp_path, monkeypatch) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_hermes_label_drift")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(_freyja6_complete_env(tmp_path), encoding="utf-8")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def fake_run(cmd, cwd=None, text=True, capture_output=True, check=False):
        if cmd[:2] == ["docker", "compose"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="services: {}\n", stderr="")
        if cmd[:3] == ["docker", "image", "inspect"]:
            image = cmd[3]
            label = "v2026.9.13" if image == "hermes-agent-local:v2026.9.14" else ""
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps([{"Config": {"Labels": {"org.opencontainers.image.version": label}}}]),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    report = module.build_report(env_file=env_file, create_dirs=True, check_images=True)

    docker_images = next(check for check in report["checks"] if check["id"] == "docker_images")
    assert report["ready"] is False
    assert docker_images["status"] == "fail"
    assert {
        "image": "hermes-agent-local:v2026.9.14",
        "reason": "org.opencontainers.image.version label must match HERMES_AGENT_VERSION",
    } in docker_images["failures"]


def test_freyja6_atlas_preflight_rejects_database_url_drift(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_database_url")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "DATABASE_URL=postgresql://litellm:postgres-local-secret@litellm-db:5432/litellm",
            "DATABASE_URL=postgresql://postgres:postgres-local-secret@localhost:5432/postgres",
        ),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    database_url = next(check for check in report["checks"] if check["id"] == "database_url")
    assert report["ready"] is False
    assert database_url["status"] == "fail"
    assert "DATABASE_URL must point at the litellm-db compose service." in database_url["failures"]
    assert "DATABASE_URL must use the litellm database user." in database_url["failures"]
    assert "DATABASE_URL must target the litellm database." in database_url["failures"]


def test_freyja6_atlas_preflight_rejects_public_live_helper_endpoint(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_public_live_helper")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        + "\n"
        + "\n".join(
            [
                "FREYJA6_LITELLM_BASE_URL=https://api.example.com/v1",
                "FREYJA6_CORE_URL=https://core.example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    endpoints = next(check for check in report["checks"] if check["id"] == "live_helper_endpoints")
    assert report["ready"] is False
    assert {"key": "FREYJA6_LITELLM_BASE_URL", "reason": "must use Atlas loopback, private, tailnet, .local, or explicitly service-scoped host"} in endpoints["failures"]
    assert {"key": "FREYJA6_CORE_URL", "reason": "must use Atlas loopback, private, tailnet, .local, or explicitly service-scoped host"} in endpoints["failures"]
    assert endpoints["endpoints_redacted"]["FREYJA6_LITELLM_BASE_URL"] == "https://atlas-public/v1"
    assert "api.example.com" not in json.dumps(endpoints["endpoints_redacted"])


def test_freyja6_atlas_preflight_rejects_internal_live_helper_endpoint_confusion(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_internal_live_helper")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        + "\n"
        + "\n".join(
            [
                "FREYJA6_LITELLM_BASE_URL=http://hermes-freyja-test:4000/v1",
                "FREYJA6_CORE_MCP_HEALTH_URL=http://litellm-db:8766/healthz",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    endpoints = next(check for check in report["checks"] if check["id"] == "live_helper_endpoints")
    assert report["ready"] is False
    assert {"key": "FREYJA6_LITELLM_BASE_URL", "reason": "must point at the LiteLLM gateway, not internal services"} in endpoints["failures"]
    assert {"key": "FREYJA6_CORE_MCP_HEALTH_URL", "reason": "must point at the Atlas Core or MCP service endpoint, not compose internals"} in endpoints["failures"]


def test_freyja6_atlas_preflight_rejects_live_helper_endpoint_path_drift(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_live_helper_paths")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        + "\n"
        + "\n".join(
            [
                "FREYJA6_LITELLM_BASE_URL=http://127.0.0.1:4600",
                "FREYJA6_CORE_MCP_HEALTH_URL=http://127.0.0.1:8766/status",
                "FREYJA6_TERMINAL_MCP_HEALTH_URL=http://127.0.0.1:8765",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    endpoints = next(check for check in report["checks"] if check["id"] == "live_helper_endpoints")
    assert report["ready"] is False
    assert {"key": "FREYJA6_LITELLM_BASE_URL", "reason": "must include the LiteLLM /v1 API base path"} in endpoints["failures"]
    assert {"key": "FREYJA6_CORE_MCP_HEALTH_URL", "reason": "must point at the MCP /healthz endpoint"} in endpoints["failures"]
    assert {"key": "FREYJA6_TERMINAL_MCP_HEALTH_URL", "reason": "must point at the MCP /healthz endpoint"} in endpoints["failures"]


def _freyja6_complete_env(tmp_path: Path) -> str:
    root = tmp_path / "srv" / "freyja6"
    return (
        "\n".join(
            [
                "COMPOSE_PROJECT_NAME=freyja6",
                "LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.89.0",
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={tmp_path / 'hermes-agent'}",
                "LITELLM_MASTER_KEY=sk-local-secret",
                "POSTGRES_PASSWORD=postgres-local-secret",
                "DATABASE_URL=postgresql://litellm:postgres-local-secret@litellm-db:5432/litellm",
                "VULCAN_OLLAMA_BASE_URL=http://100.94.80.21:11434",
                "VULCAN_FAST_MODEL=qwen2.5:14b-instruct",
                "VULCAN_GENERAL_MODEL=qwen2.5:32b-instruct",
                "VULCAN_CODE_MODEL=qwen2.5-coder:32b-instruct",
                "FREYJA6_DISCORD_BOT_TOKEN=discord-local-secret",
                "FREYJA6_DISCORD_CHANNEL_ID=discord-channel-123456",
                "FREYJA6_CORE_MCP_TOKEN=core-mcp-local-secret",
                "FREYJA6_TERMINAL_MCP_TOKEN=terminal-mcp-local-secret",
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved-files'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n"
    )


def test_freyja6_env_audit_flags_example_placeholders_without_secret_values() -> None:
    module = _load_env_audit_module("freyja6_env_audit_example")

    report = module.build_report(env_file=ROOT / "deploy/compose/freyja6/.env.example")
    rendered = str(report)

    assert report["ok"] is False
    assert report["secrets_included"] is False
    required_values = next(check for check in report["checks"] if check["id"] == "required_values")
    assert required_values["status"] == "fail"
    assert "FREYJA6_DISCORD_BOT_TOKEN" in required_values["placeholders"]
    assert "replace-with-atlas-local-litellm-key" not in rendered
    assert "replace-with-freyja6-postgres-password" not in rendered


def test_freyja6_env_audit_passes_complete_env_and_redacts_secrets(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_complete")
    env_file = tmp_path / ".env"
    env_file.write_text(_freyja6_complete_env(tmp_path), encoding="utf-8")

    report = module.build_report(env_file=env_file)
    rendered = str(report)

    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert all(check["status"] == "pass" for check in report["checks"])
    assert "sk-local-secret" not in rendered
    assert "postgres-local-secret" not in rendered
    assert "discord-local-secret" not in rendered
    assert "core-mcp-local-secret" not in rendered
    assert "terminal-mcp-local-secret" not in rendered
    assert "<redacted:" in rendered


def test_freyja6_env_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_env_audit_module("freyja6_env_audit_symlink_output")
    env_file = tmp_path / ".env"
    env_file.write_text(_freyja6_complete_env(tmp_path), encoding="utf-8")
    real_output = tmp_path / "real-env-audit.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "env-audit.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--env-file", str(env_file), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: env-audit.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_env_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_env_audit_module("freyja6_env_audit_directory_output")
    env_file = tmp_path / ".env"
    env_file.write_text(_freyja6_complete_env(tmp_path), encoding="utf-8")
    output = tmp_path / "env-audit-dir"
    output.mkdir()

    exit_code = module.main(["--env-file", str(env_file), "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: env-audit-dir"


def test_freyja6_env_audit_rejects_symlinked_env_file_before_loading(tmp_path, monkeypatch) -> None:
    module = _load_env_audit_module("freyja6_env_audit_symlink_env_source")
    real_env = tmp_path / "real.env"
    real_env.write_text(_freyja6_complete_env(tmp_path), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.symlink_to(real_env)

    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.build_report(env_file=env_file)

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(env_file)]


def test_freyja6_env_audit_rejects_directory_env_file_before_loading(tmp_path, monkeypatch) -> None:
    module = _load_env_audit_module("freyja6_env_audit_directory_env_source")
    env_file = tmp_path / ".env"
    env_file.mkdir()

    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.build_report(env_file=env_file)

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(env_file)]


def test_freyja6_env_audit_rejects_example_style_placeholders(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_example_style_placeholders")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        .replace("discord-local-secret", "example-discord-token")
        .replace("core-mcp-local-secret", "<core-mcp-token>")
        .replace("terminal-mcp-local-secret", "terminal-placeholder-token"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    required_values = next(check for check in report["checks"] if check["id"] == "required_values")
    assert report["ok"] is False
    assert required_values["status"] == "fail"
    assert "FREYJA6_DISCORD_BOT_TOKEN" in required_values["placeholders"]
    assert "FREYJA6_CORE_MCP_TOKEN" in required_values["placeholders"]
    assert "FREYJA6_TERMINAL_MCP_TOKEN" in required_values["placeholders"]


def test_freyja6_env_audit_rejects_unsafe_roots_and_unpinned_images(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_unsafe")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        .replace("LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.89.0", "LITELLM_IMAGE=ghcr.io/berriai/litellm:latest")
        .replace("HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14", "HERMES_AGENT_IMAGE=hermes-agent-local:main")
        .replace(f"FREYJA6_LOG_ROOT={tmp_path / 'srv' / 'freyja6' / 'logs'}", "FREYJA6_LOG_ROOT=/srv"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    assert report["ok"] is False
    assert next(check for check in report["checks"] if check["id"] == "image_pins")["status"] == "fail"
    assert next(check for check in report["checks"] if check["id"] == "host_roots")["status"] == "fail"


def test_freyja6_env_audit_rejects_symlinked_host_root(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_symlink_roots")
    root = tmp_path / "srv" / "freyja6"
    root.mkdir(parents=True)
    real_logs = tmp_path / "legacy-logs"
    real_logs.mkdir()
    log_link = root / "logs"
    log_link.symlink_to(real_logs)
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            f"FREYJA6_LOG_ROOT={root / 'logs'}",
            f"FREYJA6_LOG_ROOT={log_link}",
        ),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    host_roots = next(check for check in report["checks"] if check["id"] == "host_roots")
    assert report["ok"] is False
    assert host_roots["status"] == "fail"
    assert {"key": "FREYJA6_LOG_ROOT", "reason": "must not be a symlink"} in host_roots["failures"]


def test_freyja6_env_audit_rejects_image_pin_drift(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_image_drift")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        .replace("LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.89.0", "LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.84.0-stable")
        .replace("HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14", "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14-extra"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    image_pins = next(check for check in report["checks"] if check["id"] == "image_pins")
    assert report["ok"] is False
    assert f"LITELLM_IMAGE must remain pinned to {module.EXPECTED_LITELLM_IMAGE}." in image_pins["failures"]
    assert "HERMES_AGENT_IMAGE tag must exactly match HERMES_AGENT_VERSION." in image_pins["failures"]


def test_freyja6_env_audit_requires_distinct_vulcan_models(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_distinct_models")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "VULCAN_GENERAL_MODEL=qwen2.5:32b-instruct",
            "VULCAN_GENERAL_MODEL=qwen2.5:14b-instruct",
        ),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    vulcan_models = next(check for check in report["checks"] if check["id"] == "vulcan_models")
    assert report["ok"] is False
    assert vulcan_models["status"] == "fail"
    assert vulcan_models["duplicates"] == ["qwen2.5:14b-instruct"]


def test_freyja6_env_audit_rejects_atlas_loopback_vulcan_url(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_vulcan_loopback")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "VULCAN_OLLAMA_BASE_URL=http://100.94.80.21:11434",
            "VULCAN_OLLAMA_BASE_URL=http://127.0.0.1:11434",
        ),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    vulcan_url = next(check for check in report["checks"] if check["id"] == "vulcan_url")
    assert report["ok"] is False
    assert vulcan_url["status"] == "fail"
    assert "VULCAN_OLLAMA_BASE_URL must point at the Vulcan inference host, not Atlas loopback or compose services." in vulcan_url["failures"]


def test_freyja6_env_audit_rejects_public_vulcan_url(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_public_vulcan")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "VULCAN_OLLAMA_BASE_URL=http://100.94.80.21:11434",
            "VULCAN_OLLAMA_BASE_URL=https://api.example.com:11434",
        ),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    vulcan_url = next(check for check in report["checks"] if check["id"] == "vulcan_url")
    assert report["ok"] is False
    assert vulcan_url["status"] == "fail"
    assert "VULCAN_OLLAMA_BASE_URL must use a private, tailnet, or explicitly Vulcan-scoped host." in vulcan_url["failures"]


def test_freyja6_env_audit_rejects_public_live_helper_endpoint(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_public_live_helper")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        + "\n"
        + "\n".join(
            [
                "FREYJA6_LITELLM_BASE_URL=https://api.example.com/v1",
                "FREYJA6_CORE_URL=https://core.example.com",
                "FREYJA6_CORE_MCP_HEALTH_URL=http://127.0.0.1:8766/healthz",
                "FREYJA6_TERMINAL_MCP_HEALTH_URL=http://127.0.0.1:8765/healthz",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    endpoints = next(check for check in report["checks"] if check["id"] == "live_helper_endpoints")
    assert report["ok"] is False
    assert endpoints["status"] == "fail"
    assert {"key": "FREYJA6_LITELLM_BASE_URL", "reason": "must use Atlas loopback, private, tailnet, .local, or explicitly service-scoped host"} in endpoints["failures"]
    assert {"key": "FREYJA6_CORE_URL", "reason": "must use Atlas loopback, private, tailnet, .local, or explicitly service-scoped host"} in endpoints["failures"]
    assert endpoints["endpoints_redacted"]["FREYJA6_LITELLM_BASE_URL"] == "https://atlas-public/v1"
    assert "api.example.com" not in json.dumps(endpoints["endpoints_redacted"])


def test_freyja6_env_audit_rejects_internal_live_helper_endpoint_confusion(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_internal_live_helper")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        + "\n"
        + "\n".join(
            [
                "FREYJA6_LITELLM_BASE_URL=http://litellm-db:4000/v1",
                "FREYJA6_CORE_URL=http://litellm:8510",
                "FREYJA6_CORE_MCP_HEALTH_URL=http://127.0.0.1:8766/healthz",
                "FREYJA6_TERMINAL_MCP_HEALTH_URL=http://127.0.0.1:8765/healthz",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    endpoints = next(check for check in report["checks"] if check["id"] == "live_helper_endpoints")
    assert report["ok"] is False
    assert {"key": "FREYJA6_LITELLM_BASE_URL", "reason": "must point at the LiteLLM gateway, not internal services"} in endpoints["failures"]
    assert {"key": "FREYJA6_CORE_URL", "reason": "must point at the Atlas Core or MCP service endpoint, not compose internals"} in endpoints["failures"]


def test_freyja6_env_audit_rejects_live_helper_endpoint_path_drift(tmp_path) -> None:
    module = _load_env_audit_module("freyja6_env_audit_live_helper_paths")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        + "\n"
        + "\n".join(
            [
                "FREYJA6_LITELLM_BASE_URL=http://127.0.0.1:4600",
                "FREYJA6_CORE_MCP_HEALTH_URL=http://127.0.0.1:8766/status",
                "FREYJA6_TERMINAL_MCP_HEALTH_URL=http://127.0.0.1:8765",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    endpoints = next(check for check in report["checks"] if check["id"] == "live_helper_endpoints")
    assert report["ok"] is False
    assert {"key": "FREYJA6_LITELLM_BASE_URL", "reason": "must include the LiteLLM /v1 API base path"} in endpoints["failures"]
    assert {"key": "FREYJA6_CORE_MCP_HEALTH_URL", "reason": "must point at the MCP /healthz endpoint"} in endpoints["failures"]
    assert {"key": "FREYJA6_TERMINAL_MCP_HEALTH_URL", "reason": "must point at the MCP /healthz endpoint"} in endpoints["failures"]


def test_freyja6_atlas_preflight_can_create_temp_directories(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_temp")
    env_file = tmp_path / ".env"
    root = tmp_path / "freyja6"
    env_file.write_text(
        "\n".join(
            [
                "COMPOSE_PROJECT_NAME=freyja6",
                "LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.89.0",
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={tmp_path / 'hermes-agent'}",
                "LITELLM_MASTER_KEY=sk-local-test",
                "POSTGRES_PASSWORD=postgres-local-test",
                "DATABASE_URL=postgresql://litellm:postgres-local-test@litellm-db:5432/litellm",
                "VULCAN_OLLAMA_BASE_URL=http://100.94.80.21:11434",
                "VULCAN_FAST_MODEL=qwen2.5:14b-instruct",
                "VULCAN_GENERAL_MODEL=qwen2.5:32b-instruct",
                "VULCAN_CODE_MODEL=qwen2.5-coder:32b-instruct",
                "FREYJA6_DISCORD_BOT_TOKEN=discord-redacted-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted-test",
                "FREYJA6_CORE_MCP_TOKEN=core-mcp-redacted-test",
                "FREYJA6_TERMINAL_MCP_TOKEN=terminal-mcp-redacted-test",
                f"FREYJA6_APPROVED_FILES_ROOT={root / 'approved'}",
                f"FREYJA6_LOG_ROOT={root / 'logs'}",
                f"FREYJA6_HERMES_DATA={root / 'hermes'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "hermes-agent").mkdir()
    (tmp_path / "hermes-agent/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    report = module.build_report(env_file=env_file, create_dirs=True)

    assert report["ready"] is True
    assert (root / "approved").is_dir()
    assert (root / "logs").is_dir()
    assert (root / "hermes").is_dir()


def test_freyja6_atlas_preflight_requires_distinct_vulcan_models(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_distinct_models")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "VULCAN_CODE_MODEL=qwen2.5-coder:32b-instruct",
            "VULCAN_CODE_MODEL=qwen2.5:32b-instruct",
        ),
        encoding="utf-8",
    )
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    report = module.build_report(env_file=env_file, create_dirs=True)

    vulcan_models = next(check for check in report["checks"] if check["id"] == "vulcan_models")
    assert report["ready"] is False
    assert vulcan_models["status"] == "fail"
    assert vulcan_models["duplicates"] == ["qwen2.5:32b-instruct"]


def test_freyja6_atlas_preflight_rejects_atlas_loopback_vulcan_url(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_vulcan_loopback")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "VULCAN_OLLAMA_BASE_URL=http://100.94.80.21:11434",
            "VULCAN_OLLAMA_BASE_URL=http://localhost:11434",
        ),
        encoding="utf-8",
    )
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    report = module.build_report(env_file=env_file, create_dirs=True)

    vulcan_url = next(check for check in report["checks"] if check["id"] == "vulcan_url")
    assert report["ready"] is False
    assert vulcan_url["status"] == "fail"
    assert "VULCAN_OLLAMA_BASE_URL must point at the Vulcan inference host, not Atlas loopback or compose services." in vulcan_url["failures"]


def test_freyja6_atlas_preflight_rejects_public_vulcan_url(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_public_vulcan")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path).replace(
            "VULCAN_OLLAMA_BASE_URL=http://100.94.80.21:11434",
            "VULCAN_OLLAMA_BASE_URL=https://api.example.com:11434",
        ),
        encoding="utf-8",
    )
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    report = module.build_report(env_file=env_file, create_dirs=True)

    vulcan_url = next(check for check in report["checks"] if check["id"] == "vulcan_url")
    assert report["ready"] is False
    assert vulcan_url["status"] == "fail"
    assert "VULCAN_OLLAMA_BASE_URL must use a private, tailnet, or explicitly Vulcan-scoped host." in vulcan_url["failures"]


def test_freyja6_atlas_preflight_rejects_unsafe_host_roots_before_create(tmp_path) -> None:
    module = _load_preflight_module("freyja6_atlas_preflight_unsafe_roots")
    hermes = tmp_path / "hermes-agent"
    hermes.mkdir()
    (hermes / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        _freyja6_complete_env(tmp_path)
        .replace(f"FREYJA6_APPROVED_FILES_ROOT={tmp_path / 'srv' / 'freyja6' / 'approved-files'}", "FREYJA6_APPROVED_FILES_ROOT=/srv")
        .replace(f"FREYJA6_LOG_ROOT={tmp_path / 'srv' / 'freyja6' / 'logs'}", f"FREYJA6_LOG_ROOT={tmp_path / 'logs'}"),
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file, create_dirs=True)

    host_dirs = next(check for check in report["checks"] if check["id"] == "host_directories")
    assert report["ready"] is False
    assert {"key": "FREYJA6_APPROVED_FILES_ROOT", "path": "/srv", "reason": "must not point at a broad host root"} in host_dirs["unsafe"]
    assert any(item["key"] == "FREYJA6_LOG_ROOT" and item["reason"] == "must stay under a freyja6-specific host path" for item in host_dirs["unsafe"])
    assert not (tmp_path / "logs").exists()


def test_freyja6_hermes_image_helper_requires_source_and_pinned_tag(tmp_path) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={tmp_path / 'hermes-agent'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "hermes-agent").mkdir()
    (tmp_path / "hermes-agent/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    report = module.build_report(env_file=env_file)

    assert report["image"] == "hermes-agent-local:v2026.9.14"
    assert next(check for check in report["checks"] if check["id"] == "image_pin")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "hermes_source")["status"] == "pass"


def test_freyja6_hermes_image_helper_rejects_unpinned_tag(tmp_path) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image_unpinned")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:latest",
                f"HERMES_AGENT_SOURCE={tmp_path / 'hermes-agent'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    assert next(check for check in report["checks"] if check["id"] == "image_pin")["status"] == "fail"


def test_freyja6_hermes_image_helper_rejects_version_suffix_tag(tmp_path) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image_suffix")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14-extra",
                f"HERMES_AGENT_SOURCE={tmp_path / 'hermes-agent'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(env_file=env_file)

    image_pin = next(check for check in report["checks"] if check["id"] == "image_pin")
    assert image_pin["status"] == "fail"
    assert image_pin["message"] == "HERMES_AGENT_IMAGE tag must exactly match HERMES_AGENT_VERSION."


def test_freyja6_hermes_image_helper_rejects_local_image_label_drift(tmp_path, monkeypatch) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image_label_drift")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={tmp_path / 'hermes-agent'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "hermes-agent").mkdir()
    (tmp_path / "hermes-agent/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def fake_run(cmd, text, capture_output, check):
        assert cmd == ["docker", "image", "inspect", "hermes-agent-local:v2026.9.14"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps([{"Config": {"Labels": {"org.opencontainers.image.version": "v2026.9.13"}}}]),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    report = module.build_report(env_file=env_file)

    local_image = next(check for check in report["checks"] if check["id"] == "local_image")
    assert report["ready"] is False
    assert local_image["status"] == "fail"
    assert local_image["message"] == "Pinned Hermes image label org.opencontainers.image.version must match HERMES_AGENT_VERSION."


def test_freyja6_hermes_image_helper_reports_build_timeout(tmp_path, monkeypatch) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image_build_timeout")
    env_file = tmp_path / ".env"
    source = tmp_path / "hermes-agent"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={source}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="missing")
        if cmd[:2] == ["docker", "build"]:
            raise subprocess.TimeoutExpired(cmd, timeout=1, output="partial out", stderr="partial err")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    report = module.build_report(env_file=env_file, build=True, build_timeout=1)

    image_build = next(check for check in report["checks"] if check["id"] == "image_build")
    assert report["ready"] is False
    assert image_build["status"] == "fail"
    assert image_build["message"] == "Docker build timed out after 1 seconds."
    assert image_build["stdout_tail"] == "partial out"
    assert image_build["stderr_tail"] == "partial err"


def test_freyja6_hermes_image_cli_refuses_symlinked_output_before_docker_work(tmp_path, monkeypatch, capsys) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image_symlink_output")
    env_file = tmp_path / ".env"
    source = tmp_path / "hermes-agent"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={source}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    real_output = tmp_path / "real-hermes-image.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "hermes-image.json"
    output.symlink_to(real_output)

    def fail_which(name):
        raise AssertionError("docker discovery should not run for unsafe output")

    def fail_run(*args, **kwargs):
        raise AssertionError("docker command should not run for unsafe output")

    monkeypatch.setattr(module.shutil, "which", fail_which)
    monkeypatch.setattr(module.subprocess, "run", fail_run)

    exit_code = module.main(["--env-file", str(env_file), "--build", "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: hermes-image.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_hermes_image_cli_refuses_directory_output_before_docker_work(tmp_path, monkeypatch, capsys) -> None:
    module = _load_hermes_image_module("freyja6_hermes_image_directory_output")
    env_file = tmp_path / ".env"
    source = tmp_path / "hermes-agent"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                f"HERMES_AGENT_SOURCE={source}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "hermes-image-dir"
    output.mkdir()

    def fail_which(name):
        raise AssertionError("docker discovery should not run for unsafe output")

    def fail_run(*args, **kwargs):
        raise AssertionError("docker command should not run for unsafe output")

    monkeypatch.setattr(module.shutil, "which", fail_which)
    monkeypatch.setattr(module.subprocess, "run", fail_run)

    exit_code = module.main(["--env-file", str(env_file), "--build", "--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: hermes-image-dir"


def test_freyja6_hermes_runtime_contract_matches_compose_and_agent_config() -> None:
    module = _load_hermes_contract_module("freyja6_hermes_contract")

    report = module.build_report(
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        schedules=ROOT / "config/freyja6/schedules.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is True
    assert all(check["status"] == "pass" for check in report["checks"])


def test_freyja6_hermes_runtime_contract_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_hermes_contract_module("freyja6_hermes_contract_symlink_output")
    real_output = tmp_path / "real-hermes-contract.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "hermes-contract.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: hermes-contract.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_hermes_runtime_contract_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_hermes_contract_module("freyja6_hermes_contract_directory_output")
    output = tmp_path / "hermes-contract-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: hermes-contract-dir"


def test_freyja6_hermes_runtime_contract_rejects_symlinked_source_file(tmp_path) -> None:
    module = _load_hermes_contract_module("freyja6_hermes_contract_symlink_source")
    real_contract = tmp_path / "real-contract.yaml"
    real_contract.write_text((ROOT / "config/freyja6/hermes-runtime-contract.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    contract = tmp_path / "hermes-runtime-contract.yaml"
    contract.symlink_to(real_contract)

    report = module.build_report(
        contract=contract,
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        schedules=ROOT / "config/freyja6/schedules.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(contract)]


def test_freyja6_hermes_runtime_contract_rejects_directory_source_file(tmp_path) -> None:
    module = _load_hermes_contract_module("freyja6_hermes_contract_directory_source")
    contract = tmp_path / "hermes-runtime-contract.yaml"
    contract.mkdir()

    report = module.build_report(
        contract=contract,
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        schedules=ROOT / "config/freyja6/schedules.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(contract)]


def test_freyja6_hermes_runtime_contract_detects_compose_drift(tmp_path) -> None:
    module = _load_hermes_contract_module("freyja6_hermes_contract_drift")
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    compose["services"]["hermes-freyja-test"]["environment"]["OPENAI_BASE_URL"] = "http://vulcan-direct:11434/v1"
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(yaml.safe_dump(compose, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        schedules=ROOT / "config/freyja6/schedules.yaml",
        compose=compose_path,
    )

    assert report["ok"] is False
    environment = next(check for check in report["checks"] if check["id"] == "environment")
    assert environment["status"] == "fail"
    assert environment["mismatches"][0]["key"] == "OPENAI_BASE_URL"


def test_freyja6_model_privacy_audit_passes_local_vulcan_only_config() -> None:
    module = _load_model_privacy_module("freyja6_model_privacy")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=ROOT / "deploy/compose/freyja6/litellm.config.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    assert report["ok"] is True
    assert all(check["status"] == "pass" for check in report["checks"])


def test_freyja6_model_privacy_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_symlink_output")
    real_output = tmp_path / "real-model-privacy.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "model-privacy.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: model-privacy.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_model_privacy_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_directory_output")
    output = tmp_path / "model-privacy-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: model-privacy-dir"


def test_freyja6_model_privacy_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_symlink_source")
    real_litellm = tmp_path / "real-litellm.config.yaml"
    real_litellm.write_text((ROOT / "deploy/compose/freyja6/litellm.config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    litellm_config = tmp_path / "litellm.config.yaml"
    litellm_config.symlink_to(real_litellm)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=litellm_config,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(litellm_config)]


def test_freyja6_model_privacy_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=ROOT / "deploy/compose/freyja6/litellm.config.yaml",
        compose=compose,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(compose)]


def test_freyja6_model_privacy_audit_rejects_cloud_model_alias(tmp_path) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_cloud")
    litellm = _yaml("deploy/compose/freyja6/litellm.config.yaml")
    litellm["model_list"].append(
        {
            "model_name": "cloud-general",
            "litellm_params": {
                "model": "openai/gpt-4.1",
                "api_base": "https://api.openai.com/v1",
            },
        }
    )
    litellm_path = tmp_path / "litellm.config.yaml"
    litellm_path.write_text(yaml.safe_dump(litellm, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=litellm_path,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    assert report["ok"] is False
    litellm_check = next(check for check in report["checks"] if check["id"] == "litellm_models")
    assert litellm_check["status"] == "fail"
    assert any(item.get("reason") == "cloud_provider_marker" for item in litellm_check["failures"])


def test_freyja6_model_privacy_audit_rejects_duplicate_vulcan_model_env(tmp_path) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_duplicate_env")
    litellm = _yaml("deploy/compose/freyja6/litellm.config.yaml")
    litellm["model_list"][2]["litellm_params"]["model"] = "ollama/qwen2.5:72b"
    litellm_path = tmp_path / "litellm.config.yaml"
    litellm_path.write_text(yaml.safe_dump(litellm, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=litellm_path,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    litellm_check = next(check for check in report["checks"] if check["id"] == "litellm_models")
    assert report["ok"] is False
    assert {
        "model_name": "vulcan-code",
        "reason": "unexpected_vulcan_model_target",
        "model": "ollama/qwen2.5:72b",
    } in litellm_check["failures"]


def test_freyja6_model_privacy_audit_rejects_cloud_fallback_target(tmp_path) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_cloud_fallback")
    litellm = _yaml("deploy/compose/freyja6/litellm.config.yaml")
    litellm["router_settings"] = {
        "fallbacks": [
            {"vulcan-general": ["openai/gpt-4.1"]},
        ]
    }
    litellm_path = tmp_path / "litellm.config.yaml"
    litellm_path.write_text(yaml.safe_dump(litellm, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=litellm_path,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    litellm_check = next(check for check in report["checks"] if check["id"] == "litellm_models")
    assert report["ok"] is False
    assert {
        "reason": "cloud_fallback_marker",
        "path": "router_settings.fallbacks[0].vulcan-general[0]",
        "target": "openai/gpt-4.1",
    } in litellm_check["failures"]


def test_freyja6_model_privacy_audit_rejects_unknown_fallback_alias(tmp_path) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_unknown_fallback")
    litellm = _yaml("deploy/compose/freyja6/litellm.config.yaml")
    litellm["router_settings"] = {"context_window_fallbacks": [{"vulcan-general": ["local-large"]}]}
    litellm_path = tmp_path / "litellm.config.yaml"
    litellm_path.write_text(yaml.safe_dump(litellm, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=litellm_path,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    litellm_check = next(check for check in report["checks"] if check["id"] == "litellm_models")
    assert report["ok"] is False
    assert {
        "reason": "fallback_target_not_vulcan_alias",
        "path": "router_settings.context_window_fallbacks[0].vulcan-general[0]",
        "target": "local-large",
    } in litellm_check["failures"]


def test_freyja6_model_privacy_audit_rejects_hermes_direct_vulcan_env(tmp_path) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_hermes_vulcan")
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    compose["services"]["hermes-freyja-test"]["environment"]["VULCAN_OLLAMA_BASE_URL"] = "http://100.94.80.21:11434"
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(yaml.safe_dump(compose, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=ROOT / "deploy/compose/freyja6/litellm.config.yaml",
        compose=compose_path,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    environment = next(check for check in report["checks"] if check["id"] == "compose_model_environment")
    assert report["ok"] is False
    assert environment["status"] == "fail"
    assert environment["forbidden_hermes_vulcan_keys"] == ["VULCAN_OLLAMA_BASE_URL"]


def test_freyja6_model_privacy_audit_rejects_litellm_cloud_provider_key(tmp_path) -> None:
    module = _load_model_privacy_module("freyja6_model_privacy_litellm_cloud_key")
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    compose["services"]["litellm"]["environment"]["OPENAI_API_KEY"] = "${REAL_CLOUD_KEY}"
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(yaml.safe_dump(compose, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        litellm_config=ROOT / "deploy/compose/freyja6/litellm.config.yaml",
        compose=compose_path,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    )

    environment = next(check for check in report["checks"] if check["id"] == "compose_model_environment")
    assert report["ok"] is False
    assert environment["status"] == "fail"
    assert environment["cloud_like_keys"] == ["litellm.OPENAI_API_KEY"]


def test_freyja6_gateway_isolation_audit_passes_current_reservations() -> None:
    module = _load_gateway_isolation_module("freyja6_gateway_isolation")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "phase_one_single_live_agent")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "unique_future_boundaries")["status"] == "pass"


def test_freyja6_gateway_isolation_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_gateway_isolation_module("freyja6_gateway_isolation_symlink_output")
    real_output = tmp_path / "real-gateway-isolation.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "gateway-isolation.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: gateway-isolation.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_gateway_isolation_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_gateway_isolation_module("freyja6_gateway_isolation_directory_output")
    output = tmp_path / "gateway-isolation-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: gateway-isolation-dir"


def test_freyja6_gateway_isolation_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_gateway_isolation_module("freyja6_gateway_isolation_symlink_source")
    real_isolation = tmp_path / "real-future-agent-isolation.yaml"
    real_isolation.write_text((ROOT / "config/freyja6/future-agent-isolation.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    isolation = tmp_path / "future-agent-isolation.yaml"
    isolation.symlink_to(real_isolation)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        isolation=isolation,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(isolation)]


def test_freyja6_gateway_isolation_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_gateway_isolation_module("freyja6_gateway_isolation_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
        compose=compose,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(compose)]


def test_freyja6_gateway_isolation_audit_rejects_duplicate_future_channel(tmp_path) -> None:
    module = _load_gateway_isolation_module("freyja6_gateway_isolation_duplicate")
    isolation = _yaml("config/freyja6/future-agent-isolation.yaml")
    isolation["future_agents"][1]["messaging"]["channel_env"] = isolation["future_agents"][0]["messaging"]["channel_env"]
    isolation_path = tmp_path / "future-agent-isolation.yaml"
    isolation_path.write_text(yaml.safe_dump(isolation), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        isolation=isolation_path,
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "unique_future_boundaries")["failures"]
    assert {"reason": "duplicate_boundary", "field": "messaging.channel_env", "values": ["FREYJA6_FREYJA_DISCORD_CHANNEL_ID"]} in failures


def test_freyja6_memory_boundary_audit_passes_local_hermes_native_config() -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "live_agent_memory")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "no_cloud_memory")["status"] == "pass"


def test_freyja6_memory_boundary_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_symlink_output")
    real_output = tmp_path / "real-memory-boundary.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "memory-boundary.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: memory-boundary.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_memory_boundary_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_directory_output")
    output = tmp_path / "memory-boundary-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: memory-boundary-dir"


def test_freyja6_memory_boundary_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_symlink_source")
    real_isolation = tmp_path / "real-future-agent-isolation.yaml"
    real_isolation.write_text((ROOT / "config/freyja6/future-agent-isolation.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    isolation = tmp_path / "future-agent-isolation.yaml"
    isolation.symlink_to(real_isolation)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        isolation=isolation,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(isolation)]


def test_freyja6_memory_boundary_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=compose,
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(compose)]


def test_freyja6_memory_boundary_audit_rejects_cloud_memory_provider(tmp_path) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_cloud")
    agent_config = _yaml("config/freyja6/freyja-test.yaml")
    agent_config["agents"][0]["memory"]["provider"] = "mem0-cloud"
    agent_path = tmp_path / "freyja-test.yaml"
    agent_path.write_text(yaml.safe_dump(agent_config), encoding="utf-8")

    report = module.build_report(
        agent_config=agent_path,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is False
    assert next(check for check in report["checks"] if check["id"] == "live_agent_memory")["status"] == "fail"
    assert "mem0" in next(check for check in report["checks"] if check["id"] == "no_cloud_memory")["markers"]


def test_freyja6_memory_boundary_audit_rejects_duplicate_future_private_memory(tmp_path) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_duplicate")
    isolation = _yaml("config/freyja6/future-agent-isolation.yaml")
    isolation["future_agents"][1]["private_memory_dir"] = isolation["future_agents"][0]["private_memory_dir"]
    isolation_path = tmp_path / "future-agent-isolation.yaml"
    isolation_path.write_text(yaml.safe_dump(isolation), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        isolation=isolation_path,
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "future_memory_reservations")["failures"]
    assert {"reason": "duplicate_private_memory_dir", "values": ["/var/lib/hermes/agents/freyja/memory/private"]} in failures


def test_freyja6_memory_boundary_audit_rejects_active_future_agent(tmp_path) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_active_future")
    isolation = _yaml("config/freyja6/future-agent-isolation.yaml")
    isolation["future_agents"][0]["status"] = "active"
    isolation_path = tmp_path / "future-agent-isolation.yaml"
    isolation_path.write_text(yaml.safe_dump(isolation), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        isolation=isolation_path,
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "future_memory_reservations")["failures"]
    assert {"reason": "future_agent_not_reserved", "agent": "Freyja", "status": "active"} in failures


def test_freyja6_memory_boundary_audit_rejects_future_live_memory_collision(tmp_path) -> None:
    module = _load_memory_boundary_module("freyja6_memory_boundary_live_collision")
    isolation = _yaml("config/freyja6/future-agent-isolation.yaml")
    isolation["future_agents"][0]["slug"] = "freyja-test"
    isolation["future_agents"][0]["private_memory_dir"] = "/var/lib/hermes/agents/freyja-test/memory/private"
    isolation_path = tmp_path / "future-agent-isolation.yaml"
    isolation_path.write_text(yaml.safe_dump(isolation, sort_keys=True), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        isolation=isolation_path,
    )

    failures = next(check for check in report["checks"] if check["id"] == "future_memory_reservations")["failures"]
    assert {
        "reason": "future_memory_collides_with_live_agent",
        "agent": "Freyja",
        "private_memory_dir": "/var/lib/hermes/agents/freyja-test/memory/private",
    } in failures


def test_freyja6_messaging_gateway_audit_passes_dedicated_discord_config() -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        env_example=ROOT / "deploy/compose/freyja6/.env.example",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "live_discord_gateway")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "no_hardcoded_discord_credentials")["status"] == "pass"


def test_freyja6_messaging_gateway_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_symlink_output")
    real_output = tmp_path / "real-messaging-gateway.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "messaging-gateway.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: messaging-gateway.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_messaging_gateway_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_directory_output")
    output = tmp_path / "messaging-gateway-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: messaging-gateway-dir"


def test_freyja6_messaging_gateway_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_symlink_source")
    real_env = tmp_path / "real-env.example"
    real_env.write_text((ROOT / "deploy/compose/freyja6/.env.example").read_text(encoding="utf-8"), encoding="utf-8")
    env_example = tmp_path / ".env.example"
    env_example.symlink_to(real_env)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))
    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        env_example=env_example,
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(env_example)]


def test_freyja6_messaging_gateway_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))
    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=compose,
        env_example=ROOT / "deploy/compose/freyja6/.env.example",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(compose)]


def test_freyja6_messaging_gateway_audit_rejects_extra_live_discord_env(tmp_path) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_extra")
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    compose["services"]["hermes-freyja-test"]["environment"]["FREYJA6_FREYJA_DISCORD_CHANNEL_ID"] = "${FREYJA6_FREYJA_DISCORD_CHANNEL_ID}"
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(yaml.safe_dump(compose), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=compose_path,
        env_example=ROOT / "deploy/compose/freyja6/.env.example",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "live_discord_gateway")["failures"]
    assert any("unexpected live Discord env vars" in failure for failure in failures)


def test_freyja6_messaging_gateway_audit_allows_discord_trace_env_but_rejects_future_live_env(tmp_path) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_env_example_extra")
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        "\n".join(
            [
                "FREYJA6_DISCORD_BOT_TOKEN=",
                "FREYJA6_DISCORD_CHANNEL_ID=",
                "FREYJA6_DISCORD_SMOKE_MESSAGE_ID=",
                "FREYJA6_DISCORD_SMOKE_REPLY_ID=",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=",
                "FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID=",
                "FREYJA6_FREYJA_DISCORD_CHANNEL_ID=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        env_example=env_example,
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    check = next(item for item in report["checks"] if item["id"] == "env_example_discord")
    assert report["ok"] is False
    assert check["future_live"] == ["FREYJA6_FREYJA_DISCORD_CHANNEL_ID"]


def test_freyja6_messaging_gateway_audit_rejects_hardcoded_discord_credential(tmp_path) -> None:
    module = _load_messaging_gateway_module("freyja6_messaging_gateway_hardcoded")
    agent_config = _yaml("config/freyja6/freyja-test.yaml")
    agent_config["agents"][0]["messaging"]["env"]["token"] = "discord-hardcoded-token"
    agent_path = tmp_path / "freyja-test.yaml"
    agent_path.write_text(yaml.safe_dump(agent_config), encoding="utf-8")

    report = module.build_report(
        agent_config=agent_path,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        env_example=ROOT / "deploy/compose/freyja6/.env.example",
        isolation=ROOT / "config/freyja6/future-agent-isolation.yaml",
    )

    assert report["ok"] is False
    assert next(check for check in report["checks"] if check["id"] == "live_discord_gateway")["status"] == "fail"
    findings = next(check for check in report["checks"] if check["id"] == "no_hardcoded_discord_credentials")["findings"]
    assert any("messaging.env.token" in finding for finding in findings)


def test_freyja6_terminal_safety_audit_passes_mcp_bounded_allowlist() -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "safe_terminal_allowlist")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "terminal_mcp_boundary")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "terminal_server_source")["status"] == "pass"


def test_freyja6_terminal_safety_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety_symlink_output")
    real_output = tmp_path / "real-terminal-safety.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "terminal-safety.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: terminal-safety.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_terminal_safety_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety_directory_output")
    output = tmp_path / "terminal-safety-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: terminal-safety-dir"


def test_freyja6_terminal_safety_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety_symlink_source")
    real_config = tmp_path / "real-freyja-test.yaml"
    real_config.write_text((ROOT / "config/freyja6/freyja-test.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    agent_config = tmp_path / "freyja-test.yaml"
    agent_config.symlink_to(real_config)

    monkeypatch.setattr(module, "_tool_smoke_safe_commands", lambda path: (_ for _ in ()).throw(AssertionError("tool smoke should not be parsed for unsafe source files")))

    report = module.build_report(
        agent_config=agent_config,
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(agent_config)]


def test_freyja6_terminal_safety_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety_directory_source")
    terminal_server = tmp_path / "freyja-terminal-mcp-server.py"
    terminal_server.mkdir()

    monkeypatch.setattr(module, "_tool_smoke_safe_commands", lambda path: (_ for _ in ()).throw(AssertionError("tool smoke should not be parsed for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        terminal_server=terminal_server,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(terminal_server)]


def test_freyja6_terminal_safety_audit_rejects_forbidden_command(tmp_path) -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety_forbidden")
    agent_config = _yaml("config/freyja6/freyja-test.yaml")
    agent_config["agents"][0]["tools"]["terminal"]["safe_commands"].append("rm")
    agent_path = tmp_path / "freyja-test.yaml"
    agent_path.write_text(yaml.safe_dump(agent_config), encoding="utf-8")

    report = module.build_report(
        agent_config=agent_path,
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "safe_terminal_allowlist")["failures"]
    assert any("Forbidden terminal commands" in failure for failure in failures)


def test_freyja6_terminal_safety_audit_rejects_broad_shell_terminal_server(tmp_path) -> None:
    module = _load_terminal_safety_module("freyja6_terminal_safety_broad_shell")
    server_text = (ROOT / "scripts/freyja-terminal-mcp-server.py").read_text(encoding="utf-8")
    server_path = tmp_path / "freyja-terminal-mcp-server.py"
    server_path.write_text(server_text + '\nBROAD_SHELL = "bash"\n', encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        terminal_server=server_path,
    )

    source_check = next(check for check in report["checks"] if check["id"] == "terminal_server_source")
    assert report["ok"] is False
    assert source_check["status"] == "fail"
    assert any("broad-shell" in failure for failure in source_check["failures"])


def test_freyja6_filesystem_boundary_audit_passes_read_only_approved_root() -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        bootstrap=ROOT / "scripts/freyja6-bootstrap-atlas.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        approved_smoke=ROOT / "config/freyja6/bootstrap/approved-smoke.txt",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "approved_filesystem_policy")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "approved_filesystem_mount")["status"] == "pass"


def test_freyja6_filesystem_boundary_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary_symlink_output")
    real_output = tmp_path / "real-filesystem-boundary.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "filesystem-boundary.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: filesystem-boundary.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_filesystem_boundary_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary_directory_output")
    output = tmp_path / "filesystem-boundary-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: filesystem-boundary-dir"


def test_freyja6_filesystem_boundary_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary_symlink_source")
    real_smoke = tmp_path / "real-approved-smoke.txt"
    real_smoke.write_text((ROOT / "config/freyja6/bootstrap/approved-smoke.txt").read_text(encoding="utf-8"), encoding="utf-8")
    approved_smoke = tmp_path / "approved-smoke.txt"
    approved_smoke.symlink_to(real_smoke)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))
    monkeypatch.setattr(module, "_redaction_markers", lambda path: (_ for _ in ()).throw(AssertionError("tool smoke should not be parsed for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        bootstrap=ROOT / "scripts/freyja6-bootstrap-atlas.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        approved_smoke=approved_smoke,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(approved_smoke)]


def test_freyja6_filesystem_boundary_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary_directory_source")
    tool_smoke = tmp_path / "freyja6-tool-smoke.py"
    tool_smoke.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))
    monkeypatch.setattr(module, "_redaction_markers", lambda path: (_ for _ in ()).throw(AssertionError("tool smoke should not be parsed for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
        bootstrap=ROOT / "scripts/freyja6-bootstrap-atlas.py",
        tool_smoke=tool_smoke,
        approved_smoke=ROOT / "config/freyja6/bootstrap/approved-smoke.txt",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(tool_smoke)]


def test_freyja6_filesystem_boundary_audit_rejects_writeable_approved_mount(tmp_path) -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary_writeable")
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    volumes = compose["services"]["hermes-freyja-test"]["volumes"]
    volumes[volumes.index("${FREYJA6_APPROVED_FILES_ROOT}:/workspace/approved:ro")] = "${FREYJA6_APPROVED_FILES_ROOT}:/workspace/approved:rw"
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(yaml.safe_dump(compose), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=compose_path,
        bootstrap=ROOT / "scripts/freyja6-bootstrap-atlas.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        approved_smoke=ROOT / "config/freyja6/bootstrap/approved-smoke.txt",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "approved_filesystem_mount")["failures"]
    assert any("read-only" in failure for failure in failures)


def test_freyja6_filesystem_boundary_audit_rejects_writable_workspace_mount(tmp_path) -> None:
    module = _load_filesystem_boundary_module("freyja6_filesystem_boundary_workspace_rw")
    compose = _yaml("deploy/compose/freyja6/compose.yaml")
    volumes = compose["services"]["hermes-freyja-test"]["volumes"]
    volumes[volumes.index("../../..:/workspace/repo:ro")] = "../../..:/workspace/repo"
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(yaml.safe_dump(compose), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=compose_path,
        bootstrap=ROOT / "scripts/freyja6-bootstrap-atlas.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        approved_smoke=ROOT / "config/freyja6/bootstrap/approved-smoke.txt",
    )

    failures = next(check for check in report["checks"] if check["id"] == "approved_filesystem_mount")["failures"]
    assert report["ok"] is False
    assert "Compose must mount the repository at /workspace/repo read-only." in failures
    assert any("Workspace mounts must be read-only" in failure for failure in failures)


def test_freyja6_mcp_boundary_audit_passes_required_core_tools() -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary")

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "mcp_config")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "gateway_policy")["status"] == "pass"


def test_freyja6_mcp_boundary_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary_symlink_output")
    real_output = tmp_path / "real-mcp-boundary.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "mcp-boundary.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: mcp-boundary.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_mcp_boundary_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary_directory_output")
    output = tmp_path / "mcp-boundary-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: mcp-boundary-dir"


def test_freyja6_mcp_boundary_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary_symlink_source")
    real_config = tmp_path / "real-freyja-test.json"
    real_config.write_text((ROOT / "config/freyja6/mcp/freyja-test.json").read_text(encoding="utf-8"), encoding="utf-8")
    mcp_config = tmp_path / "freyja-test.json"
    mcp_config.symlink_to(real_config)

    monkeypatch.setattr(module, "_load_gateway", lambda: (_ for _ in ()).throw(AssertionError("gateway should not load for unsafe source files")))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=mcp_config,
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(mcp_config)]


def test_freyja6_mcp_boundary_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary_directory_source")
    core_server = tmp_path / "freyja-core-mcp-server.py"
    core_server.mkdir()

    monkeypatch.setattr(module, "_load_gateway", lambda: (_ for _ in ()).throw(AssertionError("gateway should not load for unsafe source files")))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        core_server=core_server,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(core_server)]


def test_freyja6_mcp_boundary_audit_rejects_destructive_calendar_policy(monkeypatch) -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary_destructive")
    gateway = module._load_gateway()
    original = gateway.AGENT_POLICIES["freyja-test"]
    monkeypatch.setitem(gateway.AGENT_POLICIES, "freyja-test", (*original, "calendar.delete_event"))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "gateway_policy")["failures"]
    assert any("forbidden tools" in failure for failure in failures)


def test_freyja6_mcp_boundary_audit_rejects_default_full_access_context(monkeypatch) -> None:
    module = _load_mcp_boundary_module("freyja6_mcp_boundary_default_context")
    gateway = module._load_gateway()
    monkeypatch.setattr(gateway, "current_agent", lambda: "freyja")

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        mcp_config=ROOT / "config/freyja6/mcp/freyja-test.json",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "gateway_policy")["failures"]
    assert "Gateway default agent context must fail closed to generic." in failures


def test_freyja6_coding_workflow_audit_passes_opencode_boundary() -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        core=ROOT / "src/freyja/core.py",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "agent_coding_executor")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "core_opencode_mapping")["status"] == "pass"


def test_freyja6_coding_workflow_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow_symlink_output")
    real_output = tmp_path / "real-coding-workflow.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "coding-workflow.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: coding-workflow.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_coding_workflow_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow_directory_output")
    output = tmp_path / "coding-workflow-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: coding-workflow-dir"


def test_freyja6_coding_workflow_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow_symlink_source")
    real_config = tmp_path / "real-tool-boundaries.yaml"
    real_config.write_text((ROOT / "config/freyja6/tool-boundaries.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    tool_boundaries = tmp_path / "tool-boundaries.yaml"
    tool_boundaries.symlink_to(real_config)

    monkeypatch.setattr(module, "_read_text", lambda path: (_ for _ in ()).throw(AssertionError("source text should not be read for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=tool_boundaries,
        core=ROOT / "src/freyja/core.py",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(tool_boundaries)]


def test_freyja6_coding_workflow_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow_directory_source")
    core = tmp_path / "core.py"
    core.mkdir()

    monkeypatch.setattr(module, "_read_text", lambda path: (_ for _ in ()).throw(AssertionError("source text should not be read for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        core=core,
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(core)]


def test_freyja6_coding_workflow_audit_rejects_non_opencode_executor(tmp_path) -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow_drift")
    agent_config = _yaml("config/freyja6/freyja-test.yaml")
    agent_config["agents"][0]["tools"]["coding_agent"]["executor"] = "hermes-direct"
    agent_path = tmp_path / "freyja-test.yaml"
    agent_path.write_text(yaml.safe_dump(agent_config), encoding="utf-8")

    report = module.build_report(
        agent_config=agent_path,
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        core=ROOT / "src/freyja/core.py",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "agent_coding_executor")["failures"]
    assert "Agent coding executor must remain opencode." in failures


def test_freyja6_coding_workflow_audit_rejects_tool_smoke_without_alias_guard(tmp_path) -> None:
    module = _load_coding_workflow_module("freyja6_coding_workflow_tool_smoke_guard")
    tool_smoke = tmp_path / "freyja6-tool-smoke.py"
    tool_smoke.write_text(
        (ROOT / "scripts/freyja6-tool-smoke.py").read_text(encoding="utf-8").replace(
            "_coding_workflow_result_ok",
            "_coding_workflow_alias_removed",
        ),
        encoding="utf-8",
    )

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        core=ROOT / "src/freyja/core.py",
        core_server=ROOT / "scripts/freyja-core-mcp-server.py",
        tool_smoke=tool_smoke,
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "tool_smoke_coding")["failures"]
    assert "Tool smoke must guard coding workflow acceptance with a dedicated OpenCode alias validator." in failures


def test_freyja6_schedule_boundary_audit_passes_validation_schedules() -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        schedules=ROOT / "config/freyja6/schedules.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "schedule_scope")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "schedule_definitions")["status"] == "pass"


def test_freyja6_schedule_boundary_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary_symlink_output")
    real_output = tmp_path / "real-schedule-boundary.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "schedule-boundary.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: schedule-boundary.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_schedule_boundary_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary_directory_output")
    output = tmp_path / "schedule-boundary-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: schedule-boundary-dir"


def test_freyja6_schedule_boundary_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary_symlink_source")
    real_schedules = tmp_path / "real-schedules.yaml"
    real_schedules.write_text((ROOT / "config/freyja6/schedules.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    schedules = tmp_path / "schedules.yaml"
    schedules.symlink_to(real_schedules)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        schedules=schedules,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(schedules)]


def test_freyja6_schedule_boundary_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("yaml should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        schedules=ROOT / "config/freyja6/schedules.yaml",
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=compose,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(compose)]


def test_freyja6_schedule_boundary_audit_rejects_future_agent_schedule(tmp_path) -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary_future")
    schedules = _yaml("config/freyja6/schedules.yaml")
    schedules["schedules"].append(
        {
            "id": "cloyd-health-heartbeat",
            "kind": "cron",
            "cron": "*/15 * * * *",
            "enabled": True,
            "purpose": "Wake Cloyd before migration.",
            "prompt": "Run Cloyd validation.",
            "evidence": {"log": "/var/log/freyja6/cloyd-acceptance.jsonl"},
        }
    )
    schedules_path = tmp_path / "schedules.yaml"
    schedules_path.write_text(yaml.safe_dump(schedules), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        schedules=schedules_path,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "schedule_definitions")["failures"]
    assert any(item.get("reason") == "unexpected_schedule_ids" for item in failures)


def test_freyja6_schedule_boundary_audit_rejects_heartbeat_acceptance_item_drift(tmp_path) -> None:
    module = _load_schedule_boundary_module("freyja6_schedule_boundary_heartbeat_acceptance")
    schedules = _yaml("config/freyja6/schedules.yaml")
    schedules["schedules"][0]["evidence"]["acceptance_item"] = "atlas_reboot_return"
    schedules_path = tmp_path / "schedules.yaml"
    schedules_path.write_text(yaml.safe_dump(schedules), encoding="utf-8")

    report = module.build_report(
        agent_config=ROOT / "config/freyja6/freyja-test.yaml",
        schedules=schedules_path,
        contract=ROOT / "config/freyja6/hermes-runtime-contract.yaml",
        compose=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "schedule_definitions")["failures"]
    assert {
        "id": "freyja-test-health-heartbeat",
        "reason": "acceptance_item_drift",
        "actual": "atlas_reboot_return",
    } in failures


def test_freyja6_calendar_boundary_audit_passes_guarded_read_create_path() -> None:
    module = _load_calendar_boundary_module("freyja6_calendar_boundary")

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        calendar_smoke=ROOT / "scripts/freyja6-calendar-write-smoke.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "calendar_tool_boundaries")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "calendar_write_smoke")["status"] == "pass"


def test_freyja6_calendar_boundary_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_calendar_boundary_module("freyja6_calendar_boundary_symlink_output")
    real_output = tmp_path / "real-calendar-boundary.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "calendar-boundary.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: calendar-boundary.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_calendar_boundary_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_calendar_boundary_module("freyja6_calendar_boundary_directory_output")
    output = tmp_path / "calendar-boundary-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: calendar-boundary-dir"


def test_freyja6_calendar_boundary_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_calendar_boundary_module("freyja6_calendar_boundary_symlink_source")
    real_boundaries = tmp_path / "real-tool-boundaries.yaml"
    real_boundaries.write_text((ROOT / "config/freyja6/tool-boundaries.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    tool_boundaries = tmp_path / "tool-boundaries.yaml"
    tool_boundaries.symlink_to(real_boundaries)

    monkeypatch.setattr(module, "_load_gateway", lambda: (_ for _ in ()).throw(AssertionError("gateway should not load for unsafe source files")))
    monkeypatch.setattr(module, "_read_text", lambda path: (_ for _ in ()).throw(AssertionError("source text should not be read for unsafe source files")))

    report = module.build_report(
        tool_boundaries=tool_boundaries,
        calendar_smoke=ROOT / "scripts/freyja6-calendar-write-smoke.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(tool_boundaries)]


def test_freyja6_calendar_boundary_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_calendar_boundary_module("freyja6_calendar_boundary_directory_source")
    calendar_smoke = tmp_path / "freyja6-calendar-write-smoke.py"
    calendar_smoke.mkdir()

    monkeypatch.setattr(module, "_load_gateway", lambda: (_ for _ in ()).throw(AssertionError("gateway should not load for unsafe source files")))
    monkeypatch.setattr(module, "_read_text", lambda path: (_ for _ in ()).throw(AssertionError("source text should not be read for unsafe source files")))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        calendar_smoke=calendar_smoke,
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(calendar_smoke)]


def test_freyja6_calendar_boundary_audit_rejects_delete_policy(monkeypatch) -> None:
    module = _load_calendar_boundary_module("freyja6_calendar_boundary_delete")
    gateway = module._load_gateway()
    original = gateway.AGENT_POLICIES["freyja-test"]
    monkeypatch.setitem(gateway.AGENT_POLICIES, "freyja-test", (*original, "calendar.delete_event"))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        calendar_smoke=ROOT / "scripts/freyja6-calendar-write-smoke.py",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "calendar_gateway_policy")["failures"]
    assert "freyja-test policy must not expose calendar.delete_event." in failures


def test_freyja6_home_assistant_boundary_audit_passes_read_only_path() -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary")

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core_mcp=ROOT / "scripts/freyja-core-mcp-server.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "home_assistant_tool_boundaries")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "home_assistant_tool_smoke")["status"] == "pass"


def test_freyja6_home_assistant_boundary_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary_symlink_output")
    real_output = tmp_path / "real-home-assistant-boundary.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "home-assistant-boundary.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: home-assistant-boundary.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_home_assistant_boundary_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary_directory_output")
    output = tmp_path / "home-assistant-boundary-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: home-assistant-boundary-dir"


def test_freyja6_home_assistant_boundary_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary_symlink_source")
    real_boundaries = tmp_path / "real-tool-boundaries.yaml"
    real_boundaries.write_text((ROOT / "config/freyja6/tool-boundaries.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    tool_boundaries = tmp_path / "tool-boundaries.yaml"
    tool_boundaries.symlink_to(real_boundaries)

    monkeypatch.setattr(module, "_load_gateway", lambda: (_ for _ in ()).throw(AssertionError("gateway should not load for unsafe source files")))
    monkeypatch.setattr(module, "_read_text", lambda path: (_ for _ in ()).throw(AssertionError("source text should not be read for unsafe source files")))

    report = module.build_report(
        tool_boundaries=tool_boundaries,
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core_mcp=ROOT / "scripts/freyja-core-mcp-server.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(tool_boundaries)]


def test_freyja6_home_assistant_boundary_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary_directory_source")
    core_mcp = tmp_path / "freyja-core-mcp-server.py"
    core_mcp.mkdir()

    monkeypatch.setattr(module, "_load_gateway", lambda: (_ for _ in ()).throw(AssertionError("gateway should not load for unsafe source files")))
    monkeypatch.setattr(module, "_read_text", lambda path: (_ for _ in ()).throw(AssertionError("source text should not be read for unsafe source files")))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core_mcp=core_mcp,
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(core_mcp)]


def test_freyja6_home_assistant_boundary_audit_requires_states_payload_guard(tmp_path) -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary_states_guard")
    tool_smoke = tmp_path / "freyja6-tool-smoke.py"
    tool_smoke.write_text(
        (ROOT / "scripts/freyja6-tool-smoke.py")
        .read_text(encoding="utf-8")
        .replace('        and ("states" in result_keys or "entities" in result_keys)\n', "")
        .replace('        and isinstance(item.get("states_count"), int)\n        and item["states_count"] > 0\n', ""),
        encoding="utf-8",
    )

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        tool_smoke=tool_smoke,
        core_mcp=ROOT / "scripts/freyja-core-mcp-server.py",
        core=ROOT / "src/freyja/core.py",
    )

    check = next(item for item in report["checks"] if item["id"] == "home_assistant_tool_smoke")
    assert report["ok"] is False
    assert '("states" in result_keys or "entities" in result_keys)' in check["missing"]
    assert 'item["states_count"] > 0' in check["missing"]


def test_freyja6_home_assistant_boundary_audit_rejects_control_policy(monkeypatch) -> None:
    module = _load_home_assistant_boundary_module("freyja6_home_assistant_boundary_control")
    gateway = module._load_gateway()
    original = gateway.TOOL_CATALOG
    monkeypatch.setattr(
        gateway,
        "TOOL_CATALOG",
        (*original, gateway.GatewayTool("home_assistant.control_state", "home", "Control a Home Assistant entity.", "write")),
    )
    original_policy = gateway.AGENT_POLICIES["freyja-test"]
    monkeypatch.setitem(gateway.AGENT_POLICIES, "freyja-test", (*original_policy, "home_assistant.control_state"))

    report = module.build_report(
        tool_boundaries=ROOT / "config/freyja6/tool-boundaries.yaml",
        tool_smoke=ROOT / "scripts/freyja6-tool-smoke.py",
        core_mcp=ROOT / "scripts/freyja-core-mcp-server.py",
        core=ROOT / "src/freyja/core.py",
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "home_assistant_gateway_policy")["failures"]
    assert "freyja-test policy exposes forbidden Home Assistant tools: home_assistant.control_state" in failures


def test_freyja6_tool_boundaries_are_explicit_about_configured_and_pending_surfaces() -> None:
    boundaries = _yaml("config/freyja6/tool-boundaries.yaml")
    targets = boundaries["tool_targets"]

    assert boundaries["agent_id"] == "freyja-test"
    assert targets["filesystem"]["status"] == "configured"
    assert targets["filesystem"]["approved_roots"] == ["/workspace/approved"]
    assert targets["filesystem"]["mode"] == "read_only"
    assert targets["terminal"]["server"] == "freyja-terminal"
    assert targets["terminal"]["safe_commands"] == ["pwd", "date", "whoami", "ls", "rg"]
    assert targets["mcp"]["servers"] == ["freyja-core-gateway", "freyja-terminal"]
    assert targets["calendar"]["server"] == "freyja-core-gateway"
    assert targets["calendar"]["core_tools"] == ["calendar.list_events", "calendar.resolve_date", "calendar.create_event"]
    assert targets["home_assistant"]["status"] == "configured"
    assert targets["home_assistant"]["server"] == "freyja-core-gateway"
    assert targets["home_assistant"]["core_tools"] == ["home_assistant.read_state", "home_assistant.list_states"]
    assert targets["coding_agent"]["executor"] == "opencode"
    assert targets["coding_agent"]["core_tools"] == ["opencode.start", "opencode.status", "opencode.send", "opencode.read", "opencode.stop"]


def test_freyja6_schedules_are_scoped_to_freyja_test_validation() -> None:
    schedules = _yaml("config/freyja6/schedules.yaml")

    assert schedules["agent_id"] == "freyja-test"
    assert [item["id"] for item in schedules["schedules"]] == [
        "freyja-test-health-heartbeat",
        "freyja-test-daily-tool-smoke",
    ]
    assert all(item["enabled"] is True for item in schedules["schedules"])
    assert all("Freyja" not in item["id"] for item in schedules["schedules"])


def test_freyja6_schedule_smoke_validates_config_without_writes(tmp_path) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke")

    report = module.run_smoke(
        schedules_path=ROOT / "config/freyja6/schedules.yaml",
        log_root=tmp_path / "logs",
        write_logs=False,
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "schedule_ids")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "schedule_guardrails")["status"] == "pass"
    assert next(check for check in report["checks"] if check["id"] == "log_writes")["status"] == "skip"
    assert not (tmp_path / "logs").exists()


def test_freyja6_schedule_smoke_rejects_mutating_prompt(tmp_path) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_mutating")
    schedules = _yaml("config/freyja6/schedules.yaml")
    schedules["schedules"][1]["prompt"] = "Run daily smoke and calendar.create_event for a follow-up."
    schedules_path = tmp_path / "schedules.yaml"
    schedules_path.write_text(yaml.safe_dump(schedules), encoding="utf-8")

    report = module.run_smoke(
        schedules_path=schedules_path,
        log_root=tmp_path / "logs",
        write_logs=False,
    )

    assert report["ok"] is False
    failures = next(check for check in report["checks"] if check["id"] == "schedule_guardrails")["failures"]
    assert {"id": "freyja-test-daily-tool-smoke", "reason": "mutating_instruction", "term": "calendar.create_event"} in failures
    assert not (tmp_path / "logs").exists()


def test_freyja6_schedule_smoke_does_not_write_logs_when_config_fails(tmp_path) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_blocked_writes")
    schedules = _yaml("config/freyja6/schedules.yaml")
    schedules["schedules"][1]["prompt"] = "Run daily smoke and calendar.create_event for a follow-up."
    schedules_path = tmp_path / "schedules.yaml"
    schedules_path.write_text(yaml.safe_dump(schedules), encoding="utf-8")

    report = module.run_smoke(
        schedules_path=schedules_path,
        log_root=tmp_path / "logs",
        write_logs=True,
    )

    assert report["ok"] is False
    assert report["writes"] == []
    log_writes = next(check for check in report["checks"] if check["id"] == "log_writes")
    assert log_writes["status"] == "fail"
    assert log_writes["blocked_by"] == ["schedule_guardrails"]
    assert not (tmp_path / "logs").exists()


def test_freyja6_schedule_smoke_writes_redacted_jsonl_entries(tmp_path) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_writes")
    log_audit = _load_log_audit_module("freyja6_schedule_smoke_log_audit_compat")

    report = module.run_smoke(
        schedules_path=ROOT / "config/freyja6/schedules.yaml",
        log_root=tmp_path / "logs",
        write_logs=True,
    )

    assert report["ok"] is True
    assert len(report["writes"]) == 2
    assert {item["log"] for item in report["writes"]} == {
        "freyja6/logs/freyja-test-acceptance.jsonl",
        "freyja6/logs/freyja-test-tools.jsonl",
    }
    acceptance_entry = json.loads((tmp_path / "logs/freyja-test-acceptance.jsonl").read_text(encoding="utf-8"))
    tool_entry = json.loads((tmp_path / "logs/freyja-test-tools.jsonl").read_text(encoding="utf-8"))
    assert acceptance_entry["event"] == "acceptance"
    assert acceptance_entry["acceptance_id"] == "scheduled_validation"
    assert acceptance_entry["status"] == "ok"
    assert tool_entry["event"] == "tool_call"
    assert tool_entry["tool"] == "status.check"
    assert tool_entry["status"] == "ok"
    assert tool_entry["status_code"] == 200
    assert "token" not in str(acceptance_entry).lower()
    assert "token" not in str(tool_entry).lower()

    (tmp_path / "logs/freyja-test-model-calls.jsonl").write_text("", encoding="utf-8")
    audit = log_audit.build_report(log_root=tmp_path / "logs")
    assert audit["ok"] is True


def test_freyja6_schedule_smoke_cli_refuses_symlinked_output_before_log_writes(tmp_path, capsys) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_symlink_output")
    real_output = tmp_path / "real-schedule-smoke.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "schedule-smoke.json"
    output.symlink_to(real_output)

    exit_code = module.main(
        [
            "--schedules",
            str(ROOT / "config/freyja6/schedules.yaml"),
            "--log-root",
            str(tmp_path / "logs"),
            "--write-logs",
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: schedule-smoke.json"
    assert rendered["writes"] == []
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"
    assert not (tmp_path / "logs").exists()


def test_freyja6_schedule_smoke_cli_refuses_directory_output_before_log_writes(tmp_path, capsys) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_directory_output")
    output = tmp_path / "schedule-smoke-dir"
    output.mkdir()

    exit_code = module.main(
        [
            "--schedules",
            str(ROOT / "config/freyja6/schedules.yaml"),
            "--log-root",
            str(tmp_path / "logs"),
            "--write-logs",
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: schedule-smoke-dir"
    assert rendered["writes"] == []
    assert not (tmp_path / "logs").exists()


def test_freyja6_schedule_smoke_rejects_symlinked_log_file(tmp_path) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_symlink_log")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    real_log = tmp_path / "real-tools.jsonl"
    real_log.write_text("sentinel\n", encoding="utf-8")
    (log_root / "freyja-test-tools.jsonl").symlink_to(real_log)

    report = module.run_smoke(
        schedules_path=ROOT / "config/freyja6/schedules.yaml",
        log_root=log_root,
        write_logs=True,
    )

    log_writes = next(check for check in report["checks"] if check["id"] == "log_writes")
    assert report["ok"] is False
    assert report["writes"] == []
    assert log_writes["status"] == "fail"
    assert any(
        item["log"] == "freyja6/logs/freyja-test-tools.jsonl"
        and "Log file must not be a symlink: freyja-test-tools.jsonl." in item["error"]
        for item in log_writes["failed"]
    )
    assert not (log_root / "freyja-test-acceptance.jsonl").exists()
    assert real_log.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_schedule_smoke_requires_exact_expected_log_writes() -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_expected_writes")

    check = module._check_log_writes(
        [
            {
                "ok": True,
                "schedule_id": "freyja-test-health-heartbeat",
                "log": "freyja6/logs/freyja-test-tools.jsonl",
            },
            {
                "ok": True,
                "schedule_id": "freyja-test-daily-tool-smoke",
                "log": "freyja6/logs/freyja-test-acceptance.jsonl",
            },
        ]
    )

    assert check["status"] == "fail"
    assert check["expected"] == {
        "freyja-test-health-heartbeat": "freyja6/logs/freyja-test-acceptance.jsonl",
        "freyja-test-daily-tool-smoke": "freyja6/logs/freyja-test-tools.jsonl",
    }
    assert check["actual"] == {
        "freyja-test-health-heartbeat": "freyja6/logs/freyja-test-tools.jsonl",
        "freyja-test-daily-tool-smoke": "freyja6/logs/freyja-test-acceptance.jsonl",
    }


def test_freyja6_schedule_smoke_verifies_written_log_content(tmp_path) -> None:
    module = _load_schedule_smoke_module("freyja6_schedule_smoke_write_content")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    (log_root / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-other","acceptance_id":"scheduled_validation","status":"ok","source":"freyja6-schedule-smoke"}\n',
        encoding="utf-8",
    )
    (log_root / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-tool","acceptance_id":"scheduled_validation","status":"ok","source":"freyja6-schedule-smoke"}\n',
        encoding="utf-8",
    )

    check = module._check_log_writes(
        [
            {
                "ok": True,
                "schedule_id": "freyja-test-health-heartbeat",
                "log": "freyja6/logs/freyja-test-acceptance.jsonl",
                "trace_id": "trace-heartbeat",
            },
            {
                "ok": True,
                "schedule_id": "freyja-test-daily-tool-smoke",
                "log": "freyja6/logs/freyja-test-tools.jsonl",
                "trace_id": "trace-tool",
            },
        ],
        log_root=log_root,
    )

    assert check["status"] == "fail"
    assert {"schedule_id": "freyja-test-health-heartbeat", "reason": "trace_id_mismatch"} in check["failures"]
    assert {"schedule_id": "freyja-test-daily-tool-smoke", "reason": "invalid_tool_entry"} in check["failures"]


def test_freyja6_live_validation_bundle_runs_required_local_steps_with_fake_runner(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            _write_cmd_output_report(cmd, payload)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    executed = [Path(call[1]).name for call in calls]
    assert report["run_id"].startswith("freyja6-live-")
    uuid.UUID(report["run_id"].removeprefix("freyja6-live-"))
    assert executed == [
        "freyja6-preservation-audit.py",
        "freyja6-env-audit.py",
        "freyja6-hermes-contract.py",
        "freyja6-model-privacy-audit.py",
        "freyja6-gateway-isolation-audit.py",
        "freyja6-memory-boundary-audit.py",
        "freyja6-messaging-gateway-audit.py",
        "freyja6-terminal-safety-audit.py",
        "freyja6-filesystem-boundary-audit.py",
        "freyja6-mcp-boundary-audit.py",
        "freyja6-coding-workflow-audit.py",
        "freyja6-schedule-boundary-audit.py",
        "freyja6-calendar-boundary-audit.py",
        "freyja6-home-assistant-boundary-audit.py",
        "freyja6-hermes-image.py",
        "freyja6-atlas-preflight.py",
        "freyja6-schedule-smoke.py",
        "freyja6-log-audit.py",
        "freyja6-acceptance-status.py",
    ]
    assert report["complete"] is True
    preservation = next(item for item in report["results"] if item["id"] == "preservation_audit")
    assert preservation["report"] == "bundle-preservation-audit.json"
    assert next(item for item in report["results"] if item["id"] == "bootstrap_atlas")["status"] == "skip"


def test_freyja6_live_validation_bundle_refuses_symlinked_output_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_symlink_output")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    real_output = tmp_path / "real-bundle.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "bundle.json"
    output.symlink_to(real_output)
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    try:
        module.run_bundle(
            env_file=env_file,
            evidence=tmp_path / "evidence.json",
            output=output,
            log_root=tmp_path / "logs",
            runner=fake_runner,
        )
    except ValueError as exc:
        assert "Bundle output must not be a symlink: bundle.json." in str(exc)
    else:
        raise AssertionError("symlinked bundle output should be rejected before writing")

    assert calls == []
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_live_validation_bundle_rejects_symlinked_env_file_before_runner(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_symlink_env_source")
    real_env = tmp_path / "real.env"
    real_env.write_text("LITELLM_MASTER_KEY=sk-test\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.symlink_to(real_env)
    output = tmp_path / "bundle.json"
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=output,
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    rendered = json.loads(output.read_text(encoding="utf-8"))
    env_source = next(item for item in report["results"] if item["id"] == "env_source_file")
    assert report["complete"] is False
    assert report["failed_required"] == ["env_source_file"]
    assert env_source["symlinks"] == [str(env_file)]
    assert calls == []
    assert rendered["failed_required"] == ["env_source_file"]


def test_freyja6_live_validation_bundle_rejects_directory_env_file_before_runner(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_directory_env_source")
    env_file = tmp_path / ".env"
    env_file.mkdir()
    output = tmp_path / "bundle.json"
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    monkeypatch.setattr(module, "_load_env", lambda path: (_ for _ in ()).throw(AssertionError("env should not be loaded for unsafe source files")))

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=output,
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_source = next(item for item in report["results"] if item["id"] == "env_source_file")
    assert report["complete"] is False
    assert report["failed_required"] == ["env_source_file"]
    assert env_source["not_regular"] == [str(env_file)]
    assert calls == []
    assert json.loads(output.read_text(encoding="utf-8"))["failed_required"] == ["env_source_file"]


def test_freyja6_live_validation_bundle_rejects_duplicate_step_definitions(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_duplicate_steps")
    env_file = tmp_path / ".env"
    env_file.write_text("HERMES_AGENT_VERSION=v2026.9.14\n", encoding="utf-8")
    original_steps = module._steps

    def duplicate_steps(**kwargs):
        steps = original_steps(**kwargs)
        steps.append({**steps[0]})
        return steps

    monkeypatch.setattr(module, "_steps", duplicate_steps)
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            _write_cmd_output_report(cmd, payload)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    assert calls == []
    assert report["complete"] is False
    assert report["failed_required"] == ["bundle_contract"]
    assert "preservation_audit step id must be unique." in report["step_definition_failures"]


def test_freyja6_live_validation_bundle_rejects_malformed_step_metadata(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_malformed_step_metadata")
    env_file = tmp_path / ".env"
    env_file.write_text("HERMES_AGENT_VERSION=v2026.9.14\n", encoding="utf-8")
    original_steps = module._steps

    def malformed_steps(**kwargs):
        steps = original_steps(**kwargs)
        steps[0]["id"] = 44
        steps[1]["reason"] = None
        steps[2]["report_type"] = ""
        steps[3]["cmd"] = []
        steps[4]["cmd"] = [steps[4]["cmd"][0], 44]
        return steps

    monkeypatch.setattr(module, "_steps", malformed_steps)
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    assert calls == []
    assert report["complete"] is False
    assert report["failed_required"] == ["bundle_contract"]
    assert "step 1 must have an id." in report["step_definition_failures"]
    assert "env_audit reason must be a string." in report["step_definition_failures"]
    assert "hermes_contract report_type must be a non-empty string when present." in report["step_definition_failures"]
    assert "model_privacy_audit cmd must contain string parts." in report["step_definition_failures"]
    assert "gateway_isolation_audit cmd must contain string parts." in report["step_definition_failures"]


def test_freyja6_live_validation_bundle_rejects_report_step_without_output(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_report_step_without_output")
    env_file = tmp_path / ".env"
    env_file.write_text("HERMES_AGENT_VERSION=v2026.9.14\n", encoding="utf-8")
    original_steps = module._steps

    def missing_output_steps(**kwargs):
        steps = original_steps(**kwargs)
        env_audit = next(step for step in steps if step["id"] == "env_audit")
        output_index = env_audit["cmd"].index("--output")
        del env_audit["cmd"][output_index : output_index + 2]
        return steps

    monkeypatch.setattr(module, "_steps", missing_output_steps)
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    assert calls == []
    assert report["complete"] is False
    assert report["failed_required"] == ["bundle_contract"]
    assert "env_audit report-bearing command must include --output." in report["step_definition_failures"]


def test_freyja6_live_validation_bundle_requires_log_entries_only_in_live_mode(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_log_entries")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_BOT_TOKEN=discord-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-test",
                "FREYJA6_MEMORY_RECALL_TRACE_ID=trace-memory-recall",
                "FREYJA6_REBOOT_START=2026-09-19T10:00:00+00:00",
                "FREYJA6_REBOOT_END=2026-09-19T10:03:00+00:00",
                "FREYJA6_CONTAINER_STATUS_AFTER=running (healthy)",
                "FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID=trace-discord-after-reboot",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            _write_cmd_output_report(cmd, payload)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=False,
        runner=fake_runner,
    )
    local_log_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-log-audit.py")
    assert "--require-entries" not in local_log_cmd

    calls.clear()
    module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle-live.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )
    live_log_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-log-audit.py")
    assert "--require-entries" in live_log_cmd


def test_freyja6_live_validation_bundle_live_mode_marks_missing_discord_required_skip(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_live_skip")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        runner=fake_runner,
    )

    discord = next(item for item in report["results"] if item["id"] == "discord_reply")
    assert discord["required"] is True
    assert discord["status"] == "skip"
    assert report["complete"] is False
    assert "discord_reply" in report["skipped_required"]
    assert "calendar_write" in report["skipped_required"]
    assert "restart_evidence" in report["skipped_required"]


def test_freyja6_live_validation_bundle_requires_complete_discord_manual_evidence(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_partial_discord")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        runner=fake_runner,
    )

    assert "freyja6-discord-smoke.py" not in [Path(call[1]).name for call in calls]
    discord = next(item for item in report["results"] if item["id"] == "discord_reply")
    assert discord["status"] == "skip"
    assert report["skipped_required"] == ["discord_reply", "calendar_write", "restart_evidence"]


def test_freyja6_live_validation_bundle_requires_discord_api_evidence(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_discord_api_required")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        runner=fake_runner,
    )

    assert "freyja6-discord-smoke.py" not in [Path(call[1]).name for call in calls]
    discord = next(item for item in report["results"] if item["id"] == "discord_reply")
    assert discord["required"] is True
    assert discord["status"] == "skip"
    assert discord["summary"] == "Set Discord bot token, channel ID, and message/reply IDs for API verification."
    assert "discord_reply" in report["skipped_required"]


def test_freyja6_live_validation_bundle_rejects_failed_payload_with_zero_exit(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_payload_failure")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": false, "status": "fail", "failures": ["drift"]}\n', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["payload_failure"] is True
    assert env_audit["report"] == "bundle-env-audit.json"
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_nested_failed_check_with_zero_exit(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_nested_payload_failure")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout='{"report_type":"freyja6-env-audit","checks":[{"id":"nested","status":"fail","message":"nested drift"}]}\n',
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["payload_failure"] is True
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_mismatched_report_type(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_report_type")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout='{"ok": true, "status": "complete", "report_type": "freyja6-preservation-audit"}\n',
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["report_type_failure"] == "report_type must be freyja6-env-audit, got freyja6-preservation-audit."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_typed_payload_without_success_signal(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_hollow_success")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(cmd, 0, stdout='{"report_type":"freyja6-env-audit","checks":[]}\n', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["contract_failure"] == "env_audit payload must include an explicit success signal."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_missing_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_missing_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete", "report_type": "freyja6-env-audit"}\n', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report must exist and be valid JSON."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_refuses_existing_symlinked_side_report_before_runner(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_existing_symlink_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    real_report = tmp_path / "real-env-audit.json"
    real_report.write_text("sentinel\n", encoding="utf-8")
    (tmp_path / "bundle-env-audit.json").symlink_to(real_report)
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    assert calls == []
    assert report["complete"] is False
    assert report["failed_required"] == ["bundle_contract"]
    assert "env_audit side report output must not be a symlink: bundle-env-audit.json." in report["step_definition_failures"]
    assert real_report.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_live_validation_bundle_rejects_side_report_outside_bundle_directory(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_side_report_escape")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    original_steps = module._steps

    def escaped_side_report_steps(**kwargs):
        steps = original_steps(**kwargs)
        env_audit = next(step for step in steps if step["id"] == "env_audit")
        output_index = env_audit["cmd"].index("--output")
        env_audit["cmd"][output_index + 1] = str(tmp_path / "outside" / "bundle-env-audit.json")
        return steps

    monkeypatch.setattr(module, "_steps", escaped_side_report_steps)
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    assert calls == []
    assert report["complete"] is False
    assert report["failed_required"] == ["bundle_contract"]
    assert "env_audit side report output must stay next to the bundle output: bundle-env-audit.json." in report["step_definition_failures"]


def test_freyja6_live_validation_bundle_rejects_symlinked_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_symlinked_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            output = Path(_option_value(cmd, "--output"))
            output.parent.mkdir(parents=True, exist_ok=True)
            real_report = tmp_path / "real-env-audit.json"
            real_report.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "report_type": "freyja6-env-audit",
                        "timestamp": "2026-09-19T00:00:00+00:00",
                        "ok": True,
                        "status": "ready",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output.symlink_to(real_report)
            return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete", "report_type": "freyja6-env-audit"}\n', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report must not be a symlink."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_wrong_typed_side_report_type(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_wrong_typed_side_report_type")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            payload = {"ok": True, "status": "complete", "report_type": "freyja6-env-audit"}
            _write_cmd_output_report(cmd, {**payload, "report_type": "freyja6-preservation-audit"})
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report must have report_type freyja6-env-audit."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_old_schema_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_old_schema_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            payload = {"ok": True, "status": "complete", "report_type": "freyja6-env-audit"}
            _write_cmd_output_report(cmd, {**payload, "schema_version": "0.9"})
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report schema_version must be 1.0."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_failing_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_failing_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            payload = {"ok": True, "status": "complete", "report_type": "freyja6-env-audit"}
            _write_cmd_output_report(cmd, {"ok": False, "status": "fail", "report_type": "freyja6-env-audit"})
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report must not indicate failure."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_hollow_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_hollow_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            payload = {"ok": True, "status": "complete", "report_type": "freyja6-env-audit"}
            _write_cmd_output_report(cmd, {"report_type": "freyja6-env-audit", "checks": []})
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report must include an explicit success signal."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_untimestamped_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_untimestamped_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            payload = {"ok": True, "status": "complete", "report_type": "freyja6-env-audit"}
            output = Path(_option_value(cmd, "--output"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"schema_version": "1.0", **payload}) + "\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report timestamp must be present."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_non_object_typed_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_non_object_typed_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            payload = {"ok": True, "status": "complete", "report_type": "freyja6-env-audit"}
            output = Path(_option_value(cmd, "--output"))
            output.write_text('["freyja6-env-audit"]\n', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["side_report_failure"] == "bundle-env-audit.json side report must be a JSON object."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_running_typed_payload(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_running_typed_payload")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(cmd, 0, stdout='{"report_type":"freyja6-env-audit","status":"running"}\n', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["contract_failure"] == "env_audit payload must include an explicit success signal."
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_not_ready_payload_with_zero_exit(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_not_ready_payload")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(cmd, 0, stdout='{"status": "not-ready", "message": "env drift"}\n', stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["payload_failure"] is True
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_rejects_missing_json_payload_with_zero_exit(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_missing_payload")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-env-audit.py":
            return subprocess.CompletedProcess(cmd, 0, stdout="looks fine\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        runner=fake_runner,
    )

    env_audit = next(item for item in report["results"] if item["id"] == "env_audit")
    assert env_audit["status"] == "fail"
    assert env_audit["payload_missing"] is True
    assert report["complete"] is False
    assert report["failed_required"] == ["env_audit"]


def test_freyja6_live_validation_bundle_redacts_api_key_in_commands(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_redact")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-local-secret",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        runner=fake_runner,
    )

    commands = [part for item in report["results"] for part in item["command"]]
    assert "sk-local-secret" not in commands
    assert "<redacted>" in commands


def test_freyja6_live_validation_bundle_runs_required_acceptance_helpers_when_flagged(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_required_acceptance_helpers")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
                "FREYJA6_CALENDAR_WRITE_CALENDAR_ID=configured-calendar",
                "FREYJA6_RESTORED_SESSION_ID=session-validation",
                "FREYJA6_MEMORY_FACT_LABEL=freyja6-validation-basement-cleanup",
                "FREYJA6_MEMORY_RECALL_TRACE_ID=trace-memory-recall",
                "FREYJA6_CONTAINER_STATUS_AFTER=running (healthy)",
                "FREYJA6_REBOOT_START=2026-09-19T10:00:00+00:00",
                "FREYJA6_REBOOT_END=2026-09-19T10:03:00+00:00",
                "FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID=trace-discord-after-reboot",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_runner(cmd):
        calls.append(Path(cmd[1]).name)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    assert "freyja6-calendar-write-smoke.py" in calls
    assert "freyja6-restart-evidence.py" in calls
    assert "calendar_write" not in report["skipped_required"]
    assert "restart_evidence" not in report["skipped_required"]


def test_freyja6_live_validation_bundle_forwards_env_overrides_to_live_helpers(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_env_forwarding")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_LITELLM_BASE_URL=http://127.0.0.1:9460/v1",
                "FREYJA6_CORE_URL=http://127.0.0.1:9510",
                "FREYJA6_CORE_MCP_HEALTH_URL=http://127.0.0.1:9766/healthz",
                "FREYJA6_TERMINAL_MCP_HEALTH_URL=http://127.0.0.1:9765/healthz",
                "FREYJA6_APPROVED_SMOKE_FILE=/srv/freyja6/approved-files/custom-smoke.txt",
                "FREYJA6_CALENDAR_SMOKE_START=2026-09-20T00:00:00+00:00",
                "FREYJA6_CALENDAR_SMOKE_END=2026-09-21T00:00:00+00:00",
                "FREYJA6_HOME_SMOKE_DOMAIN=light",
                "FREYJA6_DISCORD_BOT_TOKEN=discord-secret",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_SMOKE_MESSAGE_ID=message-id",
                "FREYJA6_DISCORD_SMOKE_REPLY_ID=reply-id",
                "FREYJA6_CALENDAR_WRITE_CALENDAR_ID=configured-calendar",
                "FREYJA6_CALENDAR_WRITE_BASE_DATE=2026-09-20",
                "FREYJA6_CALENDAR_WRITE_START_TIME=10:30:00",
                "FREYJA6_HERMES_DATA=/srv/freyja6/hermes-custom",
                "FREYJA6_RESTORED_SESSION_ID=session-validation",
                "FREYJA6_MEMORY_FACT_LABEL=freyja6-validation-basement-cleanup",
                "FREYJA6_MEMORY_RECALL_TRACE_ID=trace-memory-recall",
                "FREYJA6_CONTAINER_STATUS_AFTER=running (healthy)",
                "FREYJA6_REBOOT_START=2026-09-20T10:00:00+00:00",
                "FREYJA6_REBOOT_END=2026-09-20T10:03:00+00:00",
                "FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID=trace-discord-after-reboot",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            _write_cmd_output_report(cmd, payload)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        prepare_restart_evidence=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    discord_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-discord-smoke.py")
    litellm_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-litellm-smoke.py")
    tool_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-tool-smoke.py")
    calendar_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-calendar-write-smoke.py")
    prepare_restart_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-prepare-restart-evidence.py")
    restart_cmd = next(call for call in calls if Path(call[1]).name == "freyja6-restart-evidence.py")

    assert _option_value(discord_cmd, "--bot-token") == "discord-secret"
    assert _option_value(discord_cmd, "--message-id") == "message-id"
    assert _option_value(discord_cmd, "--reply-id") == "reply-id"
    assert _option_value(litellm_cmd, "--base-url") == "http://127.0.0.1:9460/v1"
    assert _option_value(tool_cmd, "--core-url") == "http://127.0.0.1:9510"
    assert _option_value(tool_cmd, "--core-mcp-health-url") == "http://127.0.0.1:9766/healthz"
    assert _option_value(tool_cmd, "--terminal-mcp-health-url") == "http://127.0.0.1:9765/healthz"
    assert _option_value(tool_cmd, "--approved-file") == "/srv/freyja6/approved-files/custom-smoke.txt"
    assert _option_value(tool_cmd, "--calendar-start") == "2026-09-20T00:00:00+00:00"
    assert _option_value(tool_cmd, "--calendar-end") == "2026-09-21T00:00:00+00:00"
    assert _option_value(tool_cmd, "--home-domain") == "light"
    assert _option_value(calendar_cmd, "--core-url") == "http://127.0.0.1:9510"
    assert _option_value(calendar_cmd, "--base-date") == "2026-09-20"
    assert _option_value(calendar_cmd, "--start-time") == "10:30:00"
    assert _option_value(prepare_restart_cmd, "--hermes-data") == "/srv/freyja6/hermes-custom"
    assert _option_value(restart_cmd, "--hermes-data") == "/srv/freyja6/hermes-custom"
    assert report["complete"] is True
    commands = [part for item in report["results"] for part in item["command"]]
    assert "discord-secret" not in commands


def test_freyja6_live_validation_bundle_rejects_acceptance_status_evidence_mismatch(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_acceptance_evidence_mismatch")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = {
                "ok": True,
                "status": "complete",
                "complete": True,
                "report_type": "freyja6-acceptance-status",
                "evidence": str(tmp_path / "stale-evidence.json"),
            }
            _write_cmd_output_report(cmd, payload)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["contract_failure"] == "acceptance_status evidence must match the bundle evidence path."


def test_freyja6_live_validation_bundle_rejects_side_report_evidence_mismatch(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_side_report_evidence_mismatch")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = {
                "ok": True,
                "status": "complete",
                "complete": True,
                "report_type": "freyja6-acceptance-status",
                "evidence": _option_value(cmd, "--evidence"),
            }
            side_report = {**payload, "evidence": str(tmp_path / "stale-evidence.json")}
            _write_cmd_output_report(cmd, side_report)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["side_report_failure"] == "bundle-acceptance-status.json side report evidence must match the bundle evidence path."


def test_freyja6_live_validation_bundle_rejects_hollow_acceptance_status_side_report(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_hollow_acceptance_side_report")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            _write_cmd_output_report(
                cmd,
                {
                    "report_type": "freyja6-acceptance-status",
                    "status": "complete",
                    "complete": True,
                    "ok": True,
                    "evidence": _option_value(cmd, "--evidence"),
                },
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["side_report_failure"] == "bundle-acceptance-status.json side report must report secrets_detected false."


def test_freyja6_live_validation_bundle_rejects_acceptance_side_report_missing_required_item(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_acceptance_side_report_missing_item")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            side_report = {**payload, "acceptance": payload["acceptance"][:-1]}
            _write_cmd_output_report(cmd, side_report)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["side_report_failure"] == "bundle-acceptance-status.json side report acceptance must include atlas_reboot_return."


def test_freyja6_live_validation_bundle_rejects_acceptance_side_report_contract_drift(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_acceptance_side_report_contract_drift")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            side_report = json.loads(json.dumps(payload))
            model_switch = next(item for item in side_report["acceptance"] if item["id"] == "model_switch")
            model_switch["required_evidence"] = ["models_tested", "gateway_trace_ids"]
            _write_cmd_output_report(cmd, side_report)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["side_report_failure"] == "bundle-acceptance-status.json side report acceptance model_switch required_evidence must match the Freyja 6 acceptance contract."


def test_freyja6_live_validation_bundle_rejects_acceptance_side_report_wrong_metadata_source(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_acceptance_side_report_metadata_source")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            side_report = json.loads(json.dumps(payload))
            calendar = next(item for item in side_report["acceptance"] if item["id"] == "calendar_create_event")
            calendar["metadata"]["source"] = "freyja6-tool-smoke"
            _write_cmd_output_report(cmd, side_report)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["side_report_failure"] == "bundle-acceptance-status.json side report acceptance calendar_create_event metadata source must be freyja6-calendar-write-smoke."


def test_freyja6_live_validation_bundle_rejects_acceptance_side_report_bad_metadata_timestamp(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_acceptance_side_report_metadata_timestamp")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                "FREYJA6_DISCORD_CHANNEL_ID=channel-redacted",
                "FREYJA6_DISCORD_MESSAGE_TRACE_ID=trace-message",
                "FREYJA6_DISCORD_REPLY_TRACE_ID=trace-reply",
                "FREYJA6_DISCORD_MANUAL_CONFIRMATION=DISCORD_REPLY_VERIFIED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        if Path(cmd[1]).name == "freyja6-acceptance-status.py":
            payload = _complete_acceptance_cmd_payload(cmd)
            side_report = json.loads(json.dumps(payload))
            discord = next(item for item in side_report["acceptance"] if item["id"] == "discord_reply")
            discord["metadata"]["captured_at"] = "2026-09-19T00:00:00"
            _write_cmd_output_report(cmd, side_report)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle.json",
        log_root=tmp_path / "logs",
        live=True,
        calendar_write=True,
        restart_evidence=True,
        runner=fake_runner,
    )

    acceptance = next(item for item in report["results"] if item["id"] == "acceptance_status")
    assert report["complete"] is False
    assert report["failed_required"] == ["acceptance_status"]
    assert acceptance["side_report_failure"] == "bundle-acceptance-status.json side report acceptance discord_reply metadata captured_at must be an ISO timestamp with timezone."


def test_freyja6_live_validation_bundle_uses_env_log_root_unless_overridden(tmp_path) -> None:
    import subprocess

    module = _load_live_bundle_module("freyja6_live_validation_bundle_log_root_env")
    env_file = tmp_path / ".env"
    env_log_root = tmp_path / "srv" / "freyja6" / "logs"
    cli_log_root = tmp_path / "cli" / "logs"
    env_file.write_text(
        "\n".join(
            [
                "HERMES_AGENT_VERSION=v2026.9.14",
                "HERMES_AGENT_IMAGE=hermes-agent-local:v2026.9.14",
                "LITELLM_MASTER_KEY=sk-test",
                f"FREYJA6_LOG_ROOT={env_log_root}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_runner(cmd):
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "status": "complete"}\n', stderr="")

    env_report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle-env.json",
        log_root=None,
        runner=fake_runner,
    )
    schedule_cmd = next(item["command"] for item in env_report["results"] if item["id"] == "schedule_smoke")
    assert _option_value(schedule_cmd, "--log-root") == str(env_log_root)
    assert env_report["log_root"] == "logs"

    cli_report = module.run_bundle(
        env_file=env_file,
        evidence=tmp_path / "evidence.json",
        output=tmp_path / "bundle-cli.json",
        log_root=cli_log_root,
        runner=fake_runner,
    )
    schedule_cmd = next(item["command"] for item in cli_report["results"] if item["id"] == "schedule_smoke")
    assert _option_value(schedule_cmd, "--log-root") == str(cli_log_root)
    assert cli_report["log_root"] == "logs"


def test_freyja6_live_validation_bundle_summarizes_top_level_json() -> None:
    module = _load_live_bundle_module("freyja6_live_validation_bundle_summary")
    payload = module._last_json(
        """
        {
          "blockers": [{"message": "top-level blocker"}],
          "checks": [{"id": "nested", "status": "fail"}],
          "ready": false
        }
        """
    )

    assert module._summary_from_payload(payload) == "top-level blocker"


def test_freyja6_stack_status_passes_for_running_services_and_logs(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_stack_status_module("freyja6_stack_status")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    for log_name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl"):
        (tmp_path / log_name).write_text("", encoding="utf-8")

    def fake_runner(cmd):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="\n".join(
                [
                    '{"Service":"litellm-db","State":"running"}',
                    '{"Service":"litellm","State":"running (healthy)"}',
                    '{"Service":"hermes-freyja-test","State":"running"}',
                ]
            ),
            stderr="",
        )

    report = module.build_report(
        env_file=ROOT / "deploy/compose/freyja6/.env.example",
        compose_file=ROOT / "deploy/compose/freyja6/compose.yaml",
        log_root=tmp_path,
        runner=fake_runner,
    )

    assert report["ok"] is True
    assert next(check for check in report["checks"] if check["id"] == "compose_ps")["status"] == "pass"
    assert report["log_root_redacted"] == tmp_path.name


def test_freyja6_stack_status_cli_refuses_symlinked_output(tmp_path, monkeypatch, capsys) -> None:
    module = _load_stack_status_module("freyja6_stack_status_symlink_output")
    monkeypatch.setattr(
        module,
        "build_report",
        lambda **kwargs: {
            "schema_version": "1.0",
            "report_type": "freyja6-stack-status",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ok": True,
            "status": "running",
        },
    )
    real_output = tmp_path / "real-stack-status.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "stack-status.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "not-ready"
    assert rendered["error"] == "output path must not be a symlink: stack-status.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_stack_status_cli_refuses_directory_output(tmp_path, monkeypatch, capsys) -> None:
    module = _load_stack_status_module("freyja6_stack_status_directory_output")
    monkeypatch.setattr(
        module,
        "build_report",
        lambda **kwargs: {
            "schema_version": "1.0",
            "report_type": "freyja6-stack-status",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ok": True,
            "status": "running",
        },
    )
    output = tmp_path / "stack-status-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "not-ready"
    assert rendered["error"] == "output path must be a regular file: stack-status-dir"


def test_freyja6_stack_status_fails_for_missing_service_or_log(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_stack_status_module("freyja6_stack_status_missing")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    def fake_runner(cmd):
        return subprocess.CompletedProcess(cmd, 0, stdout='[{"Service":"litellm","State":"running"}]', stderr="")

    report = module.build_report(
        env_file=ROOT / "deploy/compose/freyja6/.env.example",
        compose_file=ROOT / "deploy/compose/freyja6/compose.yaml",
        log_root=tmp_path,
        runner=fake_runner,
    )

    assert report["ok"] is False
    compose_check = next(check for check in report["checks"] if check["id"] == "compose_ps")
    assert compose_check["missing"] == ["litellm-db", "hermes-freyja-test"]
    logs_check = next(check for check in report["checks"] if check["id"] == "logs")
    assert "freyja-test-model-calls.jsonl" in logs_check["missing"]


def test_freyja6_stack_status_rejects_unexpected_future_agent_service(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_stack_status_module("freyja6_stack_status_unexpected")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    for log_name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl"):
        (tmp_path / log_name).write_text("", encoding="utf-8")

    def fake_runner(cmd):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="\n".join(
                [
                    '{"Service":"litellm-db","State":"running"}',
                    '{"Service":"litellm","State":"running (healthy)"}',
                    '{"Service":"hermes-freyja-test","State":"running"}',
                    '{"Service":"hermes-cloyd","State":"running"}',
                ]
            ),
            stderr="",
        )

    report = module.build_report(
        env_file=ROOT / "deploy/compose/freyja6/.env.example",
        compose_file=ROOT / "deploy/compose/freyja6/compose.yaml",
        log_root=tmp_path,
        runner=fake_runner,
    )

    compose_check = next(check for check in report["checks"] if check["id"] == "compose_ps")
    assert report["ok"] is False
    assert compose_check["status"] == "fail"
    assert compose_check["unexpected"] == ["hermes-cloyd"]


def test_freyja6_stack_status_rejects_log_directories(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_stack_status_module("freyja6_stack_status_log_directory")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    (tmp_path / "freyja-test-tools.jsonl").mkdir()
    (tmp_path / "freyja-test-model-calls.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "freyja-test-acceptance.jsonl").write_text("", encoding="utf-8")

    def fake_runner(cmd):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="\n".join(
                [
                    '{"Service":"litellm-db","State":"running"}',
                    '{"Service":"litellm","State":"running (healthy)"}',
                    '{"Service":"hermes-freyja-test","State":"running"}',
                ]
            ),
            stderr="",
        )

    report = module.build_report(
        env_file=ROOT / "deploy/compose/freyja6/.env.example",
        compose_file=ROOT / "deploy/compose/freyja6/compose.yaml",
        log_root=tmp_path,
        runner=fake_runner,
    )

    logs_check = next(check for check in report["checks"] if check["id"] == "logs")
    assert report["ok"] is False
    assert logs_check["not_files"] == ["freyja-test-tools.jsonl"]


def test_freyja6_stack_status_rejects_log_symlinks(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_stack_status_module("freyja6_stack_status_log_symlink")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    real_log = tmp_path / "real-tools.jsonl"
    real_log.write_text("", encoding="utf-8")
    (tmp_path / "freyja-test-tools.jsonl").symlink_to(real_log)
    (tmp_path / "freyja-test-model-calls.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "freyja-test-acceptance.jsonl").write_text("", encoding="utf-8")

    def fake_runner(cmd):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="\n".join(
                [
                    '{"Service":"litellm-db","State":"running"}',
                    '{"Service":"litellm","State":"running (healthy)"}',
                    '{"Service":"hermes-freyja-test","State":"running"}',
                ]
            ),
            stderr="",
        )

    report = module.build_report(
        env_file=ROOT / "deploy/compose/freyja6/.env.example",
        compose_file=ROOT / "deploy/compose/freyja6/compose.yaml",
        log_root=tmp_path,
        runner=fake_runner,
    )

    logs_check = next(check for check in report["checks"] if check["id"] == "logs")
    assert report["ok"] is False
    assert logs_check["symlinks"] == ["freyja-test-tools.jsonl"]


def test_freyja6_stack_status_rejects_not_running_substring(tmp_path, monkeypatch) -> None:
    import subprocess

    module = _load_stack_status_module("freyja6_stack_status_not_running")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    for log_name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl"):
        (tmp_path / log_name).write_text("", encoding="utf-8")

    def fake_runner(cmd):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="\n".join(
                [
                    '{"Service":"litellm-db","State":"running"}',
                    '{"Service":"litellm","State":"not running"}',
                    '{"Service":"hermes-freyja-test","State":"running"}',
                ]
            ),
            stderr="",
        )

    report = module.build_report(
        env_file=ROOT / "deploy/compose/freyja6/.env.example",
        compose_file=ROOT / "deploy/compose/freyja6/compose.yaml",
        log_root=tmp_path,
        runner=fake_runner,
    )

    compose_check = next(check for check in report["checks"] if check["id"] == "compose_ps")
    assert report["ok"] is False
    assert compose_check["not_running"] == [{"service": "litellm", "status": "not running"}]


def test_freyja6_log_audit_passes_for_redacted_jsonl_entries(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit")
    _write_complete_log_audit_logs(tmp_path)

    report = module.build_report(log_root=tmp_path, require_entries=True)

    assert report["ok"] is True
    assert {check["entry_count"] for check in report["checks"]} == {3, 7, 13}
    assert report["log_root_redacted"] == tmp_path.name


def test_freyja6_log_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_log_audit_module("freyja6_log_audit_symlink_output")
    _write_complete_log_audit_logs(tmp_path)
    real_output = tmp_path / "real-log-audit.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "log-audit.json"
    output.symlink_to(real_output)

    exit_code = module.main(
        [
            "--log-root",
            str(tmp_path),
            "--require-entries",
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: log-audit.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_log_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_log_audit_module("freyja6_log_audit_directory_output")
    _write_complete_log_audit_logs(tmp_path)
    output = tmp_path / "log-audit-dir"
    output.mkdir()

    exit_code = module.main(
        [
            "--log-root",
            str(tmp_path),
            "--require-entries",
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: log-audit-dir"


def test_freyja6_log_audit_requires_all_live_acceptance_ids_when_entries_required(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_live_acceptance_coverage")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-discord","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert any(failure.startswith("acceptance log must include all live acceptance ids:") for failure in failures)
    assert "scheduled_validation" not in failures[-1]


def test_freyja6_log_audit_rejects_secret_markers(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_secret")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool","trace_id":"trace-tool","tool":"status.check","status":"ok","token":"do-not-log"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    assert report["ok"] is False
    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    assert tool_log["status"] == "fail"
    assert "secret" in tool_log["message"]


def test_freyja6_log_audit_rejects_symlinked_log_files(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_symlink")
    real_tool_log = tmp_path / "real-tools.jsonl"
    real_tool_log.write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-tools.jsonl").symlink_to(real_tool_log)
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    assert report["ok"] is False
    assert tool_log["status"] == "fail"
    assert "regular file" in tool_log["message"]


def test_freyja6_log_audit_rejects_unstructured_entries(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_unstructured")
    (tmp_path / "freyja-test-tools.jsonl").write_text('{"event":"tool","trace_id":"trace-tool","status":"ok","source":"freyja6-log-audit-test"}\n', encoding="utf-8")
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    assert report["ok"] is False
    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    assert tool_log["status"] == "fail"
    assert tool_log["incomplete_entries"][0]["missing"] == ["timestamp", "tool"]


def test_freyja6_log_audit_rejects_wrong_event_or_status_values(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_semantics")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool","trace_id":"trace-tool","tool":"status.check","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"complete","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"failed","source":"freyja6-discord-smoke"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    assert report["ok"] is False
    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    model_log = next(check for check in report["checks"] if check["id"] == "model_log")
    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    assert tool_log["semantic_failures"][0]["failures"] == ["event must be tool_call."]
    assert model_log["semantic_failures"][0]["failures"] == ["status must be one of: failed, ok."]
    assert acceptance_log["semantic_failures"][0]["failures"] == ["status must be one of: ok."]


def test_freyja6_log_audit_requires_failed_tool_and_model_diagnostics(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_failed_diagnostics")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"failed","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"failed","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    model_log = next(check for check in report["checks"] if check["id"] == "model_log")
    assert report["ok"] is False
    assert "failed tool/model log entries must include error_summary." in tool_log["semantic_failures"][0]["failures"]
    assert "failed tool/model log entries must include error_summary." in model_log["semantic_failures"][0]["failures"]


def test_freyja6_log_audit_requires_status_codes_for_ok_http_tool_calls(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_tool_status_code")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-terminal","tool":"terminal.safe_command","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"tool_call","trace_id":"trace-mcp","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:02:00+00:00","event":"tool_call","trace_id":"trace-calendar","tool":"calendar.list_events","status":"ok","status_code":503,"source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-discord","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    failures = [failure for item in tool_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "ok HTTP-backed tool_call status_code must be an integer." in failures
    assert "ok HTTP-backed tool_call status_code must be 2xx." in failures


def test_freyja6_log_audit_allows_failed_tool_and_model_with_redacted_diagnostics(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_failed_diagnostics_ok")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"failed","source":"freyja6-log-audit-test","error_summary":"health endpoint unavailable"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"failed","status_code":504,"source":"freyja6-log-audit-test","error_summary":"gateway timeout"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    model_log = next(check for check in report["checks"] if check["id"] == "model_log")
    assert tool_log["status"] == "pass"
    assert model_log["status"] == "pass"


def test_freyja6_log_audit_rejects_unapproved_log_values(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_allowed_values")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"calendar.delete_event","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"gpt-4o","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"future_agent_ready","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    model_log = next(check for check in report["checks"] if check["id"] == "model_log")
    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    assert report["ok"] is False
    assert "tool must be an approved Freyja 6 tool log name." in tool_log["semantic_failures"][0]["failures"]
    assert "model must be an approved Freyja 6 Vulcan alias." in model_log["semantic_failures"][0]["failures"]
    assert "acceptance_id must be an approved Freyja 6 acceptance item." in acceptance_log["semantic_failures"][0]["failures"]


def test_freyja6_log_audit_rejects_reused_restart_acceptance_traces(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_acceptance_trace_reuse")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-discord-reply","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-restart","acceptance_id":"restart_identity_session","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:02:00+00:00","event":"acceptance","trace_id":"trace-restart","acceptance_id":"remember_fact","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:03:00+00:00","event":"acceptance","trace_id":"trace-discord-reply","acceptance_id":"atlas_reboot_return","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "remember_fact trace_id must be distinct from restart_identity_session trace_id." in failures
    assert "atlas_reboot_return trace_id must be distinct from discord_reply trace_id." in failures


def test_freyja6_log_audit_allows_repeated_acceptance_ids_with_distinct_traces(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_repeated_acceptance_ids")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-restart","acceptance_id":"restart_identity_session","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-restart","acceptance_id":"remember_fact","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:02:00+00:00","event":"acceptance","trace_id":"trace-restart-later","acceptance_id":"restart_identity_session","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "remember_fact trace_id must be distinct from restart_identity_session trace_id." in failures


def test_freyja6_log_audit_rejects_repeated_acceptance_id_with_reused_trace(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_duplicate_acceptance_trace")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-restart","acceptance_id":"restart_identity_session","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-restart","acceptance_id":"restart_identity_session","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=False)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "restart_identity_session must not reuse the same trace_id across repeated acceptance log entries." in failures


def test_freyja6_log_audit_rejects_reused_litellm_acceptance_traces(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_litellm_trace_reuse")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-general","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"model_call","trace_id":"trace-fast","model":"vulcan-fast","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-general","acceptance_id":"litellm_to_vulcan","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-general","acceptance_id":"model_switch","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "model_switch trace_id must be distinct from litellm_to_vulcan trace_id." in failures


def test_freyja6_log_audit_requires_litellm_acceptance_traces_in_model_log(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_litellm_acceptance_model_trace")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-general","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-general","acceptance_id":"litellm_to_vulcan","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-fast","acceptance_id":"model_switch","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "model_switch trace_id must match an ok model_call log trace." in failures


def test_freyja6_log_audit_requires_model_switch_to_have_distinct_model_aliases(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_model_switch_distinct_aliases")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-general-a","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"model_call","trace_id":"trace-general-b","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-general-a","acceptance_id":"litellm_to_vulcan","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-general-b","acceptance_id":"model_switch","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "model_switch must be supported by at least two distinct ok model_call aliases." in failures


def test_freyja6_log_audit_requires_model_acceptance_supporting_source(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_model_acceptance_supporting_source")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-vulcan","model":"vulcan-general","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-vulcan","acceptance_id":"litellm_to_vulcan","status":"ok","source":"freyja6-litellm-smoke"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "litellm_to_vulcan supporting model_call source must be freyja6-litellm-smoke." in failures


def test_freyja6_log_audit_requires_model_call_status_codes(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_model_status_code")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-missing","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"model_call","trace_id":"trace-bad","model":"vulcan-fast","status":"ok","status_code":503,"source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-missing","acceptance_id":"litellm_to_vulcan","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    model_log = next(check for check in report["checks"] if check["id"] == "model_log")
    failures = [failure for item in model_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "model_call status_code must be an integer." in failures
    assert "ok model_call status_code must be 2xx." in failures


def test_freyja6_log_audit_requires_tool_acceptance_traces_in_tool_log(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_tool_acceptance_trace")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-terminal","tool":"terminal.safe_command","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-terminal","acceptance_id":"safe_terminal","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-calendar","acceptance_id":"calendar_read","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "calendar_read trace_id must match an ok calendar.list_events tool_call log trace." in failures


def test_freyja6_log_audit_requires_tool_acceptance_trace_to_match_expected_tool(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_tool_acceptance_expected_tool")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-calendar","tool":"status.check","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-calendar","acceptance_id":"calendar_read","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "calendar_read trace_id must match an ok calendar.list_events tool_call log trace." in failures


def test_freyja6_log_audit_requires_tool_acceptance_supporting_source(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_tool_acceptance_supporting_source")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-calendar-create","tool":"calendar.create_event","status":"ok","source":"freyja6-tool-smoke"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:01:00+00:00","event":"acceptance","trace_id":"trace-calendar-create","acceptance_id":"calendar_create_event","status":"ok","source":"freyja6-calendar-write-smoke"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "calendar_create_event supporting calendar.create_event tool_call source must be freyja6-calendar-write-smoke." in failures


def test_freyja6_log_audit_rejects_reused_tool_acceptance_traces(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_tool_trace_reuse")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-shared-tool","tool":"terminal.safe_command","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-shared-tool","tool":"calendar.list_events","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-shared-tool","acceptance_id":"safe_terminal","status":"ok","source":"freyja6-log-audit-test"}',
                '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-shared-tool","acceptance_id":"calendar_read","status":"ok","source":"freyja6-log-audit-test"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "calendar_read trace_id must be distinct from safe_terminal trace_id." in failures
    assert "safe_terminal trace_id must be distinct from calendar_read trace_id." in failures


def test_freyja6_log_audit_rejects_acceptance_before_supporting_trace(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_acceptance_trace_order")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:05:00+00:00","event":"tool_call","trace_id":"trace-calendar","tool":"calendar.list_events","status":"ok","source":"freyja6-tool-smoke"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:05:00+00:00","event":"model_call","trace_id":"trace-general","model":"vulcan-general","status":"ok","source":"freyja6-litellm-smoke"}',
                '{"timestamp":"2026-09-19T00:06:00+00:00","event":"model_call","trace_id":"trace-fast","model":"vulcan-fast","status":"ok","source":"freyja6-litellm-smoke"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-09-19T00:04:00+00:00","event":"acceptance","trace_id":"trace-general","acceptance_id":"litellm_to_vulcan","status":"ok","source":"freyja6-litellm-smoke"}',
                '{"timestamp":"2026-09-19T00:04:00+00:00","event":"acceptance","trace_id":"trace-fast","acceptance_id":"model_switch","status":"ok","source":"freyja6-litellm-smoke"}',
                '{"timestamp":"2026-09-19T00:04:00+00:00","event":"acceptance","trace_id":"trace-calendar","acceptance_id":"calendar_read","status":"ok","source":"freyja6-tool-smoke"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert "litellm_to_vulcan timestamp must not be before supporting model_call log trace." in failures
    assert "model_switch timestamp must not be before supporting model_call log trace." in failures
    assert "calendar_read timestamp must not be before supporting calendar.list_events tool_call log trace." in failures


def test_freyja6_log_audit_rejects_bad_timestamp_and_trace_id(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_trace_semantics")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"after lunch","event":"tool_call","trace_id":"raw-tool","tool":"status.check","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"freyja6-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    assert report["ok"] is False
    assert tool_log["semantic_failures"][0]["failures"] == [
        "timestamp must be an ISO timestamp.",
        "trace_id must use a Freyja validation trace prefix.",
    ]


def test_freyja6_log_audit_rejects_naive_and_future_timestamps(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_timestamp_provenance")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2999-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    model_log = next(check for check in report["checks"] if check["id"] == "model_log")
    assert report["ok"] is False
    assert tool_log["semantic_failures"][0]["failures"] == ["timestamp must include a timezone offset."]
    assert model_log["semantic_failures"][0]["failures"] == ["timestamp must not be in the future."]


def test_freyja6_log_audit_rejects_placeholder_trace_ids(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_placeholder_trace")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-...","tool":"status.check","status":"ok","status_code":200,"source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    assert report["ok"] is False
    assert tool_log["semantic_failures"][0]["failures"] == ["trace_id must not use placeholder ellipses."]


def test_freyja6_log_audit_requires_freyja6_source_attribution(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_source")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","status_code":200,"source":"manual"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-log-audit-test"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    assert report["ok"] is False
    assert tool_log["semantic_failures"][0]["failures"] == [
        "source must identify an approved Freyja 6 validation helper: freyja6-calendar-write-smoke, freyja6-log-audit-test, freyja6-schedule-smoke, freyja6-tool-smoke."
    ]


def test_freyja6_log_audit_rejects_unknown_freyja6_source(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_unknown_freyja6_source")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-tool","tool":"status.check","status":"ok","source":"freyja6-made-up-helper"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","source":"freyja6-litellm-smoke"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-acceptance","acceptance_id":"discord_reply","status":"ok","source":"freyja6-discord-smoke"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path, require_entries=True)

    tool_log = next(check for check in report["checks"] if check["id"] == "tool_log")
    failures = [failure for item in tool_log["semantic_failures"] for failure in item["failures"]]
    assert report["ok"] is False
    assert any(failure.startswith("source must identify an approved Freyja 6 validation helper:") for failure in failures)


def test_freyja6_log_audit_requires_acceptance_source_to_match_item(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_acceptance_source_match")
    (tmp_path / "freyja-test-tools.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"tool_call","trace_id":"trace-calendar-create","tool":"calendar.create_event","status":"ok","source":"freyja6-calendar-write-smoke"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-model-calls.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"model_call","trace_id":"trace-model","model":"vulcan-general","status":"ok","status_code":200,"source":"freyja6-litellm-smoke"}\n',
        encoding="utf-8",
    )
    (tmp_path / "freyja-test-acceptance.jsonl").write_text(
        '{"timestamp":"2026-09-19T00:00:00+00:00","event":"acceptance","trace_id":"trace-calendar-create","acceptance_id":"calendar_create_event","status":"ok","source":"freyja6-discord-smoke"}\n',
        encoding="utf-8",
    )

    report = module.build_report(log_root=tmp_path)

    acceptance_log = next(check for check in report["checks"] if check["id"] == "acceptance_log")
    failures = [failure for item in acceptance_log["semantic_failures"] for failure in item["failures"]]
    assert "source must be freyja6-calendar-write-smoke for calendar_create_event." in failures


def test_freyja6_log_audit_requires_entries_when_requested(tmp_path) -> None:
    module = _load_log_audit_module("freyja6_log_audit_empty")
    for log_name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl"):
        (tmp_path / log_name).write_text("", encoding="utf-8")

    report = module.build_report(log_root=tmp_path, require_entries=True)

    assert report["ok"] is False
    assert {check["status"] for check in report["checks"]} == {"fail"}


def test_freyja6_preservation_audit_passes_current_side_by_side_guardrails() -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit")

    report = module.build_report()

    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert next(check for check in report["checks"] if check["id"] == "guardrails")["status"] == "pass"
    compose = next(check for check in report["checks"] if check["id"] == "compose_side_by_side")
    assert compose["services"] == ["hermes-freyja-test", "litellm", "litellm-db"]


def test_freyja6_preservation_audit_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit_symlink_output")
    real_output = tmp_path / "real-preservation.json"
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "preservation.json"
    output.symlink_to(real_output)

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must not be a symlink: preservation.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_preservation_audit_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit_directory_output")
    output = tmp_path / "preservation-dir"
    output.mkdir()

    exit_code = module.main(["--output", str(output)])

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ok"] is False
    assert rendered["status"] == "fail"
    assert rendered["error"] == "output path must be a regular file: preservation-dir"


def test_freyja6_preservation_audit_rejects_symlinked_source_file(tmp_path, monkeypatch) -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit_symlink_source")
    real_config = tmp_path / "real-freyja-test.yaml"
    real_config.write_text((ROOT / "config/freyja6/freyja-test.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    agent_config = tmp_path / "freyja-test.yaml"
    agent_config.symlink_to(real_config)

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("source YAML should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config_path=agent_config,
        compose_path=ROOT / "deploy/compose/freyja6/compose.yaml",
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["symlinks"] == [str(agent_config)]


def test_freyja6_preservation_audit_rejects_directory_source_file(tmp_path, monkeypatch) -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit_directory_source")
    compose = tmp_path / "compose.yaml"
    compose.mkdir()

    monkeypatch.setattr(module, "_load_yaml", lambda path: (_ for _ in ()).throw(AssertionError("source YAML should not be loaded for unsafe source files")))

    report = module.build_report(
        agent_config_path=ROOT / "config/freyja6/freyja-test.yaml",
        compose_path=compose,
    )

    assert report["ok"] is False
    assert report["checks"] == report["failures"]
    source_files = next(check for check in report["checks"] if check["id"] == "source_files")
    assert source_files["status"] == "fail"
    assert source_files["not_regular"] == [str(compose)]


def test_freyja6_preservation_audit_detects_guardrail_drift(monkeypatch) -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit_drift")
    original = module._load_yaml

    def fake_load_yaml(path):
        payload = original(path)
        if str(path).endswith("freyja-test.yaml"):
            payload["guardrails"]["preserve_existing_systems"] = ["Freyja 4"]
        return payload

    monkeypatch.setattr(module, "_load_yaml", fake_load_yaml)

    report = module.build_report()

    assert report["ok"] is False
    guardrails = next(check for check in report["checks"] if check["id"] == "guardrails")
    assert "Freyja 5" in guardrails["missing_preserved_systems"]


def test_freyja6_preservation_audit_rejects_legacy_runtime_coupling(monkeypatch) -> None:
    module = _load_preservation_audit_module("freyja6_preservation_audit_legacy_runtime")
    original = module._load_yaml

    def fake_load_yaml(path):
        payload = original(path)
        if str(path).endswith("compose.yaml"):
            payload["services"]["hermes-freyja-test"]["environment"]["FREYJA_DISCORD_BOT_TOKEN"] = "${FREYJA_DISCORD_BOT_TOKEN}"
            payload["services"]["hermes-freyja-test"]["volumes"].append("/Users/freyja/Library/Application Support/Msty Go:/legacy/msty-go:ro")
        return payload

    monkeypatch.setattr(module, "_load_yaml", fake_load_yaml)

    report = module.build_report()

    coupling = next(check for check in report["checks"] if check["id"] == "legacy_runtime_coupling")
    assert report["ok"] is False
    assert coupling["status"] == "fail"
    assert {"service": "hermes-freyja-test", "field": "environment", "marker": "FREYJA_DISCORD"} in coupling["findings"]
    assert any(item["field"] == "volumes" and item["marker"] == "MSTY" for item in coupling["findings"])


def test_freyja6_migration_readiness_blocks_without_complete_acceptance_and_repeated_runs(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_blocked")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    bundle = tmp_path / "bundle.json"
    acceptance.write_text('{"complete": false, "remaining_acceptance": ["discord_reply"], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-validation-bundle","timestamp":"2026-09-19T00:00:00+00:00","live":true,"complete":true,"status":"complete","failed_required":[],"skipped_required":[]}\n',
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=3,
    )

    assert report["ready"] is False
    assert report["status"] == "not_ready"
    assert report["next_migration_candidate"] == ""
    assert [check["id"] for check in report["blockers"]] == ["acceptance", "repeated_live_bundles"]


def test_freyja6_migration_readiness_allows_only_after_repeated_complete_live_runs(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_ready")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    assert report["ready"] is True
    assert report["next_migration_candidate"] == "Freyja"
    assert report["migration_order"] == ["freyja-test", "Freyja", "Cloyd", "Benedict", "Agent 44", "Agent Smith"]
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["unique_successful_timestamps"] == 3
    assert repeated["distinct_successful_dates"] == ["2026-09-17", "2026-09-18", "2026-09-19"]


def test_freyja6_migration_readiness_rejects_extra_bad_bundle_report_even_with_enough_successes(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_extra_bad_bundle")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)
    extra = tmp_path / "bundle-extra.json"
    extra.write_text('{"report_type":"freyja6-migration-readiness"}\n', encoding="utf-8")
    bundles.append(extra)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 3
    assert {"report": "bundle-extra.json", "reason": "not_live_validation_bundle"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_symlinked_live_bundle_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_symlink_bundle_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index, timestamp in enumerate(
        [
            "2026-09-17T00:00:00+00:00",
            "2026-09-18T00:00:00+00:00",
            "2026-09-19T00:00:00+00:00",
        ]
    ):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(timestamp))
        bundles.append(bundle)
    real_bundle = bundles[0]
    symlink_bundle = tmp_path / "bundle-symlink.json"
    symlink_bundle.symlink_to(real_bundle)
    bundles[0] = symlink_bundle

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 2
    assert {"report": "bundle-symlink.json", "reason": "input_report_symlink"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_directory_live_bundle_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_directory_bundle_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index, timestamp in enumerate(
        [
            "2026-09-17T00:00:00+00:00",
            "2026-09-18T00:00:00+00:00",
            "2026-09-19T00:00:00+00:00",
        ]
    ):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(timestamp))
        bundles.append(bundle)
    directory_bundle = tmp_path / "bundle-dir.json"
    directory_bundle.mkdir()
    bundles[0] = directory_bundle

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 2
    assert {"report": "bundle-dir.json", "reason": "input_report_not_regular"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_cli_refuses_to_overwrite_input_reports(tmp_path, capsys) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_output_collision")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    bundle = tmp_path / "bundle.json"
    original_acceptance = json.dumps(_complete_acceptance_status_payload()) + "\n"
    acceptance.write_text(original_acceptance, encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-19T00:00:00+00:00"))

    exit_code = module.main(
        [
            "--acceptance-status",
            str(acceptance),
            "--preservation-report",
            str(preservation),
            "--bundle-report",
            str(bundle),
            "--output",
            str(acceptance),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["ready"] is False
    assert output["error"] == "output path must not overwrite input evidence reports"
    assert output["conflicting_inputs"] == ["acceptance.json"]
    assert acceptance.read_text(encoding="utf-8") == original_acceptance


def test_freyja6_migration_readiness_cli_refuses_to_overwrite_globbed_bundle_report(tmp_path, capsys) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_glob_output_collision")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    bundle = tmp_path / "freyja6-live-validation-bundle.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    original_bundle = json.dumps(_complete_live_bundle_payload("2026-09-19T00:00:00+00:00")) + "\n"
    bundle.write_text(original_bundle, encoding="utf-8")

    exit_code = module.main(
        [
            "--acceptance-status",
            str(acceptance),
            "--preservation-report",
            str(preservation),
            "--bundle-glob",
            str(tmp_path / "freyja6-live-validation-bundle*.json"),
            "--output",
            str(bundle),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["ready"] is False
    assert output["error"] == "output path must not overwrite input evidence reports"
    assert output["conflicting_inputs"] == ["freyja6-live-validation-bundle.json"]
    assert bundle.read_text(encoding="utf-8") == original_bundle


def test_freyja6_migration_readiness_cli_rejects_output_matching_bundle_glob(tmp_path, capsys) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_output_matches_bundle_glob")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    output = tmp_path / "freyja6-live-validation-bundle-readiness.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")

    exit_code = module.main(
        [
            "--acceptance-status",
            str(acceptance),
            "--preservation-report",
            str(preservation),
            "--bundle-glob",
            str(tmp_path / "freyja6-live-validation-bundle*.json"),
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["error"] == "output path must not overwrite input evidence reports"
    assert rendered["conflicting_inputs"] == ["freyja6-live-validation-bundle-readiness.json"]
    assert not output.exists()


def test_freyja6_migration_readiness_cli_refuses_symlinked_output(tmp_path, capsys) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_symlink_output")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    bundle = tmp_path / "bundle.json"
    real_output = tmp_path / "real-readiness.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-19T00:00:00+00:00"))
    real_output.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "readiness.json"
    output.symlink_to(real_output)

    exit_code = module.main(
        [
            "--acceptance-status",
            str(acceptance),
            "--preservation-report",
            str(preservation),
            "--bundle-report",
            str(bundle),
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["error"] == "output path must not be a symlink: readiness.json"
    assert real_output.read_text(encoding="utf-8") == "sentinel\n"


def test_freyja6_migration_readiness_cli_refuses_directory_output(tmp_path, capsys) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_directory_output")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    bundle = tmp_path / "bundle.json"
    output = tmp_path / "readiness-dir"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-19T00:00:00+00:00"))
    output.mkdir()

    exit_code = module.main(
        [
            "--acceptance-status",
            str(acceptance),
            "--preservation-report",
            str(preservation),
            "--bundle-report",
            str(bundle),
            "--output",
            str(output),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["ready"] is False
    assert rendered["error"] == "output path must be a regular file: readiness-dir"


def test_freyja6_migration_readiness_enforces_three_run_floor(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_three_run_floor")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-20T00:00:00+00:00"))

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert report["min_successful_runs"] == 3
    assert report["requested_min_successful_runs"] == 1
    assert repeated["required"] == 3
    assert repeated["complete_count"] == 1


def test_freyja6_migration_readiness_rejects_spoofed_acceptance_status(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_spoofed_acceptance")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text('{"complete": true, "remaining_acceptance": [], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert acceptance_check["contract_failures"] == [
        "schema_version must be 1.0.",
        "report_type must be freyja6-acceptance-status.",
        "status must be complete.",
        "timestamp must be a non-empty ISO timestamp.",
        "evidence must be a non-empty string.",
        "evidence_contract must be an object.",
        "acceptance must be a list.",
    ]


def test_freyja6_migration_readiness_rejects_symlinked_acceptance_status(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_symlink_acceptance")
    real_acceptance = tmp_path / "real-acceptance.json"
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    real_acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    acceptance.symlink_to(real_acceptance)
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "input_report_symlink" in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_directory_acceptance_status(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_directory_acceptance")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.mkdir()
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "input_report_not_regular" in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_untimestamped_acceptance_status(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_acceptance_timestamp")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    del payload["timestamp"]
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "timestamp must be a non-empty ISO timestamp." in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_acceptance_status_missing_required_items(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_acceptance_items")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    payload["acceptance"] = [{"id": "discord_reply", "status": "complete"}]
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "acceptance must include restart_identity_session." in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_spoofed_acceptance_item_details(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_spoofed_acceptance_details")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    discord = next(item for item in payload["acceptance"] if item["id"] == "discord_reply")
    del discord["missing_evidence"]
    discord["semantic_failures"] = ["verification_method must be discord-api or manual-confirmed."]
    discord["present_evidence"] = ["reply_trace_id"]
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "acceptance discord_reply missing_evidence must be a list." in acceptance_check["contract_failures"]
    assert "acceptance discord_reply semantic_failures must be empty." in acceptance_check["contract_failures"]
    assert "acceptance discord_reply present_evidence must match required_evidence." in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_shrunken_acceptance_contract(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_shrunken_acceptance_contract")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    discord = next(item for item in payload["acceptance"] if item["id"] == "discord_reply")
    discord["required_evidence"] = ["reply_trace_id"]
    discord["present_evidence"] = ["reply_trace_id"]
    discord["required_metadata"] = ["captured_at"]
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "acceptance discord_reply required_evidence must match the Freyja 6 acceptance contract." in acceptance_check["contract_failures"]
    assert "acceptance discord_reply present_evidence must match required_evidence." in acceptance_check["contract_failures"]
    assert "acceptance discord_reply required_metadata must match the Freyja 6 acceptance contract." in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_spoofed_acceptance_metadata(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_spoofed_acceptance_metadata")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    calendar = next(item for item in payload["acceptance"] if item["id"] == "calendar_create_event")
    calendar["metadata"] = {
        "captured_at": "2026-09-19T00:00:00+00:00",
        "source": "freyja6-tool-smoke",
    }
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "acceptance calendar_create_event metadata source must be freyja6-calendar-write-smoke." in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_acceptance_status_missing_evidence_reference(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_acceptance_evidence")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    del payload["evidence"]
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert "evidence must be a non-empty string." in acceptance_check["contract_failures"]
    assert repeated["complete_count"] == 3


def test_freyja6_migration_readiness_rejects_acceptance_status_unexpected_evidence_artifact(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_unexpected_acceptance_evidence")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    payload["evidence"] = str(tmp_path / "scratch-evidence.json")
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00", evidence=payload["evidence"]))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert "evidence must reference freyja6-live-evidence.json." in acceptance_check["contract_failures"]
    assert repeated["complete_count"] == 0
    assert {"report": "bundle-0.json", "reason": "acceptance_status_side_report_contract_failure"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_malformed_acceptance_summary_fields(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_malformed_acceptance_summary")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    payload = _complete_acceptance_status_payload()
    payload["complete"] = "true"
    payload["remaining_acceptance"] = "none"
    payload["secrets_detected"] = "false"
    payload["evidence_contract"] = []
    acceptance.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    acceptance_check = next(check for check in report["checks"] if check["id"] == "acceptance")
    assert report["ready"] is False
    assert "complete must be true." in acceptance_check["contract_failures"]
    assert "remaining_acceptance must be a list." in acceptance_check["contract_failures"]
    assert "secrets_detected must be false." in acceptance_check["contract_failures"]
    assert "evidence_contract must be an object." in acceptance_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_spoofed_preservation_audit(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_spoofed_preservation")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    preservation_check = next(check for check in report["checks"] if check["id"] == "preservation")
    assert report["ready"] is False
    assert preservation_check["contract_failures"] == [
        "schema_version must be 1.0.",
        "report_type must be freyja6-preservation-audit.",
        "status must be pass.",
        "secrets_included must be false.",
        "failures must be a list.",
        "checks must be a list.",
    ]


def test_freyja6_migration_readiness_rejects_symlinked_preservation_audit(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_symlink_preservation")
    acceptance = tmp_path / "acceptance.json"
    real_preservation = tmp_path / "real-preservation.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    real_preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    preservation.symlink_to(real_preservation)
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    preservation_check = next(check for check in report["checks"] if check["id"] == "preservation")
    assert report["ready"] is False
    assert "input_report_symlink" in preservation_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_directory_preservation_audit(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_directory_preservation")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.mkdir()
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    preservation_check = next(check for check in report["checks"] if check["id"] == "preservation")
    assert report["ready"] is False
    assert "input_report_not_regular" in preservation_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_malformed_preservation_checks(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_malformed_preservation_checks")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    payload = _passing_preservation_payload()
    payload["checks"] = [
        {"id": "guardrails", "status": "pass"},
        {"id": "guardrails", "status": "pass"},
        {"id": "phase_one_agent_scope", "status": "fail"},
        {"id": "compose_side_by_side", "status": 44},
        {"id": "future_agent_ready", "status": "pass"},
        {"status": "pass"},
        "legacy_evidence_present",
    ]
    preservation.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    preservation_check = next(check for check in report["checks"] if check["id"] == "preservation")
    assert report["ready"] is False
    assert "checks entries must be objects with string ids." in preservation_check["contract_failures"]
    assert "checks contain duplicate id guardrails." in preservation_check["contract_failures"]
    assert "checks contain unexpected id future_agent_ready." in preservation_check["contract_failures"]
    assert "check phase_one_agent_scope status must be pass." in preservation_check["contract_failures"]
    assert "check compose_side_by_side status must be a string." in preservation_check["contract_failures"]
    assert "check compose_side_by_side status must be pass." in preservation_check["contract_failures"]
    assert "checks must include source_files." in preservation_check["contract_failures"]
    assert "checks must include legacy_runtime_coupling." in preservation_check["contract_failures"]
    assert "checks must include legacy_evidence_present." in preservation_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_contradictory_preservation_summary(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_contradictory_preservation")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    payload = _passing_preservation_payload()
    payload["ok"] = "true"
    payload["failures"] = [{"id": "guardrails", "status": "fail"}]
    preservation.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    preservation_check = next(check for check in report["checks"] if check["id"] == "preservation")
    assert report["ready"] is False
    assert "ok must be true." in preservation_check["contract_failures"]
    assert "failures must be empty." in preservation_check["contract_failures"]


def test_freyja6_migration_readiness_rejects_same_day_burst_runs(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_same_day")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text('{"complete": true, "remaining_acceptance": [], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(f"2026-09-19T00:0{index}:00+00:00"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 3
    assert repeated["unique_successful_timestamps"] == 3
    assert repeated["distinct_successful_dates"] == ["2026-09-19"]


def test_freyja6_migration_readiness_rejects_duplicated_live_bundle_timestamps(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_duplicate_timestamps")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text('{"complete": true, "remaining_acceptance": [], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-19T00:00:00+00:00", run_id=f"freyja6-live-{uuid.uuid4()}"))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    assert report["ready"] is False
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 1
    assert repeated["unique_successful_timestamps"] == 1
    assert {"report": "bundle-1.json", "reason": "duplicate_timestamp"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_missing_live_bundle_run_id(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_run_id")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    del payload["run_id"]
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "missing_run_id"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_invalid_live_bundle_run_id(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_invalid_run_id")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-19T00:00:00+00:00", run_id="manual-copy"))

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_run_id"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_duplicate_live_bundle_run_ids(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_duplicate_run_id")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    duplicate_run_id = f"freyja6-live-{uuid.uuid4()}"
    timestamps = [
        "2026-09-17T00:00:00+00:00",
        "2026-09-18T00:00:00+00:00",
        "2026-09-19T00:00:00+00:00",
    ]
    bundles = []
    for index, timestamp in enumerate(timestamps):
        bundle = tmp_path / f"bundle-{index}.json"
        run_id = duplicate_run_id if index < 2 else None
        _write_live_bundle(bundle, _complete_live_bundle_payload(timestamp, run_id=run_id))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 2
    assert repeated["unique_successful_run_ids"] == 2
    assert {"report": "bundle-1.json", "reason": "duplicate_run_id"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_symlinked_bundle_env_file(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_symlink_env_file")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    real_env = tmp_path / "real.env"
    real_env.write_text("COMPOSE_PROJECT_NAME=freyja6\n", encoding="utf-8")
    env_link = tmp_path / ".env"
    env_link.symlink_to(real_env)
    bundles = []
    for index, timestamp in enumerate(
        [
            "2026-09-17T00:00:00+00:00",
            "2026-09-18T00:00:00+00:00",
            "2026-09-19T00:00:00+00:00",
        ]
    ):
        payload = _complete_live_bundle_payload(timestamp)
        payload["env_file"] = str(env_link) if index == 0 else "deploy/compose/freyja6/.env"
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, payload)
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 2
    assert {"report": "bundle-0.json", "reason": "env_file_symlink"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_directory_bundle_env_file(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_directory_env_file")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    env_dir = tmp_path / ".env"
    env_dir.mkdir()
    bundles = []
    for index, timestamp in enumerate(
        [
            "2026-09-17T00:00:00+00:00",
            "2026-09-18T00:00:00+00:00",
            "2026-09-19T00:00:00+00:00",
        ]
    ):
        payload = _complete_live_bundle_payload(timestamp)
        payload["env_file"] = str(env_dir) if index == 0 else "deploy/compose/freyja6/.env"
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, payload)
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 2
    assert {"report": "bundle-0.json", "reason": "env_file_not_regular"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_duplicate_live_bundle_instants_with_different_offsets(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_duplicate_instant_offsets")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    timestamps = [
        "2026-09-19T00:00:00+00:00",
        "2026-09-18T20:00:00-04:00",
        "2026-09-20T00:00:00+00:00",
    ]
    bundles = []
    for index, timestamp in enumerate(timestamps):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(timestamp))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 2
    assert repeated["unique_successful_timestamps"] == 2
    assert {"report": "bundle-1.json", "reason": "duplicate_timestamp"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_invalid_live_bundle_timestamp(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_invalid_timestamp")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text('{"complete": true, "remaining_acceptance": [], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundles = []
    for index, timestamp in enumerate(("2026-09-19T00:00:00+00:00", "after lunch", "2026-09-19T00:02:00+00:00")):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, _complete_live_bundle_payload(timestamp))
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    assert report["ready"] is False
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 2
    assert {"report": "bundle-1.json", "reason": "invalid_timestamp"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_date_only_live_bundle_timestamp(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_date_only_timestamp")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, _complete_live_bundle_payload("2026-09-19"))

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_timestamp"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_future_live_bundle_timestamp(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_future_timestamp")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, _complete_live_bundle_payload("2099-09-19T00:00:00+00:00"))

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "future_timestamp"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_bundle_status_not_complete(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_bundle_status")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text('{"complete": true, "remaining_acceptance": [], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-validation-bundle","timestamp":"2026-09-19T00:00:00+00:00","live":true,"complete":true,"status":"incomplete","failed_required":[],"skipped_required":[]}\n',
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    assert report["ready"] is False
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "status_not_complete"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_malformed_required_summary_fields(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_malformed_required_summary")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["failed_required"] = ""
    payload["skipped_required"] = ""
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_required_summary"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_live_bundle_missing_provenance(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_bundle_provenance")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    del payload["env_file"]
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "missing_env_file"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_example_env_live_bundle(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_example_env_bundle")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["env_file"] = "deploy/compose/freyja6/.env.example"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "example_env_file"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_invalid_env_file_live_bundle(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_invalid_env_bundle")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["env_file"] = "deploy/compose/freyja6/manual.env"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_env_file"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_unexpected_live_bundle_log_root(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_invalid_log_root")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["log_root"] = "scratch"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_log_root"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_invalid_bundle_schema_version(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_bundle_schema")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"0.9","report_type":"freyja6-live-validation-bundle","timestamp":"2026-09-19T00:00:00+00:00","live":true,"complete":true,"status":"complete","failed_required":[],"skipped_required":[]}\n',
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    assert report["ready"] is False
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_schema_version"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_complete_bundle_without_step_results(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_bundle_results")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-validation-bundle","timestamp":"2026-09-19T00:00:00+00:00","live":true,"complete":true,"status":"complete","failed_required":[],"skipped_required":[]}\n',
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "missing_results"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_non_list_live_bundle_results(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_non_list_results")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"] = {"env_audit": "pass"}
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_results"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_non_object_live_bundle_results(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_non_object_results")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"].append("not-a-step")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "invalid_results"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_missing_required_reportless_live_step(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_required_reportless_step")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"] = [item for item in payload["results"] if item["id"] != "discord_reply"]
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "missing_required_live_steps"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_required_step_marked_non_required(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_required_step_not_required")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    env_audit = next(item for item in payload["results"] if item["id"] == "env_audit")
    env_audit["required"] = False
    env_audit["status"] = "skip"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_not_marked_required"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_duplicate_required_live_steps(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_duplicate_required_steps")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"].append(
        {
            "id": "env_audit",
            "required": True,
            "status": "pass",
            "exit_code": 0,
            "command": [".venv/bin/python", "scripts/freyja6-env-audit.py"],
        }
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "duplicate_required_live_steps"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_unexpected_live_bundle_steps(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_unexpected_live_steps")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"].append({"id": "cloyd_discord_reply", "required": False, "status": "pass"})
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "unexpected_live_step"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_malformed_live_bundle_steps(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_malformed_live_steps")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"].append({"required": False, "status": "pass"})
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "malformed_live_step"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_non_string_live_bundle_step_ids(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_non_string_live_step_id")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    payload["results"].append({"id": 44, "required": False, "status": "pass"})
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "malformed_live_step"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_non_boolean_live_bundle_required_flags(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_non_boolean_required")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    env_audit = next(item for item in payload["results"] if item["id"] == "env_audit")
    env_audit["required"] = "true"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "malformed_live_step"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_nested_required_bundle_failure(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_nested_failure")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text('{"complete": true, "remaining_acceptance": [], "secrets_detected": false}\n', encoding="utf-8")
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-live-validation-bundle",
                "timestamp": "2026-09-19T00:00:00+00:00",
                "live": True,
                "complete": True,
                "status": "complete",
                "failed_required": [],
                "skipped_required": [],
                "results": [
                    {"id": "env_audit", "required": True, "status": "fail"},
                    {"id": "acceptance_status", "required": True, "status": "pass"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    assert report["ready"] is False
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "nested_required_not_complete"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_unknown_required_step_status(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_unknown_required_status")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    env_audit = next(item for item in payload["results"] if item["id"] == "env_audit")
    env_audit["status"] = "unknown"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "nested_required_status_unknown"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_passed_step_with_failure_markers(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_pass_with_failure_markers")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    env_audit = next(item for item in payload["results"] if item["id"] == "env_audit")
    env_audit["payload_failure"] = True
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_pass_with_failure_markers"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_passed_step_without_zero_exit(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_pass_without_zero_exit")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    tool_smoke = next(item for item in payload["results"] if item["id"] == "tool_smoke")
    tool_smoke["exit_code"] = 2
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_pass_without_zero_exit"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_passed_step_without_command(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_command")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    discord = next(item for item in payload["results"] if item["id"] == "discord_reply")
    discord.pop("command")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_missing_command"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_passed_step_wrong_command_launcher(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_wrong_command_launcher")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    discord = next(item for item in payload["results"] if item["id"] == "discord_reply")
    discord["command"] = ["bash", "scripts/freyja6-discord-smoke.py"]
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_command_launcher_mismatch"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_passed_step_wrong_command(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_wrong_command")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    discord = next(item for item in payload["results"] if item["id"] == "discord_reply")
    discord["command"] = [".venv/bin/python", "scripts/freyja6-tool-smoke.py"]
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_command_mismatch"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_required_step_without_report_reference(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_step_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    del log_audit["report"]
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_missing_report"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_required_step_wrong_report_reference(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_wrong_step_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    log_audit["report"] = "bundle-acceptance-status.json"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_missing_report"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_required_step_report_from_other_bundle(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_wrong_bundle_step_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    original = tmp_path / "bundle-log-audit.json"
    other = tmp_path / "other-bundle-log-audit.json"
    other.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    original.unlink()
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    log_audit["report"] = other.name
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_report_bundle_mismatch"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_accepts_reports_under_certification_reports(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_certification_report_refs")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    bundles = []
    for index in range(3):
        payload = _complete_live_bundle_payload(f"2026-09-1{index + 7}T00:00:00+00:00")
        for item in payload["results"]:
            if "report" in item:
                item["report"] = f"certification/reports/{item['report']}"
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(bundle, payload)
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is True
    assert repeated["status"] == "pass"
    assert repeated["complete_count"] == 3


def test_freyja6_migration_readiness_rejects_step_report_path_traversal(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_step_report_traversal")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    log_audit["report"] = "../bundle-log-audit.json"
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "required_live_step_missing_report"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_missing_step_report_artifact(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_missing_step_report_artifact")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "missing_step_report_artifact"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_step_report_type_mismatch(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_step_report_type_mismatch")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    (tmp_path / "bundle-log-audit.json").write_text(
        '{"schema_version":"1.0","report_type":"freyja6-acceptance-status","status":"pass"}\n',
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_type_mismatch"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_symlinked_step_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_symlink_step_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    real_report = tmp_path / "real-log-audit.json"
    real_report.write_text((tmp_path / "bundle-log-audit.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "bundle-log-audit.json").unlink()
    (tmp_path / "bundle-log-audit.json").symlink_to(real_report)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_symlink"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_directory_step_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_directory_step_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    (tmp_path / "bundle-log-audit.json").unlink()
    (tmp_path / "bundle-log-audit.json").mkdir()

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_not_regular"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_step_report_schema_mismatch(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_step_report_schema_mismatch")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    side_report = json.loads((tmp_path / "bundle-log-audit.json").read_text(encoding="utf-8"))
    side_report["schema_version"] = "0.9"
    (tmp_path / "bundle-log-audit.json").write_text(json.dumps(side_report) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_invalid_schema_version"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_failed_step_side_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_failed_step_side_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    (tmp_path / "bundle-log-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-log-audit",
                "status": "fail",
                "ok": False,
                "failures": [{"id": "acceptance_log", "status": "fail"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_indicates_failure"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_step_side_report_evidence_mismatch(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_step_side_report_evidence_mismatch")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    expected_evidence = tmp_path / "freyja6-live-evidence.json"
    stale_evidence = tmp_path / "stale-evidence.json"
    acceptance_payload = _complete_acceptance_status_payload()
    acceptance_payload["evidence"] = str(expected_evidence)
    acceptance.write_text(json.dumps(acceptance_payload) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00", evidence=str(expected_evidence))
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    (tmp_path / "bundle-acceptance-status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-acceptance-status",
                "status": "complete",
                "complete": True,
                "ok": True,
                "evidence": str(stale_evidence),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_evidence_mismatch"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_hollow_acceptance_status_side_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_hollow_acceptance_side_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    (tmp_path / "bundle-acceptance-status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "freyja6-acceptance-status",
                "timestamp": "2026-09-19T00:00:00+00:00",
                "status": "complete",
                "complete": True,
                "ok": True,
                "evidence": "certification/reports/freyja6-live-evidence.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "acceptance_status_side_report_contract_failure"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_stale_step_side_report(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_stale_step_side_report")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T00:00:00+00:00")
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    stale_report = json.loads((tmp_path / "bundle-log-audit.json").read_text(encoding="utf-8"))
    stale_report["timestamp"] = "2026-09-18T23:59:59+00:00"
    (tmp_path / "bundle-log-audit.json").write_text(json.dumps(stale_report) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_stale_timestamp"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_side_report_outside_step_window(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_side_report_step_window")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T12:00:00+00:00")
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    log_audit["started_at"] = "2026-09-19T12:00:00+00:00"
    log_audit["finished_at"] = "2026-09-19T12:00:05+00:00"
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)
    copied_report = json.loads((tmp_path / "bundle-log-audit.json").read_text(encoding="utf-8"))
    copied_report["timestamp"] = "2026-09-19T11:59:59+00:00"
    (tmp_path / "bundle-log-audit.json").write_text(json.dumps(copied_report) + "\n", encoding="utf-8")

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_report_outside_step_window"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_step_report_missing_step_timestamps(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_side_report_missing_step_times")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T12:00:00+00:00")
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    del log_audit["started_at"]
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_result_missing_timestamps"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_step_report_invalid_step_timestamp_order(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_side_report_bad_step_order")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    acceptance.write_text(json.dumps(_complete_acceptance_status_payload()) + "\n", encoding="utf-8")
    preservation.write_text(json.dumps(_passing_preservation_payload()) + "\n", encoding="utf-8")
    payload = _complete_live_bundle_payload("2026-09-19T12:00:00+00:00")
    log_audit = next(item for item in payload["results"] if item["id"] == "log_audit")
    log_audit["started_at"] = "2026-09-19T12:00:05+00:00"
    log_audit["finished_at"] = "2026-09-19T12:00:00+00:00"
    bundle = tmp_path / "bundle.json"
    _write_live_bundle(bundle, payload)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=[bundle],
        bundle_glob="unused",
        min_successful_runs=1,
    )

    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert report["ready"] is False
    assert repeated["complete_count"] == 0
    assert {"report": "bundle.json", "reason": "step_result_invalid_timestamp_order"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_rejects_bundle_evidence_mismatch(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_evidence_mismatch")
    acceptance = tmp_path / "acceptance.json"
    preservation = tmp_path / "preservation.json"
    expected_evidence = tmp_path / "expected" / "freyja6-live-evidence.json"
    other_evidence = tmp_path / "other" / "freyja6-live-evidence.json"
    acceptance.write_text(
        json.dumps({"complete": True, "remaining_acceptance": [], "secrets_detected": False, "evidence": str(expected_evidence)}) + "\n",
        encoding="utf-8",
    )
    preservation.write_text('{"ok": true}\n', encoding="utf-8")
    bundles = []
    for index in range(3):
        bundle = tmp_path / f"bundle-{index}.json"
        _write_live_bundle(
            bundle,
            _complete_live_bundle_payload(
                f"2026-09-1{index + 7}T00:00:00+00:00",
                evidence=str(other_evidence if index == 1 else expected_evidence),
            ),
        )
        bundles.append(bundle)

    report = module.build_report(
        acceptance_status=acceptance,
        preservation_report=preservation,
        bundle_reports=bundles,
        bundle_glob="unused",
        min_successful_runs=3,
    )

    assert report["ready"] is False
    repeated = next(check for check in report["checks"] if check["id"] == "repeated_live_bundles")
    assert repeated["complete_count"] == 2
    assert {"report": "bundle-1.json", "reason": "evidence_reference_mismatch"} in repeated["rejected_reports"]


def test_freyja6_migration_readiness_accepts_absolute_bundle_glob(tmp_path) -> None:
    module = _load_migration_readiness_module("freyja6_migration_readiness_absolute_glob")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"1.0","report_type":"freyja6-live-validation-bundle","timestamp":"2026-09-19T00:00:00+00:00","live":true,"complete":true,"status":"complete","failed_required":[],"skipped_required":[]}\n',
        encoding="utf-8",
    )

    bundles = module._glob_bundle_reports(str(tmp_path / "*.json"))

    assert bundles == [bundle]
