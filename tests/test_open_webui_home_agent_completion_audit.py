from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit-open-webui-home-agent-completion.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_open_webui_home_agent_completion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_completion_audit_reports_expected_current_gate_statuses() -> None:
    audit = _module().build_audit()

    assert audit["secrets_included"] is False
    assert audit["private_content_included"] is False
    assert isinstance(audit["generated_at_unix"], int)
    assert audit["git_head"]
    assert audit["complete"] is False
    assert audit["status_counts"]["complete"] >= 5
    assert audit["status_counts"]["auth_gated"] >= 3
    assert audit["status_counts"]["credential_gated"] >= 1
    assert audit["completion_metrics"] == {
        "total_requirements": 15,
        "complete_requirements": 8,
        "incomplete_requirements": 7,
        "auth_gated_requirements": 3,
        "credential_gated_requirements": 1,
        "partial_requirements": 3,
        "external_gated_requirements": 4,
        "verified_completion_percent": 53.3,
    }
    assert audit["exact_next_action"].startswith("Use the existing Atlas Open WebUI admin account")
    assert audit["required_next_actions"][0].startswith("Use the existing Atlas Open WebUI admin account")
    assert "Set OPEN_WEBUI_API_KEY outside source control." in audit["required_next_actions"]
    assert "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account." not in audit["required_next_actions"]
    assert len(audit["required_next_actions"]) == len(set(audit["required_next_actions"]))
    ids = [item["requirement_id"] for item in audit["items"]]
    assert len(ids) == len(set(ids))
    assert {"five_agents", "memory_layers", "tools"}.issubset(
        {item["requirement_id"] for item in audit["items"] if item["status"] == "auth_gated"}
    )
    assert {"messaging_channels"} == {item["requirement_id"] for item in audit["items"] if item["status"] == "credential_gated"}
    by_id = {item["requirement_id"]: item for item in audit["items"]}
    assert "certification/reports/open-webui-home-agent-readiness-summary.json" in by_id["verification"]["evidence"]
    assert by_id["local_inference"]["command"].startswith("OPEN_WEBUI_API_KEY=<redacted>")
    assert any("OPEN_WEBUI_API_KEY" in action for action in by_id["local_inference"]["next_actions"])
    assert by_id["five_agents"]["command"].startswith("scripts/activate-open-webui-home-agent-post-auth.py")
    assert any("Open WebUI admin" in action for action in by_id["five_agents"]["next_actions"])
    assert by_id["memory_layers"]["command"] == by_id["five_agents"]["command"]
    assert by_id["memory_layers"]["next_actions"] == by_id["five_agents"]["next_actions"]
    assert by_id["tools"]["command"] == by_id["five_agents"]["command"]
    assert by_id["tools"]["next_actions"] == by_id["five_agents"]["next_actions"]
    assert "scripts/run-freyja-channels-telegram-pilot.py" in by_id["messaging_channels"]["command"]
    assert by_id["messaging_channels"]["commands"] == [
        "scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json",
        "scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json",
    ]
    assert any("TELEGRAM_BOT_TOKEN" in action for action in by_id["messaging_channels"]["next_actions"])
    assert any("SIGNAL_REST_API_URL" in action for action in by_id["messaging_channels"]["next_actions"])
    assert "TELEGRAM_BOT_TOKEN" not in by_id["messaging_channels"]["command"]
    assert "SIGNAL_ACCOUNT_NUMBER" not in by_id["messaging_channels"]["command"]
    assert by_id["verification"]["next_action"] == "Clear all external readiness gates, then rerun the completion audit."
    assert by_id["verification"]["commands"] == [
        "scripts/summarize-open-webui-home-agent-readiness.py",
        "scripts/audit-open-webui-home-agent-completion.py",
    ]
    assert any("generate an admin" in action for action in by_id["verification"]["next_actions"])
    statuses = {item["requirement"]: item["status"] for item in audit["items"]}
    assert statuses["Inspect repository, running services, Docker stacks, endpoints, credentials locations, and Open WebUI config"] == "complete"
    assert statuses["Identify Open WebUI host and Vulcan path"] == "partial"
    assert statuses["Keep inference local by default and connect Open WebUI to Vulcan"] == "partial"
    assert statuses["Create/import five Open WebUI agents"] == "auth_gated"
    assert statuses["Implement deterministic Telegram/Signal channel gateway with WhatsApp disabled"] == "credential_gated"
    assert statuses["Add proactive behavior disabled by default"] == "complete"
    assert statuses["Preserve Freyja 4.1 fallback"] == "complete"


def test_completion_audit_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "completion.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-agent-completion-audit"


def test_completion_metrics_round_verified_percent() -> None:
    items = [{"status": "complete"}, {"status": "complete"}, {"status": "partial"}]
    counts = {"complete": 2, "partial": 1}

    metrics = _module()._completion_metrics(items, counts)

    assert metrics["verified_completion_percent"] == 66.7
    assert metrics["incomplete_requirements"] == 1


def test_completion_audit_dedupes_values_without_reordering() -> None:
    assert _module()._dedupe(["first", "second", "first", "third", "second"]) == ["first", "second", "third"]


