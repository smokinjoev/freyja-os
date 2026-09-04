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
    proxy_environment = compose["services"]["model-proxy"]["environment"]
    env_example = OPEN_WEBUI_ENV_EXAMPLE.read_text(encoding="utf-8")

    assert environment["OPENAI_API_BASE_URL"] == "${OPENAI_API_BASE_URL:-http://model-proxy:8080/v1}"
    assert environment["DEFAULT_MODELS"] == "${DEFAULT_MODELS:-qwen2.5vl:72b}"
    assert "OPENAI_API_BASE_URL=http://model-proxy:8080/v1" in env_example
    assert "DEFAULT_MODELS=qwen2.5vl:72b" in env_example
    assert "OPEN_WEBUI_FREYJA5_BASE_URL=http://host.docker.internal:8500/v1" in env_example
    assert "OPEN_WEBUI_FREYJA5_AGENT_MODELS=agent/freyja,agent/cloyd-gibbler,agent/benedict,agent/benedict-paralegal,agent/agent-47,agent/jennacide" in env_example
    assert proxy_environment["FREYJA5_BASE_URL"] == "${OPEN_WEBUI_FREYJA5_BASE_URL:-http://host.docker.internal:8500/v1}"
    assert "DEFAULT_MODELS=freyja-5" not in env_example
    assert "qwen2.5:72b" not in proxy_environment["APPROVED_MODELS"]
    assert "qwen3.5:122b-a10b" not in proxy_environment["APPROVED_MODELS"]
    approved_line = next(line for line in env_example.splitlines() if line.startswith("OPEN_WEBUI_APPROVED_MODELS="))
    assert "qwen2.5:72b" not in approved_line
    assert "qwen3.5:122b-a10b" not in approved_line


def test_proxy_model_listing_skips_invalid_upstream_json() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    sent = {}

    responses = iter(
        (
            (200, {"content-type": "application/json"}, b"not-json"),
            (
                200,
                {"content-type": "application/json"},
                json.dumps({"data": [{"id": "qwen2.5:7b"}]}).encode("utf-8"),
            ),
            (599, {"content-type": "application/json"}, b"{}"),
        )
    )
    handler._upstream = lambda *args, **kwargs: next(responses)
    handler._send = lambda status, headers, body: sent.update(
        {"status": status, "headers": headers, "body": json.loads(body.decode("utf-8"))}
    )

    handler._proxy_models()

    assert sent["status"] == 200
    assert sent["body"]["data"] == [{"id": "qwen2.5:7b"}]


def test_proxy_model_listing_uses_bounded_upstream_timeout() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    calls = []
    sent = {}

    def fake_upstream(*args, **kwargs):
        calls.append((*args, kwargs))
        return 599, {}, b""

    handler._upstream = fake_upstream
    handler._send = lambda status, headers, body: sent.update({"status": status})

    handler._proxy_models()

    assert sent["status"] == 503
    assert len(calls) == 3
    assert all(call[-1]["timeout"] == proxy.MODEL_LIST_TIMEOUT_SECONDS for call in calls)


def test_proxy_model_listing_includes_reachable_freyja5_agent_models() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    sent = {}

    responses = iter(
        (
            (200, {"content-type": "application/json"}, json.dumps({"data": [{"id": "qwen2.5:32b-instruct"}]}).encode("utf-8")),
            (200, {"content-type": "application/json"}, json.dumps({"data": [{"id": "qwen2.5:7b"}]}).encode("utf-8")),
            (
                200,
                {"content-type": "application/json"},
                json.dumps(
                    {
                        "data": [
                            {"id": "agent/freyja", "owned_by": "freyja-os"},
                            {"id": "agent/not-approved", "owned_by": "freyja-os"},
                        ]
                    }
                ).encode("utf-8"),
            ),
        )
    )
    handler._upstream = lambda *args, **kwargs: next(responses)
    handler._send = lambda status, headers, body: sent.update(
        {"status": status, "headers": headers, "body": json.loads(body.decode("utf-8"))}
    )

    handler._proxy_models()

    model_ids = {model["id"] for model in sent["body"]["data"]}
    assert sent["status"] == 200
    assert "qwen2.5:32b-instruct" in model_ids
    assert "qwen2.5:7b" in model_ids
    assert "agent/freyja" in model_ids
    assert "agent/not-approved" not in model_ids


