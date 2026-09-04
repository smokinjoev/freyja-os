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
    assert bundle["status"] == "maximally_completed_pending_external_auth"
    assert bundle["git_head"]
    assert bundle["completion_status_counts"] == {"auth_gated": 3, "complete": 9, "credential_gated": 1, "partial": 2}
    assert bundle["endpoint_map"]["open_webui_local"] == "http://127.0.0.1:3001"
    assert bundle["rollback"]["open_webui_volume_backup"].endswith("open-webui-data-volume.tgz")
    assert [step["step"] for step in bundle["rollback"]["steps"]] == [
        "stop_open_webui",
        "restore_source_checkpoint",
        "restore_open_webui_volume",
        "start_open_webui",
        "verify_open_webui",
    ]
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
    assert [gate["gate_id"] for gate in bundle["external_gates"]] == [
        "post_auth_activation",
        "authenticated_chat_smoke",
        "telegram_pilot",
        "signal_pilot",
    ]
    assert all(gate["ready"] is False for gate in bundle["external_gates"])
    assert bundle["external_gates"][0]["next_action"].startswith("Create/sign in to Open WebUI")
    assert bundle["external_gates"][2]["next_action"].startswith("Set TELEGRAM_BOT_TOKEN")
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
    assert requirement_audit["five_agents"]["command"].startswith("scripts/activate-open-webui-home-agent-post-auth.py")
    assert "scripts/run-freyja-channels-telegram-pilot.py" in requirement_audit["messaging_channels"]["command"]
    assert requirement_audit["final_deliverable"]["status"] == "complete"
    assert bundle["artifacts"]["runbook"] == "docs/operations/open-webui-home-agent.md"
    assert bundle["artifacts"]["backup_rollback_audit"] == "certification/reports/open-webui-backup-rollback-audit.json"
    assert bundle["artifacts"]["secret_safety_audit"] == "certification/reports/open-webui-home-agent-secret-safety.json"
    assert bundle["artifacts"]["platform_inventory"] == "certification/reports/open-webui-home-agent-platform-inventory.json"
    assert bundle["artifacts"]["chat_smoke"] == "certification/reports/open-webui-home-agent-chat-smoke.json"
    assert bundle["artifacts"]["tools_gateway"] == "certification/reports/open-webui-tools-gateway-readiness.json"
    assert bundle["artifacts"]["tools_openapi"] == "certification/reports/open-webui-tools-openapi.json"
    assert bundle["artifacts"]["readiness_summary"] == "certification/reports/open-webui-home-agent-readiness-summary.json"
    assert bundle["artifacts"]["proactive_dry_run"] == "certification/reports/freyja-proactive-dry-run.json"
    assert bundle["artifacts"]["telegram_pilot"] == "certification/reports/freyja-channels-telegram-pilot.json"
    assert bundle["artifacts"]["signal_pilot"] == "certification/reports/freyja-channels-signal-pilot.json"
    assert bundle["evidence_summary"]["inventory_hosts"] == ["atlas", "hera", "iris", "vulcan"]
    assert isinstance(bundle["evidence_summary"]["inventory_generated_at_unix"], int)
    assert bundle["evidence_summary"]["inventory_git_head"]
    assert isinstance(bundle["evidence_summary"]["live_verifier_generated_at_unix"], int)
    assert bundle["evidence_summary"]["live_verifier_git_head"]
    assert bundle["evidence_summary"]["backup_contains_webui_db"] is True
    assert isinstance(bundle["evidence_summary"]["backup_rollback_generated_at_unix"], int)
    assert bundle["evidence_summary"]["backup_rollback_git_head"]
    assert bundle["evidence_summary"]["secret_safety_findings"] == 0
    assert isinstance(bundle["evidence_summary"]["secret_safety_generated_at_unix"], int)
    assert bundle["evidence_summary"]["secret_safety_git_head"]
    assert bundle["evidence_summary"]["chat_smoke_status"] == "pending"
    assert bundle["evidence_summary"]["completion_status_counts"] == bundle["completion_status_counts"]
    assert isinstance(bundle["evidence_summary"]["completion_audit_generated_at_unix"], int)
    assert bundle["evidence_summary"]["completion_audit_git_head"]
    assert bundle["evidence_summary"]["git_head"] == bundle["git_head"]
    assert bundle["evidence_summary"]["live_optional_pending"] == []
    assert isinstance(bundle["evidence_summary"]["access_audit_generated_at_unix"], int)
    assert bundle["evidence_summary"]["access_audit_git_head"]
    assert isinstance(bundle["evidence_summary"]["access_bind_generated_at_unix"], int)
    assert bundle["evidence_summary"]["access_bind_git_head"]
    assert isinstance(bundle["evidence_summary"]["model_apply_generated_at_unix"], int)
    assert bundle["evidence_summary"]["model_apply_git_head"]
    assert isinstance(bundle["evidence_summary"]["resource_export_generated_at_unix"], int)
    assert bundle["evidence_summary"]["resource_export_git_head"]
    assert isinstance(bundle["evidence_summary"]["resource_import_generated_at_unix"], int)
    assert bundle["evidence_summary"]["resource_import_git_head"]
    assert isinstance(bundle["evidence_summary"]["resource_counts_generated_at_unix"], int)
    assert bundle["evidence_summary"]["resource_counts_git_head"]
    assert isinstance(bundle["evidence_summary"]["proxy_catalog_generated_at_unix"], int)
    assert bundle["evidence_summary"]["proxy_catalog_git_head"]
    assert bundle["evidence_summary"]["tools_gateway_operation_count"] == 20
    assert isinstance(bundle["evidence_summary"]["tools_gateway_generated_at_unix"], int)
    assert bundle["evidence_summary"]["tools_gateway_git_head"]
    assert bundle["evidence_summary"]["tools_openapi_paths"] == ["/open-webui-tools", "/open-webui-tools/invoke"]
    assert isinstance(bundle["evidence_summary"]["tools_openapi_generated_at_unix"], int)
    assert bundle["evidence_summary"]["tools_openapi_git_head"]
    assert bundle["evidence_summary"]["readiness_summary_status"] == "pending_external_auth_or_credentials"
    assert bundle["evidence_summary"]["readiness_summary_all_ready"] is False
    assert isinstance(bundle["evidence_summary"]["readiness_summary_generated_at_unix"], int)
    assert bundle["evidence_summary"]["readiness_summary_git_head"]
    assert isinstance(bundle["evidence_summary"]["inference_policy_generated_at_unix"], int)
    assert bundle["evidence_summary"]["inference_policy_git_head"]
    assert bundle["evidence_summary"]["channel_thread_persistence_store"]["path"] == "data/freyja-channels/threads.json"
    assert bundle["evidence_summary"]["channel_audit_store"]["raw_sender_logged"] is False
    assert bundle["evidence_summary"]["channel_audit_store"]["denied_attempts_logged"] is True
    assert bundle["evidence_summary"]["channel_audit_store"]["response_failures_logged"] is True
    assert bundle["evidence_summary"]["channel_open_webui_client"]["endpoint"].endswith("/openai/v1/chat/completions")
    assert bundle["evidence_summary"]["channel_open_webui_client"]["api_key_configured"] is False
    assert bundle["evidence_summary"]["telegram_pilot_ready"] is False
    assert isinstance(bundle["evidence_summary"]["channels_readiness_generated_at_unix"], int)
    assert bundle["evidence_summary"]["channels_readiness_git_head"]
    assert isinstance(bundle["evidence_summary"]["telegram_pilot_generated_at_unix"], int)
    assert bundle["evidence_summary"]["telegram_pilot_git_head"]
    assert bundle["evidence_summary"]["telegram_pilot_checks"]["telegram_bot_token_configured"] is False
    assert bundle["evidence_summary"]["telegram_pilot_checks"]["allowlist_identity_map_complete"] is False
    assert bundle["evidence_summary"]["signal_pilot_ready"] is False
    assert isinstance(bundle["evidence_summary"]["signal_pilot_generated_at_unix"], int)
    assert bundle["evidence_summary"]["signal_pilot_git_head"]
    assert bundle["evidence_summary"]["signal_pilot_checks"]["signal_account_configured"] is False
    assert bundle["evidence_summary"]["signal_pilot_checks"]["allowlist_identity_map_complete"] is False
    assert bundle["evidence_summary"]["proactive_dry_run_would_send_count"] == 0
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
    assert "External Gates" in text
    assert "`post_auth_activation`: pending" in text
    assert "`telegram_pilot`: pending" in text
    assert "Command: `scripts/activate-open-webui-home-agent-post-auth.py" in text
    assert "Requirement Audit" in text
    assert "`local_inference`: `partial`" in text
    assert "`messaging_channels`: `credential_gated`" in text
    assert "Command: `OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py" in text
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


def test_loader_rejects_reports_not_marked_secret_free(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module()._load_json(path)
