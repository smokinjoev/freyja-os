from __future__ import annotations

import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER = REPO_ROOT / "deploy" / "compose" / "freyja-gateway-remote" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("gateway_remote", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_token_generation_stores_hashes_only(tmp_path, monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "TOKEN_FILE", tmp_path / "tokens.json")

    issued = server.ensure_tokens()

    assert sorted(issued) == ["beth", "jenna", "joe", "liam"]
    stored = json.loads((tmp_path / "tokens.json").read_text(encoding="utf-8"))
    assert all("sha256" in record for record in stored.values())
    for raw in issued.values():
        assert raw not in str(stored)


def test_append_trace_omits_prompt_and_credentials(tmp_path, monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "TRACE_FILE", tmp_path / "trace.jsonl")

    server.append_trace(
        {
            "request_id": "req-1",
            "person": "joe",
            "agent": "freyja",
            "prompt": "secret prompt",
            "credential": "secret-token",
            "trace_id": "trace-1",
            "egress_state": "local-only",
        }
    )

    body = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "secret prompt" not in body
    assert "secret-token" not in body
    assert "trace-1" in body


def test_chat_proxy_forwards_gateway_model_without_logging_prompt(tmp_path, monkeypatch) -> None:
    server = load_server()
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "TRACE_FILE", tmp_path / "trace.jsonl")
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "done"}}],
                    "freyja": {
                        "trace_id": "trace-2",
                        "route": "general",
                        "endpoint": "vulcan-nexus-strong",
                        "provider": "nexus",
                        "egress_state": "local-only",
                    },
                }
            ).encode()

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    with patch.object(urllib.request, "urlopen", fake_urlopen):
        request = urllib.request.Request(
            "http://test/api/chat",
            data=json.dumps({"model": "agent/freyja", "messages": [{"role": "user", "content": "hello"}]}).encode(),
        )
        response = fake_urlopen(request)
        assert response.status == 200

    assert captured["body"]["model"] == "agent/freyja"
