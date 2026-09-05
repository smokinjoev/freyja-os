from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "smoke-open-webui-home-agent-chats.py"


def _module():
    spec = importlib.util.spec_from_file_location("smoke_open_webui_home_agent_chats", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chat_smoke_dry_run_lists_all_agents_without_secrets(tmp_path: Path, capsys) -> None:
    output = tmp_path / "smoke.json"

    assert _module().main(["--dry-run", "--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert printed == report
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["timestamp_unix"] == report["generated_at_unix"]
    assert report["git_head"]
    assert report["status"] == "pending"
    assert report["missing_configuration"] == []
    assert report["next_actions"] == [
        "Set OPEN_WEBUI_API_KEY when ready to perform the authenticated five-agent chat smoke.",
        "Rerun without --dry-run and require status=complete for all selected agents.",
    ]
    assert {item["agent_id"] for item in report["checks"]} == {
        "freyja",
        "cloyd",
        "benedict",
        "agent-44",
        "jenna",
    }
    assert all(item["open_webui_model_id"].startswith("agent/") for item in report["checks"])


def test_chat_smoke_missing_api_key_is_pending(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "smoke.json"
    monkeypatch.delenv("OPEN_WEBUI_API_KEY", raising=False)

    assert _module().main(["--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pending"
    assert report["complete"] is False
    assert report["reason"] == "OPEN_WEBUI_API_KEY not supplied"
    assert report["missing_configuration"] == ["OPEN_WEBUI_API_KEY"]
    assert report["next_actions"] == [
        "Create/sign in to Open WebUI and generate an admin or service-account API key.",
        "Set OPEN_WEBUI_API_KEY outside source control.",
        "Rerun scripts/smoke-open-webui-home-agent-chats.py and require status=complete for all five agents.",
    ]
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]


def test_chat_smoke_invalid_timeout_env_uses_default(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "smoke.json"
    monkeypatch.setenv("OPEN_WEBUI_CHAT_SMOKE_TIMEOUT", "not-a-number")
    monkeypatch.delenv("OPEN_WEBUI_API_KEY", raising=False)

    assert _module().main(["--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pending"
    assert report["reason"] == "OPEN_WEBUI_API_KEY not supplied"
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_chat_smoke_nonpositive_timeout_env_uses_default(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_WEBUI_CHAT_SMOKE_TIMEOUT", "-10")

    args = _module().build_parser().parse_args([])

    assert args.timeout == 120.0


def test_chat_smoke_live_report_redacts_auth_and_requires_response(monkeypatch) -> None:
    module = _module()
    manifest = module.load_manifest(REPO_ROOT / "config" / "open-webui-home-agents.yaml")
    calls = []

    def fake_request(base_url, api_key, model_id, display_name, *, timeout):
        calls.append(
            {
                "base_url": base_url,
                "api_key": api_key,
                "model_id": model_id,
                "display_name": display_name,
                "timeout": timeout,
            }
        )
        return 200, {"choices": [{"message": {"content": "Freyja home agent online"}}]}, None, 0.25

    monkeypatch.setattr(module, "request_chat_completion", fake_request)
    report = module.run_smoke(
        Namespace(
            open_webui_url="http://open-webui.local:3001",
            open_webui_api_key="secret-token",
            timeout=10,
            agent=["benedict"],
        ),
        manifest,
    )

    assert report["status"] == "complete"
    assert report["secrets_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["timestamp_unix"] == report["generated_at_unix"]
    assert report["git_head"]
    assert "secret-token" not in json.dumps(report)
    assert calls == [
        {
            "base_url": "http://open-webui.local:3001",
            "api_key": "secret-token",
            "model_id": "agent/benedict",
            "display_name": "Benedict",
            "timeout": 10,
        }
    ]
    assert report["checks"][0]["expected_vulcan_model"] == "qwen3:30b-a3b"
