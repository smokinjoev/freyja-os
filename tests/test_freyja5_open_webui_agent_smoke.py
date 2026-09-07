from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "freyja5-open-webui-agent-smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("freyja5_open_webui_agent_smoke", SMOKE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_webui_agent_smoke_lists_models_and_checks_freyja_and_cloyd(monkeypatch) -> None:
    smoke = load_smoke_module()
    calls: list[tuple[str, str, str, dict | None]] = []

    def fake_request_json(method, url, *, token="", payload=None, timeout=15.0):
        calls.append((method, url, token, payload))
        if url.endswith("/models"):
            return 200, {"data": [{"id": model_id} for model_id in smoke.AGENT_MODEL_IDS]}
        model_id = payload["model"]
        return 200, {
            "model": model_id,
            "freyja": {
                "agent": "freyja" if model_id == "agent/freyja" else "cloyd-gibbler",
                "agent_model": model_id,
                "route": "general" if model_id == "agent/freyja" else "code",
                "endpoint": "vulcan-nexus-strong" if model_id == "agent/freyja" else "vulcan-nexus-coder",
                "provider": "nexus",
                "egress_state": "local-only",
                "trace": {
                    "channel": "open-webui",
                    "resolved_user": "person:joe",
                    "inference_status": "not_run",
                },
            },
        }

    monkeypatch.setattr(smoke, "_request_json", fake_request_json)

    report = smoke.run_smoke(base_url="http://atlas.test:8080/v1/", token="secret-token", timeout=1.5)

    assert report["passed"] is True
    assert report["base_url"] == "http://atlas.test:8080/v1"
    assert report["token_configured"] is True
    assert "secret-token" not in str(report)
    assert [check["name"] for check in report["checks"]] == ["models", "chat_freyja", "chat_cloyd"]
    assert report["checks"][0]["agent_models"] == smoke.AGENT_MODEL_IDS
    assert report["checks"][1]["agent"] == "freyja"
    assert report["checks"][2]["agent"] == "cloyd-gibbler"
    assert {call[2] for call in calls} == {"secret-token"}
