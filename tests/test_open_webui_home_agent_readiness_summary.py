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
    assert summary["status"] == "pending_external_auth_or_credentials"
    assert summary["all_ready"] is False
    gates = {gate["gate_id"]: gate for gate in summary["gates"]}
    assert set(gates) == {"post_auth_activation", "authenticated_chat_smoke", "telegram_pilot", "signal_pilot"}
    assert gates["post_auth_activation"]["ready"] is False
    assert gates["authenticated_chat_smoke"]["ready"] is False
    assert gates["telegram_pilot"]["ready"] is False
    assert gates["signal_pilot"]["ready"] is False
    assert "OPEN_WEBUI_API_KEY" in gates["authenticated_chat_smoke"]["next_action"]
    assert "TELEGRAM_IDENTITY_MAP" in gates["telegram_pilot"]["next_action"]
    assert "SIGNAL_IDENTITY_MAP" in gates["signal_pilot"]["next_action"]


def test_readiness_summary_prefers_current_git_head(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_git_head", lambda: "current-head")

    summary = module.build_summary()

    assert summary["git_head"] == "current-head"


def test_readiness_summary_main_writes_reports_and_exits_nonzero_while_pending(tmp_path: Path, capsys) -> None:
    output_json = tmp_path / "summary.json"
    output_md = tmp_path / "summary.md"

    assert _module().main(["--output-json", str(output_json), "--output-md", str(output_md)]) == 1

    printed = json.loads(capsys.readouterr().out)
    assert json.loads(output_json.read_text(encoding="utf-8")) == printed
    markdown = output_md.read_text(encoding="utf-8")
    assert "Open WebUI Home-Agent Readiness Summary" in markdown
    assert "`post_auth_activation`: pending" in markdown


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
