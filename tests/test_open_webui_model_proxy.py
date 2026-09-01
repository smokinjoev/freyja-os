from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
OPEN_WEBUI_COMPOSE = REPO_ROOT / "deploy" / "compose" / "open-webui" / "compose.yaml"
OPEN_WEBUI_ENV_EXAMPLE = REPO_ROOT / "deploy" / "compose" / "open-webui" / ".env.example"


def load_proxy_module():
    path = REPO_ROOT / "deploy/compose/open-webui/model-proxy.py"
    spec = importlib.util.spec_from_file_location("open_webui_model_proxy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_webui_defaults_stay_on_model_proxy_until_freyja5_cutover() -> None:
    compose = yaml.safe_load(OPEN_WEBUI_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["open-webui"]["environment"]
    env_example = OPEN_WEBUI_ENV_EXAMPLE.read_text(encoding="utf-8")

    assert environment["OPENAI_API_BASE_URL"] == "${OPENAI_API_BASE_URL:-http://model-proxy:8080/v1}"
    assert environment["DEFAULT_MODELS"] == "${DEFAULT_MODELS:-qwen2.5vl:72b}"
    assert "OPENAI_API_BASE_URL=http://model-proxy:8080/v1" in env_example
    assert "DEFAULT_MODELS=qwen2.5vl:72b" in env_example
    assert "DEFAULT_MODELS=freyja-5" not in env_example


def test_probe_failure_unloads_loaded_primary_model() -> None:
    proxy = load_proxy_module()
    calls: list[tuple[str, str, dict, float]] = []

    def fake_ollama(method: str, path: str, body: bytes, timeout: float = 30):
        payload = json.loads(body.decode("utf-8")) if body else {}
        calls.append((method, path, payload, timeout))
        if path == "/api/ps":
            return 200, {}, json.dumps({"models": [{"name": "gpt-oss:120b"}]}).encode("utf-8")
        if path == "/api/generate" and payload.get("keep_alive") == 0:
            return 200, {}, json.dumps({"done": True, "done_reason": "unload"}).encode("utf-8")
        return 599, {}, b""

    handler = proxy.Handler.__new__(proxy.Handler)
    handler._ollama = fake_ollama

    assert handler._primary_model_loaded("gpt-oss:120b") is True
    assert handler._probe_primary_model("gpt-oss:120b") is False
    handler._unload_primary_model("gpt-oss:120b")

    assert ("POST", "/api/generate", {"model": "gpt-oss:120b", "prompt": "", "stream": False, "keep_alive": 0}, 30) in calls


def test_probe_success_accepts_completed_generation() -> None:
    proxy = load_proxy_module()

    def fake_ollama(method: str, path: str, body: bytes, timeout: float = 30):
        assert method == "POST"
        assert path == "/api/generate"
        assert timeout == proxy.PROBE_TIMEOUT_SECONDS
        return 200, {}, json.dumps({"done": True, "response": "ok"}).encode("utf-8")

    handler = proxy.Handler.__new__(proxy.Handler)
    handler._ollama = fake_ollama

    assert handler._probe_primary_model("gpt-oss:120b") is True


def test_routes_tool_payload_away_from_vision_model() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "qwen2.5vl:72b",
        "messages": [{"role": "user", "content": "What time is it?"}],
        "tools": [{"type": "function", "function": {"name": "current_time"}}],
    }

    assert handler._routed_chat_model(payload) == "qwen2.5:32b-instruct"


def test_keeps_plain_text_payload_on_vision_model() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "qwen2.5vl:72b",
        "messages": [{"role": "user", "content": "Write a short greeting."}],
    }

    assert handler._routed_chat_model(payload) == "qwen2.5vl:72b"


def test_routes_image_payload_to_vision_model() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "qwen2.5:32b-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            }
        ],
    }

    assert handler._routed_chat_model(payload) == "qwen2.5vl:72b"


def test_routes_pdf_payload_to_vision_model() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "qwen2.5:32b-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Summarize this PDF."},
                    {"type": "file", "mime_type": "application/pdf", "file": {"file_id": "file-1"}},
                ],
            }
        ],
    }

    assert handler._routed_chat_model(payload) == "qwen2.5vl:72b"
