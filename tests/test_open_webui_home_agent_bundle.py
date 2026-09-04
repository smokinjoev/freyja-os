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
    assert bundle["tests"]["focused_pytest"] == "117 passed, 1 warning"
    assert bundle["tests"]["full_pytest"] == "1554 passed, 1 skipped, 1 warning"
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
    assert bundle["artifacts"]["runbook"] == "docs/operations/open-webui-home-agent.md"
    assert bundle["artifacts"]["backup_rollback_audit"] == "certification/reports/open-webui-backup-rollback-audit.json"
    assert bundle["artifacts"]["secret_safety_audit"] == "certification/reports/open-webui-home-agent-secret-safety.json"
    assert bundle["artifacts"]["platform_inventory"] == "certification/reports/open-webui-home-agent-platform-inventory.json"
    assert bundle["artifacts"]["chat_smoke"] == "certification/reports/open-webui-home-agent-chat-smoke.json"
    assert bundle["artifacts"]["tools_gateway"] == "certification/reports/open-webui-tools-gateway-readiness.json"
    assert bundle["artifacts"]["tools_openapi"] == "certification/reports/open-webui-tools-openapi.json"
    assert bundle["artifacts"]["proactive_dry_run"] == "certification/reports/freyja-proactive-dry-run.json"
    assert bundle["evidence_summary"]["inventory_hosts"] == ["atlas", "hera", "iris", "vulcan"]
    assert bundle["evidence_summary"]["backup_contains_webui_db"] is True
    assert bundle["evidence_summary"]["secret_safety_findings"] == 0
    assert bundle["evidence_summary"]["chat_smoke_status"] == "pending"
    assert bundle["evidence_summary"]["completion_status_counts"] == bundle["completion_status_counts"]
    assert bundle["evidence_summary"]["git_head"] == bundle["git_head"]
    assert bundle["evidence_summary"]["live_optional_pending"] == []
    assert bundle["evidence_summary"]["tools_gateway_operation_count"] == 20
    assert bundle["evidence_summary"]["tools_openapi_paths"] == ["/open-webui-tools", "/open-webui-tools/invoke"]
    assert bundle["evidence_summary"]["channel_thread_persistence_store"]["path"] == "data/freyja-channels/threads.json"
    assert bundle["evidence_summary"]["channel_audit_store"]["raw_sender_logged"] is False
    assert bundle["evidence_summary"]["channel_audit_store"]["denied_attempts_logged"] is True
    assert bundle["evidence_summary"]["channel_open_webui_client"]["endpoint"].endswith("/openai/v1/chat/completions")
    assert bundle["evidence_summary"]["channel_open_webui_client"]["api_key_configured"] is False
    assert bundle["evidence_summary"]["proactive_dry_run_would_send_count"] == 0
    assert bundle["evidence_summary"]["freyja41_legacy_endpoint_check"] is True
    assert bundle["evidence_summary"]["freyja41_legacy_inference_endpoint_count"] == 7
    assert bundle["requirement_status"]["scoped_memory_service"] == "deployed and live-tested"


def test_bundle_markdown_renders_high_signal_summary() -> None:
    module = _module()
    text = module.render_markdown(module.build_bundle(now=1))

    assert "# Open WebUI Home-Agent Deliverable" in text
    assert "Focused tests" in text
    assert "Full tests" in text
    assert "Backup rollback audit ok" in text
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
    assert "Exact Next Action" in text
    assert "Open WebUI owner/user rows are missing" in text


def test_loader_rejects_reports_not_marked_secret_free(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module()._load_json(path)
