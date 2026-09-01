from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "freyja5-smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("freyja5_smoke", SMOKE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_smoke_report_is_token_safe_and_checks_webgui_paths(monkeypatch) -> None:
    smoke = load_smoke_module()
    calls: list[tuple[str, str, str, dict | None]] = []

    def fake_request_json(method, url, *, token="", payload=None, timeout=5.0):
        calls.append((method, url, token, payload))
        if url.endswith("/health"):
            return 200, {"status": "healthy"}
        if url.endswith("/freyja5/readiness"):
            return 200, {
                "ok": True,
                "version": "freyja-5.0",
                "openai_model": "freyja-5",
                "webgui": {"default_model_preserved": "agent-smith", "freyja5_opt_in": True},
                "mcp": {
                    "hosts": ["atlas", "iris"],
                    "servers": [
                        {"id": "iris-apple-mcp"},
                        {"id": "atlas-household-mcp"},
                        {"id": "atlas-media-mcp"},
                    ],
                },
                "certification": {
                    "targets": [
                        {"target": "A"},
                        {"target": "B"},
                        {"target": "C"},
                        {"target": "D"},
                        {"target": "E"},
                        {"target": "F"},
                        {"target": "G"},
                    ]
                },
            }
        if url.endswith("/v1/models") and method == "GET":
            return 200, {"data": [{"id": "agent-smith"}, {"id": "freyja-5"}]}
        route = "vision" if isinstance(payload["messages"][0]["content"], list) else "code"
        return 200, {
            "freyja": {
                "trace_id": "trace-123",
                "agent": "freyja",
                "route": route,
                "endpoint": "vulcan-nexus-vision-docs" if route == "vision" else "vulcan-nexus-coder",
                "provider": "nexus",
                "egress_state": "local-only",
                "attachment_count": 1 if route == "vision" else 0,
                "trace": {
                    "requested_route": route,
                    "channel": "open-webui",
                    "resolved_user": "person:joe",
                    "inference_status": "not_run",
                },
            }
        }

    monkeypatch.setattr(smoke, "_request_json", fake_request_json)

    report = smoke.run_smoke(base_url="http://atlas.test:8500/", token="secret-token", timeout=1.5)

    assert report["passed"] is True
    assert report["base_url"] == "http://atlas.test:8500"
    assert report["token_configured"] is True
    assert "secret-token" not in str(report)
    assert {check["name"] for check in report["checks"]} == {
        "health",
        "readiness",
        "models",
        "chat_text",
        "chat_image",
        "chat_pdf",
    }
    assert next(check for check in report["checks"] if check["name"] == "models")["models"] == [
        "agent-smith",
        "freyja-5",
    ]
    readiness = next(check for check in report["checks"] if check["name"] == "readiness")
    assert readiness["mcp_hosts"] == ["atlas", "iris"]
    assert readiness["mcp_server_ids"] == ["iris-apple-mcp", "atlas-household-mcp", "atlas-media-mcp"]
    assert readiness["certification_targets"] == ["A", "B", "C", "D", "E", "F", "G"]
    assert readiness["webgui_default_model"] == "agent-smith"
    assert readiness["webgui_freyja5_opt_in"] is True
    for check in report["checks"]:
        if check["name"].startswith("chat_"):
            assert check["trace_id"] == "trace-123"
            assert check["egress_state"] == "local-only"
            assert check["trace_channel"] == "open-webui"
    assert {call[2] for call in calls if not call[1].endswith("/health")} == {"secret-token"}


def test_freyja5_smoke_can_skip_media_checks(monkeypatch) -> None:
    smoke = load_smoke_module()

    def fake_request_json(method, url, *, token="", payload=None, timeout=5.0):
        if url.endswith("/v1/chat/completions"):
            return 200, {"freyja": {"trace": {}}}
        if url.endswith("/v1/models"):
            return 200, {"data": [{"id": "freyja-5"}]}
        return 200, {"ok": True}

    monkeypatch.setattr(smoke, "_request_json", fake_request_json)

    report = smoke.run_smoke(base_url="http://127.0.0.1:8500", token="", timeout=1.0, skip_media=True)

    assert report["passed"] is True
    assert [check["name"] for check in report["checks"]] == ["health", "readiness", "models", "chat_text"]
