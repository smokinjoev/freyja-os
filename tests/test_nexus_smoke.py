from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_PATH = REPO_ROOT / "scripts" / "nexus-smoke.py"


def _load_smoke():
    spec = importlib.util.spec_from_file_location("nexus_smoke", SMOKE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_safe_body_redacts_secret_shaped_fields() -> None:
    smoke = _load_smoke()

    safe = smoke._safe_body(
        {
            "id": "ok",
            "token": "secret",
            "apiKey": "secret",
            "nested": {"authorization": "Bearer secret"},
            "choices": [{"message": {"content": "private output"}}],
        }
    )

    assert safe["id"] == "ok"
    assert safe["token"] == "<redacted>"
    assert safe["apiKey"] == "<redacted>"
    assert safe["nested"]["authorization"] == "<redacted>"
    assert safe["choices"] == "<omitted>"


def test_run_smoke_reports_ready_only_with_successful_gateway_and_expected_failures(monkeypatch) -> None:
    smoke = _load_smoke()
    calls = []

    def fake_request(method, url, *, token="", payload=None, timeout=20.0):
        calls.append((method, url, token, payload, timeout))
        if "not-a-real-preset" in str(payload) or token == "bad-token":
            return {"ok": False, "status": 401 if token == "bad-token" else 404}
        body = {"data": [{"id": "model"}]}
        if payload and payload.get("messages"):
            body = {"model": "qwen", "choices": [{"message": {"content": "nexus-ok"}}]}
        return {"ok": True, "status": 200, "body": smoke._safe_body(body), "raw_body": body}

    monkeypatch.setattr(smoke, "_request", fake_request)

    report = smoke.run_smoke("http://nexus.test:3939/", "real-token", "@preset/freyja-fast-local")

    assert report["ready"] is True
    assert report["base_url"] == "http://nexus.test:3939"
    assert report["token_value"] == "<redacted>"
    assert report["checks"]["chat"]["response_matched"] is True
    assert report["checks"]["chat"]["resolved_model"] == "qwen"
    assert all("raw_body" not in check for check in report["checks"].values())
    assert calls[2][1] == "http://nexus.test:3939/v1/models"
    assert calls[3][3]["model"] == "@preset/freyja-fast-local"


def test_run_smoke_not_ready_when_chat_text_does_not_match(monkeypatch) -> None:
    smoke = _load_smoke()

    def fake_request(method, url, *, token="", payload=None, timeout=20.0):
        if "not-a-real-preset" in str(payload) or token == "bad-token":
            return {"ok": False, "status": 404}
        body = {"choices": [{"message": {"content": "wrong"}}]} if payload else {}
        return {"ok": True, "status": 200, "body": smoke._safe_body(body), "raw_body": body}

    monkeypatch.setattr(smoke, "_request", fake_request)

    report = smoke.run_smoke("http://nexus.test:3939", "real-token", "@preset/freyja-fast-local")

    assert report["ready"] is False
    assert report["checks"]["chat"]["response_matched"] is False