def test_proxy_forwards_freyja5_agent_chat_without_unloading_vulcan() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    handler.command = "POST"
    handler.path = "/v1/chat/completions"
    body = json.dumps({"model": "agent/freyja", "messages": [{"role": "user", "content": "hello"}]}).encode("utf-8")
    handler.headers = {"content-type": "application/json", "content-length": str(len(body))}
    handler.rfile = type("Reader", (), {"read": lambda self, length: body})()
    sent = {}
    upstream_calls = []

    def fake_upstream(base_url, api_key, method, path, request_body, timeout=120):
        upstream_calls.append((base_url, api_key, method, path, json.loads(request_body.decode("utf-8"))))
        return 200, {"content-type": "application/json"}, json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")

    handler._upstream = fake_upstream
    handler._unload_other_primary_models = lambda requested_model: (_ for _ in ()).throw(AssertionError("should not unload"))
    handler._send = lambda status, headers, response_body: sent.update(
        {"status": status, "headers": headers, "body": json.loads(response_body.decode("utf-8"))}
    )

    handler._proxy()

    assert sent["status"] == 200
    assert upstream_calls == [(proxy.FREYJA5_BASE_URL, proxy.FREYJA5_API_KEY, "POST", "/chat/completions", {"model": "agent/freyja", "messages": [{"role": "user", "content": "hello"}]})]


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


def test_guarded_large_models_reject_streaming_requests() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "gpt-oss:120b",
        "messages": [{"role": "user", "content": "Write a short answer."}],
        "stream": True,
    }

    assert handler._large_model_guard_error(payload, "gpt-oss:120b") == (
        "streaming is disabled for guarded large model: gpt-oss:120b"
    )


def test_guarded_large_models_reject_tiny_output_budgets() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "gpt-oss:120b",
        "messages": [{"role": "user", "content": "Write a short answer."}],
        "stream": False,
        "max_tokens": 32,
    }

    assert handler._large_model_guard_error(payload, "gpt-oss:120b") == (
        "max_tokens for guarded large model gpt-oss:120b must be at least 512"
    )


def test_guarded_large_models_allow_plain_non_streaming_requests_without_tiny_budget() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    payload = {
        "model": "gpt-oss:120b",
        "messages": [{"role": "user", "content": "Write a short answer."}],
        "stream": False,
        "max_tokens": 512,
    }

    assert handler._large_model_guard_error(payload, "gpt-oss:120b") is None


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


def test_promotes_reasoning_to_content_when_upstream_content_is_empty() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "Visible answer ended up in the reasoning field.",
                    }
                }
            ]
        }
    ).encode("utf-8")

    adapted = json.loads(handler._adapt_chat_completion_response(body).decode("utf-8"))

    assert adapted["choices"][0]["message"]["content"] == "Visible answer ended up in the reasoning field."
    assert adapted["choices"][0]["message"]["reasoning"] == "Visible answer ended up in the reasoning field."
    assert adapted["freyja_adapter"]["reasoning_promoted_to_content"] is True


def test_does_not_promote_truncated_reasoning_to_content() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "Truncated reasoning should not become the answer.",
                    },
                }
            ]
        }
    ).encode("utf-8")

    adapted = json.loads(handler._adapt_chat_completion_response(body).decode("utf-8"))

    assert adapted["choices"][0]["message"]["content"] == ""
    assert "freyja_adapter" not in adapted


def test_keeps_existing_content_when_reasoning_is_also_present() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Final answer.",
                        "reasoning": "Internal reasoning.",
                    }
                }
            ]
        }
    ).encode("utf-8")

    adapted = json.loads(handler._adapt_chat_completion_response(body).decode("utf-8"))

    assert adapted["choices"][0]["message"]["content"] == "Final answer."
    assert "freyja_adapter" not in adapted


def test_guarded_large_models_block_truncated_empty_visible_content() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "Spent the whole budget in hidden reasoning.",
                    },
                }
            ]
        }
    ).encode("utf-8")

    assert handler._large_model_response_guard_error(body, "gpt-oss:120b") == (
        "guarded large model exhausted output budget before visible content: gpt-oss:120b"
    )


def test_guarded_large_models_block_repetitive_visible_content() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    },
                }
            ]
        }
    ).encode("utf-8")

    assert handler._large_model_response_guard_error(body, "gpt-oss:120b") == (
        "guarded large model returned repetitive or malformed content: gpt-oss:120b"
    )


def test_guarded_large_models_allow_clean_visible_content() -> None:
    proxy = load_proxy_module()
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "The diagnostic path is clean."},
                }
            ]
        }
    ).encode("utf-8")

    assert handler._large_model_response_guard_error(body, "gpt-oss:120b") is None


def test_keeps_qwen35_out_of_default_approved_catalog() -> None:
    proxy = load_proxy_module()

    assert "qwen3.5:122b-a10b" not in proxy.APPROVED_MODELS
