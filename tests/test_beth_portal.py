from __future__ import annotations

import importlib.util
import io
import json
import os
from email.message import Message
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PORTAL_ROOT = REPO_ROOT / "deploy" / "compose" / "beth-portal"


def load_server_module(monkeypatch):
    monkeypatch.setenv("FREYJA_OPENAI_BASE_URL", "http://freyja.test/v1")
    monkeypatch.setenv("FREYJA_API_KEY", "test-token")
    path = PORTAL_ROOT / "server.py"
    spec = importlib.util.spec_from_file_location("beth_portal_server", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_beth_portal_hardwires_benedict_modes_without_model_picker() -> None:
    html = (PORTAL_ROOT / "app" / "index.html").read_text(encoding="utf-8")
    js = (PORTAL_ROOT / "app" / "app.js").read_text(encoding="utf-8")

    assert "mode-benedict" in html
    assert "mode-paralegal" in html
    assert "Daily + PDFs" in html
    assert "Local PDFs" in html
    assert "<select" not in html
    assert '"agent/benedict"' in js
    assert '"agent/benedict-paralegal"' in js
    assert 'user: "beth"' in js
    assert 'user: "paralegal"' in js
    assert 'fetch("/v1/chat/completions"' in js
    assert "localStorage" in js
    assert "readAsDataURL" in js


def test_beth_portal_compose_serves_one_local_port_and_proxies_to_freyja() -> None:
    compose = yaml.safe_load((PORTAL_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["beth-portal"]

    assert service["ports"] == ["${BETH_PORTAL_BIND_IP:-0.0.0.0}:${BETH_PORTAL_HOST_PORT:-8091}:8091"]
    assert service["environment"]["FREYJA_OPENAI_BASE_URL"] == "${FREYJA_OPENAI_BASE_URL:-http://host.docker.internal:8500/v1}"
    assert "FREYJA_API_KEY=" in (PORTAL_ROOT / ".env.example").read_text(encoding="utf-8")


def test_beth_portal_proxy_forwards_v1_with_server_side_auth(monkeypatch) -> None:
    server = load_server_module(monkeypatch)
    payload = {"model": "agent/benedict", "user": "beth", "messages": [{"role": "user", "content": "hello"}]}
    sent = {}
    captured = {}

    class FakeResponse:
        status = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    handler = server.Handler.__new__(server.Handler)
    handler.command = "POST"
    handler.path = "/v1/chat/completions"
    handler.headers = Message()
    body = json.dumps(payload).encode("utf-8")
    handler.headers["content-length"] = str(len(body))
    handler.headers["content-type"] = "application/json"
    handler.rfile = io.BytesIO(body)
    handler._send = lambda status, headers, body: sent.update(
        {"status": status, "headers": headers, "body": json.loads(body.decode("utf-8"))}
    )
    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    handler._proxy()

    assert captured["url"] == "http://freyja.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["body"] == payload
    assert captured["timeout"] == 180
    assert sent["status"] == 200
    assert sent["body"] == {"ok": True}
