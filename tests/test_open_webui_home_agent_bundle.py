from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build-open-webui-home-agent-bundle.py"


def _module():
    spec = importlib.util.spec_from_file_location("build_open_webui_home_agent_bundle", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_contains_required_deliverable_sections() -> None:
    bundle = _module().build_bundle(now=1)

    assert bundle["secrets_included"] is False
    assert bundle["private_content_included"] is False
    assert "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account." not in json.dumps(bundle)
    assert bundle["status"] == "maximally_completed_pending_external_auth"
    assert bundle["git_head"]
    assert bundle["completion_status_counts"] == {"auth_gated": 3, "complete": 9, "credential_gated": 1, "partial": 2}
    assert bundle["completion_metrics"] == {
        "total_requirements": 15,
        "complete_requirements": 9,
        "incomplete_requirements": 6,
        "auth_gated_requirements": 3,
        "credential_gated_requirements": 1,
        "partial_requirements": 2,
        "external_gated_requirements": 4,
        "verified_completion_percent": 60.0,
    }
    assert bundle["endpoint_map"]["open_webui_local"] == "http://127.0.0.1:3001"
    assert bundle["rollback"]["open_webui_volume_backup"].endswith("open-webui-data-volume.tgz")
    assert [step["step"] for step in bundle["rollback"]["steps"]] == [
        "stop_open_webui",
        "restore_source_checkpoint",
        "restore_open_webui_volume",
        "start_open_webui",
        "verify_open_webui",
    ]
    assert "-f deploy/compose/open-webui/compose.yaml down" in bundle["rollback"]["steps"][0]["command"]
    assert "-f deploy/compose/open-webui/compose.yaml up -d" in bundle["rollback"]["steps"][3]["command"]
    assert bundle["rollback"]["steps"][-1]["command"] == "curl -fsS --max-time 10 http://127.0.0.1:3001/api/version"
    assert bundle["tests"]["focused_pytest"] == "133 passed, 1 warning"
    assert bundle["tests"]["full_pytest"] == "1582 passed, 1 skipped, 1 warning"
    assert bundle["tests"]["backup_rollback_audit_ok"] is True
    assert bundle["tests"]["secret_safety_audit_ok"] is True
    assert bundle["tests"]["channels_deterministic"] is True
    assert bundle["tests"]["proactive_all_disabled"] is True
    assert bundle["tests"]["proactive_dry_run_suppressed"] is True
    assert bundle["tests"]["freyja41_preservation_ok"] is True
    assert bundle["tests"]["freyja41_legacy_endpoints_ok"] is True
    assert bundle["tests"]["completion_audit_complete"] is False
    assert bundle["tests"]["post_auth_activation_ready"] is False
    assert bundle["tests"]["inference_policy_ok"] is True
    assert bundle["tests"]["authenticated_chat_smoke"] == "pending"
    assert bundle["tests"]["open_webui_tools_gateway_ok"] is True
    assert bundle["tests"]["open_webui_tools_openapi_ok"] is True
    assert "exact_next_action" in bundle
    assert "Open WebUI" in bundle["exact_next_action"]
    assert bundle["evidence_summary"]["post_auth_activation_next_actions"] == [
        "Create/sign in Open WebUI users for: beth, jenna, joe, liam.",
        "Complete first-account onboarding, or pass --owner-user-id when multiple Open WebUI users exist.",
    ]
    assert bundle["evidence_summary"]["post_auth_activation_access_missing_users"] == ["beth", "jenna", "joe", "liam"]
    assert bundle["evidence_summary"]["post_auth_activation_access_missing_models"] == []
    assert bundle["evidence_summary"]["post_auth_activation_resource_owner_resolved"] is False
    assert bundle["evidence_summary"]["post_auth_activation_resource_owner_policy"] == "auto_single_user_only"
    assert [gate["gate_id"] for gate in bundle["external_gates"]] == [
        "post_auth_activation",
        "authenticated_chat_smoke",
        "telegram_pilot",
        "signal_pilot",
    ]
    assert all(gate["ready"] is False for gate in bundle["external_gates"])
    assert bundle["external_gates"][0]["next_action"].startswith("Complete first-account Open WebUI onboarding")
    assert any("Open WebUI users" in action for action in bundle["external_gates"][0]["next_actions"])
    assert any("generate an admin" in action for action in bundle["external_gates"][1]["next_actions"])
    assert bundle["external_gates"][2]["next_action"].startswith("Configure: TELEGRAM_ALLOWED_USER_IDS")
    assert any("TELEGRAM_BOT_TOKEN" in action for action in bundle["external_gates"][2]["next_actions"])
    assert any("SIGNAL_REST_API_URL" in action for action in bundle["external_gates"][3]["next_actions"])
    assert bundle["external_gates"][0]["command"].startswith("scripts/activate-open-webui-home-agent-post-auth.py")
    assert "OPEN_WEBUI_API_KEY=<redacted>" in bundle["external_gates"][1]["command"]
    assert "TELEGRAM_BOT_TOKEN" not in bundle["external_gates"][2]["command"]
    assert "SIGNAL_ACCOUNT_NUMBER" not in bundle["external_gates"][3]["command"]
    for gate in bundle["external_gates"]:
        assert "evidence_generated_at_unix" in gate
        assert "evidence_git_head" in gate
    requirement_audit = {item["requirement_id"]: item for item in bundle["requirement_audit"]}
    assert len(requirement_audit) == 15
    assert requirement_audit["local_inference"]["status"] == "partial"
    assert requirement_audit["five_agents"]["status"] == "auth_gated"
    assert requirement_audit["messaging_channels"]["status"] == "credential_gated"
    assert "certification/reports/open-webui-home-agent-chat-smoke.json" in requirement_audit["local_inference"]["evidence"]
    assert requirement_audit["local_inference"]["command"].startswith("OPEN_WEBUI_API_KEY=<redacted>")
    assert any("OPEN_WEBUI_API_KEY" in action for action in requirement_audit["local_inference"]["next_actions"])
    assert requirement_audit["five_agents"]["command"].startswith("scripts/activate-open-webui-home-agent-post-auth.py")
    assert any("Open WebUI users" in action for action in requirement_audit["five_agents"]["next_actions"])
    assert "scripts/run-freyja-channels-telegram-pilot.py" in requirement_audit["messaging_channels"]["command"]
    assert requirement_audit["messaging_channels"]["commands"] == [
        "scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json",
        "scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json",
    ]
    assert any("TELEGRAM_BOT_TOKEN" in action for action in requirement_audit["messaging_channels"]["next_actions"])
    assert requirement_audit["verification"]["commands"] == [
        "scripts/summarize-open-webui-home-agent-readiness.py",
        "scripts/audit-open-webui-home-agent-completion.py",
    ]
    assert requirement_audit["final_deliverable"]["status"] == "complete"
    assert bundle["artifacts"]["runbook"] == "docs/operations/open-webui-home-agent.md"
    assert bundle["artifacts"]["backup_rollback_audit"] == "certification/reports/open-webui-backup-rollback-audit.json"
    assert bundle["artifacts"]["secret_safety_audit"] == "certification/reports/open-webui-home-agent-secret-safety.json"
    assert bundle["artifacts"]["platform_inventory"] == "certification/reports/open-webui-home-agent-platform-inventory.json"
    assert bundle["artifacts"]["chat_smoke"] == "certification/reports/open-webui-home-agent-chat-smoke.json"
    assert bundle["artifacts"]["tools_gateway"] == "certification/reports/open-webui-tools-gateway-readiness.json"
    assert bundle["artifacts"]["tools_openapi"] == "certification/reports/open-webui-tools-openapi.json"
    assert bundle["artifacts"]["readiness_summary"] == "certification/reports/open-webui-home-agent-readiness-summary.json"
    assert bundle["artifacts"]["evidence_refresh"] == "certification/reports/open-webui-home-agent-evidence-refresh.json"
    assert bundle["artifacts"]["proactive_dry_run"] == "certification/reports/freyja-proactive-dry-run.json"
    assert bundle["artifacts"]["telegram_pilot"] == "certification/reports/freyja-channels-telegram-pilot.json"
    assert bundle["artifacts"]["signal_pilot"] == "certification/reports/freyja-channels-signal-pilot.json"
    assert bundle["evidence_summary"]["inventory_hosts"] == ["atlas", "hera", "iris", "vulcan"]
    endpoint_ownership = bundle["evidence_summary"]["endpoint_ownership"]
    assert endpoint_ownership["atlas_open_webui"]["endpoint"] == "http://127.0.0.1:3001"
    assert endpoint_ownership["atlas_open_webui"]["container"] == "freyja-open-webui-atlas-open-webui-1"
    assert "healthy" in endpoint_ownership["atlas_open_webui"]["status"]
    assert endpoint_ownership["atlas_model_proxy"]["endpoint"] == "http://model-proxy:8080/v1"
    assert endpoint_ownership["atlas_freyja5_gateway"]["endpoint"] == "http://127.0.0.1:8500"
    assert endpoint_ownership["vulcan_inference"]["ollama_endpoint"] == "http://100.94.80.21:11434"
    assert endpoint_ownership["vulcan_inference"]["nexus_required"] is False
    assert endpoint_ownership["iris_apple_capabilities"]["mcp_host"] == "iris"
    assert endpoint_ownership["iris_apple_capabilities"]["fallback_only_for_inference"] is True
    assert isinstance(bundle["evidence_summary"]["open_webui_public_config"], dict)
    assert bundle["evidence_summary"]["open_webui_public_config"].get("secrets_included") is False
    assert "token=" not in json.dumps(bundle["evidence_summary"]["open_webui_public_config"]).lower()
    assert "Open WebUI" in bundle["evidence_summary"]["open_webui_next_action_hint"]
    assert isinstance(bundle["evidence_summary"]["inventory_generated_at_unix"], int)
    assert bundle["evidence_summary"]["inventory_git_head"]
    assert isinstance(bundle["evidence_summary"]["live_verifier_generated_at_unix"], int)
    assert bundle["evidence_summary"]["live_verifier_git_head"]
    assert bundle["evidence_summary"]["home_memory_operations_ok"] is True
    assert bundle["evidence_summary"]["home_memory_joe_write_ok"] is True
    assert bundle["evidence_summary"]["home_memory_joe_read_ok"] is True
    assert bundle["evidence_summary"]["home_memory_recent_events_ok"] is True
    assert bundle["evidence_summary"]["home_memory_beth_denied_joe_scope_ok"] is True
    assert bundle["evidence_summary"]["backup_contains_webui_db"] is True
    assert bundle["evidence_summary"]["backup_scope"]["report_sanitized"] is True
    assert bundle["evidence_summary"]["backup_scope"]["archive_handling"] == "treat_as_sensitive_do_not_commit_or_print_contents"
    assert isinstance(bundle["evidence_summary"]["backup_rollback_generated_at_unix"], int)
    assert bundle["evidence_summary"]["backup_rollback_git_head"]
    assert bundle["evidence_summary"]["secret_safety_findings"] == 0
    assert isinstance(bundle["evidence_summary"]["secret_safety_generated_at_unix"], int)
    assert bundle["evidence_summary"]["secret_safety_git_head"]
    assert bundle["evidence_summary"]["chat_smoke_status"] == "pending"
    assert bundle["evidence_summary"]["chat_smoke_missing_configuration"] == ["OPEN_WEBUI_API_KEY"]
    assert any("generate an admin" in action for action in bundle["evidence_summary"]["chat_smoke_next_actions"])
    assert bundle["evidence_summary"]["completion_status_counts"] == bundle["completion_status_counts"]
    assert bundle["evidence_summary"]["completion_metrics"] == bundle["completion_metrics"]
    assert isinstance(bundle["evidence_summary"]["completion_audit_generated_at_unix"], int)
    assert bundle["evidence_summary"]["completion_audit_git_head"]
    assert bundle["evidence_summary"]["git_head"] == bundle["git_head"]
    assert bundle["evidence_summary"]["live_optional_pending"] == []
    assert isinstance(bundle["evidence_summary"]["access_audit_generated_at_unix"], int)
    assert bundle["evidence_summary"]["access_audit_git_head"]
    assert isinstance(bundle["evidence_summary"]["access_bind_generated_at_unix"], int)
    assert bundle["evidence_summary"]["access_bind_git_head"]
    assert bundle["evidence_summary"]["model_import_ok"] is True
    assert bundle["evidence_summary"]["model_import_validation_errors"] == []
    assert bundle["evidence_summary"]["model_import_record_count"] == 5
    agent_policy = bundle["evidence_summary"]["agent_policy_summary"]
    assert agent_policy["agent_ids"] == ["agent-44", "benedict", "cloyd", "freyja", "jenna"]
    assert agent_policy["runtime_model_ids"] == [
        "agent/agent-47",
        "agent/benedict",
        "agent/cloyd-gibbler",
        "agent/freyja",
        "agent/jennacide",
    ]
    assert agent_policy["benedict_access_groups"] == ["beth"]
    assert agent_policy["benedict_cloud_fallback"] == "forbidden"
    assert agent_policy["benedict_permitted_knowledge"] == ["personal:beth", "restricted:benedict"]
    assert agent_policy["benedict_confirm_tools"] == []
    assert "admin" in agent_policy["child_agents"]["agent-44"]["deny"]
    assert "messaging.send" in agent_policy["child_agents"]["agent-44"]["deny"]
    assert "home.device_action" in agent_policy["child_agents"]["agent-44"]["deny"]
    assert agent_policy["child_agents"]["agent-44"]["confirm"] == []
    assert "admin" in agent_policy["child_agents"]["jenna"]["deny"]
    assert "messaging.send" in agent_policy["child_agents"]["jenna"]["deny"]
    assert "home.device_action" in agent_policy["child_agents"]["jenna"]["deny"]
    assert agent_policy["child_agents"]["jenna"]["confirm"] == []
    assert isinstance(bundle["evidence_summary"]["model_import_generated_at_unix"], int)
    assert bundle["evidence_summary"]["model_import_git_head"]
    assert isinstance(bundle["evidence_summary"]["model_apply_generated_at_unix"], int)
    assert bundle["evidence_summary"]["model_apply_git_head"]
    assert bundle["evidence_summary"]["resource_export_ok"] is True
    assert bundle["evidence_summary"]["resource_export_validation_errors"] == []
    assert bundle["evidence_summary"]["resource_export_knowledge_count"] == 3
    assert bundle["evidence_summary"]["resource_export_tool_count"] == 6
    assert bundle["evidence_summary"]["resource_export_native_memory_mode"] == "per_user"
    assert isinstance(bundle["evidence_summary"]["resource_export_generated_at_unix"], int)
    assert bundle["evidence_summary"]["resource_export_git_head"]
    assert isinstance(bundle["evidence_summary"]["resource_import_generated_at_unix"], int)
    assert bundle["evidence_summary"]["resource_import_git_head"]
    assert isinstance(bundle["evidence_summary"]["resource_counts_generated_at_unix"], int)
    assert bundle["evidence_summary"]["resource_counts_git_head"]
    assert isinstance(bundle["evidence_summary"]["proxy_catalog_generated_at_unix"], int)
    assert bundle["evidence_summary"]["proxy_catalog_git_head"]
    assert bundle["evidence_summary"]["proxy_missing_models"] == []
    assert "agent/freyja" in bundle["evidence_summary"]["proxy_agent_models_present"]
    assert bundle["evidence_summary"]["proxy_agent_profiles_missing"] == []
    assert bundle["evidence_summary"]["proxy_agent_profiles_non_local"] == []
    assert bundle["evidence_summary"]["proxy_agent_profile_map"]["agent/freyja"]["provider"] == "vulcan_ollama"
    assert bundle["evidence_summary"]["tools_gateway_operation_count"] == 20
    assert bundle["evidence_summary"]["tools_gateway_destructive_default_all_deny"] is True
    assert bundle["evidence_summary"]["tools_gateway_live_side_effects_invoked"] is False
    assert bundle["evidence_summary"]["tools_gateway_execution_statuses"]["read_only"] == "dry_run_available"
    assert bundle["evidence_summary"]["tools_gateway_execution_statuses"]["pdf_analysis"] == "dry_run_available"
    assert bundle["evidence_summary"]["tools_gateway_execution_statuses"]["image_analysis"] == "dry_run_available"
    assert bundle["evidence_summary"]["tools_gateway_execution_statuses"]["confirmed_write"] == "confirmed_not_configured"
    assert "calendar.create" in bundle["evidence_summary"]["tools_gateway_confirmation_required"]
    assert "home.device_action" in bundle["evidence_summary"]["tools_gateway_confirmation_required"]
    assert "imessage.send.approved" in bundle["evidence_summary"]["tools_gateway_confirmation_required"]
    assert "shortcuts.run" in bundle["evidence_summary"]["tools_gateway_confirmation_required"]
    assert "weather.read" in bundle["evidence_summary"]["tools_gateway_child_allowed_operations"]
    assert "infrastructure.health" not in bundle["evidence_summary"]["tools_gateway_child_allowed_operations"]
    assert "home.device_action" not in bundle["evidence_summary"]["tools_gateway_child_allowed_operations"]
    assert bundle["evidence_summary"]["tools_gateway_checks"]["children_can_analyze_pdf"] is True
    assert bundle["evidence_summary"]["tools_gateway_checks"]["children_can_analyze_image"] is True
    assert bundle["evidence_summary"]["tools_gateway_checks"]["benedict_can_analyze_pdf"] is True
    assert bundle["evidence_summary"]["tools_gateway_checks"]["benedict_can_analyze_image"] is True
    assert bundle["evidence_summary"]["tools_gateway_checks"]["pdf_image_analysis_are_dry_run_only"] is True
    assert isinstance(bundle["evidence_summary"]["tools_gateway_generated_at_unix"], int)
    assert bundle["evidence_summary"]["tools_gateway_git_head"]
    assert bundle["evidence_summary"]["tools_openapi_paths"] == ["/open-webui-tools", "/open-webui-tools/invoke"]
    assert isinstance(bundle["evidence_summary"]["tools_openapi_generated_at_unix"], int)
    assert bundle["evidence_summary"]["tools_openapi_git_head"]
    assert bundle["evidence_summary"]["readiness_summary_status"] == "pending_external_auth_or_credentials"
    assert bundle["evidence_summary"]["readiness_summary_all_ready"] is False
    assert bundle["evidence_summary"]["readiness_required_next_actions"][0].startswith("Complete first-account Open WebUI onboarding")
    assert any("OPEN_WEBUI_API_KEY" in action for action in bundle["evidence_summary"]["readiness_required_next_actions"])
    assert any("TELEGRAM_BOT_TOKEN" in action for action in bundle["evidence_summary"]["readiness_required_next_actions"])
    assert any("SIGNAL_REST_API_URL" in action for action in bundle["evidence_summary"]["readiness_required_next_actions"])
    assert isinstance(bundle["evidence_summary"]["readiness_summary_generated_at_unix"], int)
    assert bundle["evidence_summary"]["readiness_summary_git_head"]
    assert isinstance(bundle["evidence_summary"]["evidence_refresh_generated_at_unix"], int)
    assert bundle["evidence_summary"]["evidence_refresh_git_head"]
    assert isinstance(bundle["evidence_summary"]["evidence_refresh_step_count"], int)
    assert isinstance(bundle["evidence_summary"]["inference_policy_generated_at_unix"], int)
    assert bundle["evidence_summary"]["inference_policy_git_head"]
    inference_checks = bundle["evidence_summary"]["inference_policy_checks"]
    assert inference_checks["open_webui_uses_model_proxy"] is True
    assert inference_checks["primary_vulcan_endpoint_configured"] is True
    assert inference_checks["vulcan_ollama_unload_endpoint_configured"] is True
    assert inference_checks["nexus_not_required"] is True
    assert inference_checks["unloads_other_primary_models"] is True
    assert inference_checks["cloud_fallback_disabled_for_open_webui_path"] is True
    assert bundle["evidence_summary"]["channels_deterministic_gateway_only"] is True
    assert bundle["evidence_summary"]["channels_model_routing_prohibited"] is True
    assert bundle["evidence_summary"]["channels_independent_agent_intelligence_prohibited"] is True
    assert bundle["evidence_summary"]["channel_thread_persistence_store"]["path"] == "data/freyja-channels/threads.json"
    assert bundle["evidence_summary"]["channel_audit_store"]["raw_sender_logged"] is False
    assert bundle["evidence_summary"]["channel_audit_store"]["denied_attempts_logged"] is True
    assert bundle["evidence_summary"]["channel_audit_store"]["response_failures_logged"] is True
    assert bundle["evidence_summary"]["channel_open_webui_client"]["endpoint"].endswith("/openai/v1/chat/completions")
    assert bundle["evidence_summary"]["channel_open_webui_client"]["api_key_configured"] is False
    assert bundle["evidence_summary"]["telegram_empty_allowlist_policy"] == "deny_all"
    assert bundle["evidence_summary"]["telegram_allowlist_count"] == 0
    assert bundle["evidence_summary"]["telegram_identity_map_count"] == 0
    assert "TELEGRAM_BOT_TOKEN" in bundle["evidence_summary"]["telegram_missing_configuration"]
    assert any("TELEGRAM_BOT_TOKEN" in action for action in bundle["evidence_summary"]["telegram_next_actions"])
    assert bundle["evidence_summary"]["telegram_pilot_ready"] is False
    assert "TELEGRAM_BOT_TOKEN" in bundle["evidence_summary"]["telegram_pilot_missing_configuration"]
    assert any("TELEGRAM_BOT_TOKEN" in action for action in bundle["evidence_summary"]["telegram_pilot_next_actions"])
    assert isinstance(bundle["evidence_summary"]["channels_readiness_generated_at_unix"], int)
    assert bundle["evidence_summary"]["channels_readiness_git_head"]
    assert isinstance(bundle["evidence_summary"]["telegram_pilot_generated_at_unix"], int)
    assert bundle["evidence_summary"]["telegram_pilot_git_head"]
    assert bundle["evidence_summary"]["telegram_pilot_checks"]["telegram_bot_token_configured"] is False
    assert bundle["evidence_summary"]["telegram_pilot_checks"]["allowlist_identity_map_complete"] is False
    assert bundle["evidence_summary"]["signal_empty_allowlist_policy"] == "deny_all"
    assert bundle["evidence_summary"]["signal_allowlist_count"] == 0
    assert bundle["evidence_summary"]["signal_identity_map_count"] == 0
    assert "SIGNAL_ACCOUNT_NUMBER" in bundle["evidence_summary"]["signal_missing_configuration"]
    assert any("SIGNAL_REST_API_URL" in action for action in bundle["evidence_summary"]["signal_next_actions"])
    assert bundle["evidence_summary"]["signal_pilot_ready"] is False
    assert "SIGNAL_ACCOUNT_NUMBER" in bundle["evidence_summary"]["signal_pilot_missing_configuration"]
    assert any("SIGNAL_REST_API_URL" in action for action in bundle["evidence_summary"]["signal_pilot_next_actions"])
    assert isinstance(bundle["evidence_summary"]["signal_pilot_generated_at_unix"], int)
    assert bundle["evidence_summary"]["signal_pilot_git_head"]
    assert bundle["evidence_summary"]["signal_pilot_checks"]["signal_account_configured"] is False
    assert bundle["evidence_summary"]["signal_pilot_checks"]["allowlist_identity_map_complete"] is False
    assert bundle["evidence_summary"]["whatsapp_ready"] is False
    assert bundle["evidence_summary"]["whatsapp_status"] == "disabled"
    assert bundle["evidence_summary"]["whatsapp_reason"] == "secured_public_webhook_not_approved"
    assert bundle["evidence_summary"]["proactive_candidate_count"] == 27
    assert bundle["evidence_summary"]["proactive_ready_schedule_count"] == 0
    assert bundle["evidence_summary"]["proactive_blocked_reason_counts"]["job_disabled"] == 27
    assert bundle["evidence_summary"]["proactive_blocked_reason_counts"]["dry_run_required"] == 27
    assert bundle["evidence_summary"]["proactive_enablement_gate"] == {
        "chat_stable": "required",
        "destinations_verified": "required",
        "dry_run_first": "required",
        "per_schedule_approval": "required",
        "recipients_verified": "required",
    }
    assert bundle["evidence_summary"]["proactive_prohibitions"] == {
        "enable_globally_by_default": True,
        "infer_unverified_destination": True,
        "message_children_without_parent_policy": True,
        "run_destructive_tools": True,
    }
    assert bundle["evidence_summary"]["proactive_dry_run_would_send_count"] == 0
    assert bundle["evidence_summary"]["proactive_dry_run_all_sends_suppressed"] is True
    assert isinstance(bundle["evidence_summary"]["proactive_readiness_generated_at_unix"], int)
    assert bundle["evidence_summary"]["proactive_readiness_git_head"]
    assert isinstance(bundle["evidence_summary"]["proactive_dry_run_generated_at_unix"], int)
    assert bundle["evidence_summary"]["proactive_dry_run_git_head"]
    assert bundle["evidence_summary"]["freyja41_legacy_endpoint_check"] is True
    assert isinstance(bundle["evidence_summary"]["freyja41_generated_at_unix"], int)
    assert bundle["evidence_summary"]["freyja41_git_head"]
    assert bundle["evidence_summary"]["freyja41_legacy_inference_endpoint_count"] == 7
    assert bundle["requirement_status"]["scoped_memory_service"] == "deployed and live-tested"


def test_bundle_markdown_renders_high_signal_summary() -> None:
    module = _module()
    text = module.render_markdown(module.build_bundle(now=1))

    assert "# Open WebUI Home-Agent Deliverable" in text
    assert "Verified completion: `60.0%` (9/15 requirements)" in text
    assert "Focused tests" in text
    assert "Full tests" in text
    assert "Backup rollback audit ok" in text
    assert "`restore_open_webui_volume`: `tar -xzf logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz" in text
    assert "Secret safety audit ok" in text
    assert "Channels deterministic" in text
    assert "Proactive all disabled" in text
    assert "Proactive dry-run suppressed" in text
    assert "Freyja 4.1 preservation ok" in text
    assert "Freyja 4.1 legacy endpoints ok" in text
    assert "Completion audit complete" in text
    assert "Post-auth activation ready" in text
    assert "Inference policy ok" in text
    assert "Authenticated chat smoke" in text
    assert "Open WebUI tools gateway ok" in text
    assert "Open WebUI tools OpenAPI ok" in text
    assert "Readiness summary" in text
    assert "## Inference" in text
    assert "`fast_chat`: `qwen2.5:32b-instruct`" in text
    assert "`strong_reasoning`: `qwen3:30b-a3b`" in text
    assert "`vision_documents`: `qwen2.5vl:72b`" in text
    assert "`coding`: `qwen3-coder-next:q4_K_M`" in text
    assert "`large_model_guard_enabled`: `True`" in text
    assert "`nexus_not_required`: `True`" in text
    assert "`unloads_other_primary_models`: `True`" in text
    assert "## Post-Auth Activation" in text
    assert "Missing users: `beth, jenna, joe, liam`" in text
    assert "Resource owner policy: `auto_single_user_only`" in text
    assert "Activation action: Complete first-account onboarding" in text
    assert "## Endpoint Ownership" in text
    assert "`atlas_open_webui`" in text
    assert "nexus_required=False" in text
    assert "## Agent Policy" in text
    assert "Benedict" in text
    assert "restricted:benedict" in text
    assert "Child `agent-44`" in text
    assert "messaging.send" in text
    assert "## Memory" in text
    assert "`home_memory_beth_denied_joe_scope_ok`: `True`" in text
    assert "## Tool Authorization" in text
    assert "`confirmation_required`" in text
    assert "imessage.send.approved" in text
    assert "`child_allowed_operations`" in text
    assert "weather.read" in text
    assert "pdf_analysis" in text
    assert "image_analysis" in text
    assert "## Channel Safety" in text
    assert "`telegram_empty_allowlist_policy`: `deny_all`" in text
    assert "`telegram_allowlist_count`: `0`" in text
    assert "`telegram_identity_map_count`: `0`" in text
    assert "`signal_empty_allowlist_policy`: `deny_all`" in text
    assert "`signal_allowlist_count`: `0`" in text
    assert "`signal_identity_map_count`: `0`" in text
    assert "## Proactive Safety" in text
    assert "dry_run_required" in text
    assert "## Required Next Actions" in text
    assert "Set OPEN_WEBUI_API_KEY outside source control." in text
    assert "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account." not in text
    assert "External Gates" in text
    assert "`post_auth_activation`: pending" in text
    assert "Action: Create/sign in Open WebUI users" in text
    assert "Action: Create/sign in to Open WebUI and generate an admin" in text
    assert "`telegram_pilot`: pending" in text
    assert "Action: Create or choose the Telegram bot" in text
    assert "Action: Set SIGNAL_REST_API_URL" in text
    assert "Command: `scripts/activate-open-webui-home-agent-post-auth.py" in text
    assert "Requirement Audit" in text
    assert "`local_inference`: `partial`" in text
    assert "`messaging_channels`: `credential_gated`" in text
    assert "Action: Rerun scripts/smoke-open-webui-home-agent-chats.py and require status=complete for all five agents." in text
    assert "Action: Set TELEGRAM_ALLOWED_USER_IDS with reviewed family sender IDs; keep an empty allowlist as deny-all." in text
    assert "Command: `OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py" in text
    assert "Command: `scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json`" in text
    assert text.count("Command: `scripts/summarize-open-webui-home-agent-readiness.py`") == 0
    assert "pending_external_auth_or_credentials" in text
    assert "readiness_summary" in text
    assert "Exact Next Action" in text
    assert "Open WebUI owner/user rows are missing" in text


def test_bundle_main_creates_distinct_output_directories(tmp_path: Path, capsys) -> None:
    output_json = tmp_path / "json" / "deliverable.json"
    output_md = tmp_path / "markdown" / "deliverable.md"

    assert _module().main(["--output-json", str(output_json), "--output-md", str(output_md)]) == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    assert json.loads(output_json.read_text(encoding="utf-8"))["report_type"] == "open-webui-home-agent-consolidated-deliverable"
    assert "Open WebUI Home-Agent Deliverable" in output_md.read_text(encoding="utf-8")


def test_bundle_dedupes_values_without_reordering() -> None:
    assert _module()._dedupe(["first", "second", "first", "third", "second"]) == ["first", "second", "third"]


def test_loader_rejects_reports_not_marked_secret_free(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module()._load_json(path)