def test_completion_audit_derives_required_next_actions_from_gates() -> None:
    summary = {
        "gates": [
            {"ready": True, "next_action": "already done"},
            {
                "ready": False,
                "next_action": "first",
                "next_actions": [
                    "second",
                    "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account.",
                    "second",
                ],
            },
        ]
    }

    assert _module()._required_next_actions(summary) == [
        "first",
        "second",
        "Set OPEN_WEBUI_API_KEY outside source control.",
    ]


def test_completion_audit_prefers_current_git_head(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_git_head", lambda: "current-head")

    audit = module.build_audit()

    assert audit["git_head"] == "current-head"


def test_completion_audit_can_mark_verification_complete_when_all_readiness_gates_clear(monkeypatch) -> None:
    module = _module()

    reports = {
        "open-webui-home-agent-live.json": {"secrets_included": False, "ok": True, "open_webui_url": "http://127.0.0.1:3001"},
        "open-webui-backup-rollback-audit.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-secret-safety.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agents-offline-apply.json": {"secrets_included": False, "model_count": 5},
        "open-webui-home-agent-access-audit.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-access-bind-dry-run.json": {"secrets_included": False},
        "open-webui-home-resources-export.json": {"secrets_included": False, "ok": True},
        "open-webui-home-resources-live-counts.json": {"secrets_included": False},
        "open-webui-home-resources-offline-dry-run.json": {"secrets_included": False, "applied": True},
        "freyja-channels-readiness.json": {"secrets_included": False, "deterministic_gateway_only": True},
        "freyja-proactive-readiness.json": {
            "secrets_included": False,
            "all_disabled_by_default": True,
            "ready_schedule_ids": [],
        },
        "freyja-proactive-dry-run.json": {"secrets_included": False, "all_sends_suppressed": True},
        "freyja41-preservation-audit.json": {"secrets_included": False, "pending": []},
        "open-webui-model-proxy-catalog.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-platform-inventory.json": {
            "secrets_included": False,
            "hosts": {"atlas": {}, "vulcan": {}, "iris": {}, "hera": {}},
        },
        "open-webui-inference-policy-audit.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-chat-smoke.json": {"secrets_included": False, "status": "complete"},
        "open-webui-tools-gateway-readiness.json": {"secrets_included": False, "ok": True},
        "open-webui-tools-openapi.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-readiness-summary.json": {
            "secrets_included": False,
            "all_ready": True,
            "gates": [
                {"gate_id": "post_auth_activation", "ready": True},
                {"gate_id": "authenticated_chat_smoke", "ready": True},
                {"gate_id": "telegram_pilot", "ready": True},
                {"gate_id": "signal_pilot", "ready": True},
            ],
        },
    }

    monkeypatch.setattr(module, "_load", lambda path: reports[path.name])
    monkeypatch.setattr(module, "_exists", lambda path: True)

    audit = module.build_audit()
    by_id = {item["requirement_id"]: item for item in audit["items"]}

    assert by_id["verification"]["status"] == "complete"
    assert by_id["verification"]["blocker"] is None
    assert "next_action" not in by_id["verification"]
    assert "certification/reports/open-webui-home-agent-evidence-refresh.json" in by_id["verification"]["evidence"]


def test_completion_audit_prefers_readiness_exact_next_action(monkeypatch) -> None:
    module = _module()

    reports = {
        "open-webui-home-agent-live.json": {"secrets_included": False, "ok": True, "open_webui_url": "http://127.0.0.1:3001"},
        "open-webui-backup-rollback-audit.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-secret-safety.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agents-offline-apply.json": {"secrets_included": False, "model_count": 5},
        "open-webui-home-agent-access-audit.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-access-bind-dry-run.json": {"secrets_included": False},
        "open-webui-home-resources-export.json": {"secrets_included": False, "ok": True},
        "open-webui-home-resources-live-counts.json": {"secrets_included": False},
        "open-webui-home-resources-offline-dry-run.json": {"secrets_included": False, "applied": False},
        "freyja-channels-readiness.json": {"secrets_included": False, "deterministic_gateway_only": True},
        "freyja-proactive-readiness.json": {
            "secrets_included": False,
            "all_disabled_by_default": True,
            "ready_schedule_ids": [],
        },
        "freyja-proactive-dry-run.json": {"secrets_included": False, "all_sends_suppressed": True},
        "freyja41-preservation-audit.json": {"secrets_included": False, "pending": []},
        "open-webui-model-proxy-catalog.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-platform-inventory.json": {
            "secrets_included": False,
            "hosts": {"atlas": {}, "vulcan": {}, "iris": {}, "hera": {}},
            "open_webui_next_action_hint": "inventory action",
        },
        "open-webui-inference-policy-audit.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-chat-smoke.json": {"secrets_included": False, "status": "pending"},
        "open-webui-tools-gateway-readiness.json": {"secrets_included": False, "ok": True},
        "open-webui-tools-openapi.json": {"secrets_included": False, "ok": True},
        "open-webui-home-agent-readiness-summary.json": {
            "secrets_included": False,
            "all_ready": False,
            "exact_next_action": "readiness action",
            "gates": [],
        },
    }

    monkeypatch.setattr(module, "_load", lambda path: reports[path.name])
    monkeypatch.setattr(module, "_exists", lambda path: True)

    assert module.build_audit()["exact_next_action"] == "readiness action"


def test_completion_audit_loader_rejects_reports_not_marked_secret_free(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module()._load(bad)
