from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "summarize-open-webui-home-agent-readiness.py"


def _module():
    spec = importlib.util.spec_from_file_location("summarize_open_webui_home_agent_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readiness_summary_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & 0o111


def test_readiness_summary_reports_current_external_gates() -> None:
    summary = _module().build_summary()

    assert summary["secrets_included"] is False
    assert summary["private_content_included"] is False
    assert isinstance(summary["generated_at_unix"], int)
    assert summary["status"] == "pending_external_auth_or_credentials"
    assert summary["all_ready"] is False
    gates = {gate["gate_id"]: gate for gate in summary["gates"]}
    assert set(gates) == {"post_auth_activation", "authenticated_chat_smoke", "telegram_pilot", "signal_pilot"}
    assert gates["post_auth_activation"]["ready"] is False
    assert gates["authenticated_chat_smoke"]["ready"] is False
    assert gates["telegram_pilot"]["ready"] is False
    assert gates["signal_pilot"]["ready"] is False
    for gate in gates.values():
        assert gate["evidence_generated_at_unix"] is None or isinstance(gate["evidence_generated_at_unix"], int)
    assert "Open WebUI" in gates["post_auth_activation"]["next_action"]
    assert any("Atlas Open WebUI admin" in action for action in gates["post_auth_activation"]["next_actions"])
    assert "OPEN_WEBUI_API_KEY" in gates["authenticated_chat_smoke"]["next_action"]
    assert any("generate an admin" in action for action in gates["authenticated_chat_smoke"]["next_actions"])
    assert "TELEGRAM_IDENTITY_MAP" in gates["telegram_pilot"]["next_action"]
    assert any("TELEGRAM_BOT_TOKEN" in action for action in gates["telegram_pilot"]["next_actions"])
    assert "SIGNAL_IDENTITY_MAP" in gates["signal_pilot"]["next_action"]
    assert any("SIGNAL_REST_API_URL" in action for action in gates["signal_pilot"]["next_actions"])
    assert gates["post_auth_activation"]["command"].startswith("scripts/activate-open-webui-home-agent-post-auth.py")
    assert "OPEN_WEBUI_API_KEY=<redacted>" in gates["authenticated_chat_smoke"]["command"]
    assert "TELEGRAM_BOT_TOKEN" not in gates["telegram_pilot"]["command"]
    assert "SIGNAL_ACCOUNT_NUMBER" not in gates["signal_pilot"]["command"]
    assert summary["required_next_actions"][0].startswith("Sign in to Atlas Open WebUI")
    assert any("OPEN_WEBUI_API_KEY" in action for action in summary["required_next_actions"])
    assert any("TELEGRAM_BOT_TOKEN" in action for action in summary["required_next_actions"])
    assert any("SIGNAL_REST_API_URL" in action for action in summary["required_next_actions"])
    assert len(summary["required_next_actions"]) == len(set(summary["required_next_actions"]))


def test_readiness_summary_prefers_current_git_head(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_git_head", lambda: "current-head")

    summary = module.build_summary()

    assert summary["git_head"] == "current-head"


def test_readiness_summary_uses_inventory_next_action_for_post_auth_gate(monkeypatch) -> None:
    module = _module()

    reports = {
        "open-webui-home-agent-post-auth-activation.json": {
            "secrets_included": False,
            "ready": False,
            "next_actions": ["Create/sign in Open WebUI users for: joe."],
        },
        "open-webui-home-agent-chat-smoke.json": {
            "secrets_included": False,
            "status": "pending",
            "reason": "OPEN_WEBUI_API_KEY not supplied",
        },
        "freyja-channels-telegram-pilot.json": {"secrets_included": False, "ready": False, "checks": {}},
        "freyja-channels-signal-pilot.json": {"secrets_included": False, "ready": False, "checks": {}},
        "open-webui-home-agent-deliverable.json": {"secrets_included": False, "exact_next_action": "old action"},
        "open-webui-home-agent-completion-audit.json": {"secrets_included": False, "status_counts": {}},
        "open-webui-home-agent-platform-inventory.json": {
            "secrets_included": False,
            "open_webui_next_action_hint": "Complete first-account Open WebUI onboarding at http://127.0.0.1:3001.",
        },
        "freyja-channels-readiness.json": {
            "secrets_included": False,
            "telegram": {},
            "signal": {},
        },
    }

    monkeypatch.setattr(module, "_load", lambda path: reports[path.name])

    summary = module.build_summary()
    gates = {gate["gate_id"]: gate for gate in summary["gates"]}

    assert gates["post_auth_activation"]["next_action"].startswith("Complete first-account Open WebUI onboarding")
    assert gates["post_auth_activation"]["next_actions"] == ["Create/sign in Open WebUI users for: joe."]
    assert summary["exact_next_action"] == gates["post_auth_activation"]["next_action"]
    assert summary["required_next_actions"][0] == gates["post_auth_activation"]["next_action"]


def test_readiness_summary_uses_channel_missing_configuration_without_secret_values(monkeypatch) -> None:
    module = _module()

    reports = {
        "open-webui-home-agent-post-auth-activation.json": {"secrets_included": False, "ready": False},
        "open-webui-home-agent-chat-smoke.json": {"secrets_included": False, "status": "pending"},
        "freyja-channels-telegram-pilot.json": {"secrets_included": False, "ready": False, "checks": {}},
        "freyja-channels-signal-pilot.json": {"secrets_included": False, "ready": False, "checks": {}},
        "open-webui-home-agent-deliverable.json": {"secrets_included": False, "exact_next_action": "old action"},
        "open-webui-home-agent-completion-audit.json": {"secrets_included": False, "status_counts": {}},
        "open-webui-home-agent-platform-inventory.json": {"secrets_included": False, "open_webui_next_action_hint": "onboard"},
        "freyja-channels-readiness.json": {
            "secrets_included": False,
            "telegram": {"missing_configuration": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_IDENTITY_MAP:missing_allowlist_entries"]},
            "signal": {"missing_configuration": ["SIGNAL_ACCOUNT_NUMBER", "SIGNAL_REST_API_URL"]},
        },
    }

    monkeypatch.setattr(module, "_load", lambda path: reports[path.name])

    summary = module.build_summary()
    gates = {gate["gate_id"]: gate for gate in summary["gates"]}
    serialized = json.dumps(summary)

    assert gates["telegram_pilot"]["next_action"] == "Configure: TELEGRAM_BOT_TOKEN, TELEGRAM_IDENTITY_MAP:missing_allowlist_entries."
    assert gates["signal_pilot"]["next_action"] == "Configure: SIGNAL_ACCOUNT_NUMBER, SIGNAL_REST_API_URL."
    assert gates["telegram_pilot"]["next_actions"] == [
        "Create or choose the Telegram bot and set TELEGRAM_BOT_TOKEN outside source control.",
        "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
        "Run scripts/run-freyja-channels-telegram-pilot.py --dry-run before enabling the long-polling pilot.",
    ]
    assert gates["signal_pilot"]["next_actions"] == [
        "Set SIGNAL_REST_API_URL for the existing signal-cli-rest-api endpoint.",
        "Set SIGNAL_ACCOUNT_NUMBER for the registered dedicated Signal account.",
        "Run scripts/run-freyja-channels-signal-pilot.py --dry-run after signal-cli-rest-api registration is healthy.",
    ]
    assert "secret-token-value" not in serialized


def test_readiness_summary_markdown_includes_required_next_actions() -> None:
    module = _module()
    text = module.render_markdown(module.build_summary())

    assert "## Required Next Actions" in text
    assert "Generate an Atlas Open WebUI admin or service-account API key" in text


def test_home_agent_runbook_documents_required_next_action_queue() -> None:
    text = (REPO_ROOT / "docs" / "operations" / "open-webui-home-agent.md").read_text(encoding="utf-8")

    assert "Machine-readable readiness queue" in text
    assert "jq '.required_next_actions'" in text
    assert "Current operator sequence" in text
    assert "Atlas Open WebUI admin account" in text
    assert "OPEN_WEBUI_API_KEY" in text
    assert "Set OPEN_WEBUI_API_KEY outside source control." in text
    assert "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account." not in text
    assert "TELEGRAM_BOT_TOKEN" in text
    assert "SIGNAL_REST_API_URL" in text
    assert "keep empty allowlists as deny-all" in text
    assert "certification/reports/open-webui-backup-rollback-audit.json" in text
    assert "verified `deploy/compose/open-webui/compose.yaml` rollback compose path" in text


def test_readiness_summary_main_writes_reports_and_exits_nonzero_while_pending(tmp_path: Path, capsys) -> None:
    output_json = tmp_path / "summary.json"
    output_md = tmp_path / "summary.md"

    assert _module().main(["--output-json", str(output_json), "--output-md", str(output_md)]) == 1

    printed = json.loads(capsys.readouterr().out)
    assert json.loads(output_json.read_text(encoding="utf-8")) == printed
    markdown = output_md.read_text(encoding="utf-8")
    assert "Open WebUI Home-Agent Readiness Summary" in markdown
    assert "`post_auth_activation`: pending" in markdown
    assert "Action: Generate an Atlas Open WebUI admin or service-account API key" in markdown
    assert "Action: Set OPEN_WEBUI_API_KEY outside source control." in markdown
    assert "Command: `scripts/activate-open-webui-home-agent-post-auth.py" in markdown


def test_readiness_summary_main_creates_distinct_output_directories(tmp_path: Path, capsys) -> None:
    output_json = tmp_path / "json" / "summary.json"
    output_md = tmp_path / "markdown" / "summary.md"

    assert _module().main(["--output-json", str(output_json), "--output-md", str(output_md)]) == 1

    assert json.loads(output_json.read_text(encoding="utf-8")) == json.loads(capsys.readouterr().out)
    assert "Open WebUI Home-Agent Readiness Summary" in output_md.read_text(encoding="utf-8")


def test_readiness_summary_rejects_reports_not_marked_secret_free(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module()._load(bad)
