#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PRIMARY_BASE_URL = os.environ.get("PRIMARY_BASE_URL", "http://100.94.80.21:8088/v1").rstrip("/")
PRIMARY_API_KEY = os.environ.get("PRIMARY_API_KEY", "not-needed")
PRIMARY_OLLAMA_BASE_URL = os.environ.get("PRIMARY_OLLAMA_BASE_URL", "http://100.94.80.21:11434").rstrip("/")
FALLBACK_BASE_URL = os.environ.get("FALLBACK_BASE_URL", "http://100.115.228.56:11434/v1").rstrip("/")
FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", "not-needed")
FREYJA5_BASE_URL = os.environ.get("FREYJA5_BASE_URL", "http://host.docker.internal:8500/v1").rstrip("/")
FREYJA5_API_KEY = os.environ.get("FREYJA5_API_KEY", "not-needed")
APPROVED_MODELS = {
    model.strip()
    for model in os.environ.get(
        "APPROVED_MODELS",
        "qwen2.5:32b-instruct,"
        "qwen2.5vl:72b,"
        "qwen3:30b-a3b,"
        "qwen3-coder-next:q4_K_M,"
        "gpt-oss:20b,"
        "gpt-oss-freyja:20b-analysis-prefill,"
        "gpt-oss:120b",
    ).split(",")
    if model.strip()
}
FALLBACK_MODELS = {
    model.strip()
    for model in os.environ.get("FALLBACK_MODELS", "qwen2.5:7b").split(",")
    if model.strip()
}
FREYJA5_AGENT_MODELS = {
    model.strip()
    for model in os.environ.get(
        "FREYJA5_AGENT_MODELS",
        "agent/freyja,"
        "agent/cloyd-gibbler,"
        "agent/benedict,"
        "agent/benedict-paralegal,"
        "agent/agent-47,"
        "agent/jennacide",
    ).split(",")
    if model.strip()
}
PROBE_MODELS = {
    model.strip()
    for model in os.environ.get("PROBE_MODELS", "gpt-oss:120b").split(",")
    if model.strip()
}
MODEL_LIST_TIMEOUT_SECONDS = float(os.environ.get("MODEL_LIST_TIMEOUT_SECONDS", "5"))
PROBE_TIMEOUT_SECONDS = float(os.environ.get("PROBE_TIMEOUT_SECONDS", "45"))
GARBAGE_GUARD_MODELS = {
    model.strip()
    for model in os.environ.get("GARBAGE_GUARD_MODELS", "gpt-oss:120b,gpt-oss-freyja:20b-analysis-prefill").split(",")
    if model.strip()
}
GARBAGE_GUARD_MIN_TOKENS = int(os.environ.get("GARBAGE_GUARD_MIN_TOKENS", "512"))
VISION_MODELS = {
    model.strip()
    for model in os.environ.get("VISION_MODELS", "qwen2.5vl:72b").split(",")
    if model.strip()
}
TEXT_MODEL = os.environ.get("TEXT_MODEL", "qwen2.5vl:72b").strip()
TOOL_MODEL = os.environ.get("TOOL_MODEL", "qwen2.5:32b-instruct").strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/v1/models":
            self._proxy_models()
            return
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def _proxy_models(self) -> None:
        models: dict[str, dict] = {}
        for base_url, api_key, allowed_models in (
            (PRIMARY_BASE_URL, PRIMARY_API_KEY, APPROVED_MODELS),
            (FALLBACK_BASE_URL, FALLBACK_API_KEY, FALLBACK_MODELS),
            (FREYJA5_BASE_URL, FREYJA5_API_KEY, FREYJA5_AGENT_MODELS),
        ):
            status, headers, body = self._upstream(
                base_url, api_key, "GET", "/models", b"", timeout=MODEL_LIST_TIMEOUT_SECONDS
            )
            if status >= 400:
                continue
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            for model in payload.get("data", []):
                if not isinstance(model, dict):
                    continue
                model_id = model.get("id")
                if model_id in allowed_models:
                    models.setdefault(model_id, model)
        if models:
            payload = {"object": "list", "data": [models[model_id] for model_id in sorted(models)]}
            self._send(200, {"content-type": "application/json"}, json.dumps(payload).encode("utf-8"))
            return
        self._send(
            503,
            {"content-type": "application/json"},
            json.dumps({"error": "no approved models available"}).encode("utf-8"),
        )

    def _proxy(self) -> None:
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        payload = self._request_payload(body) if self.command == "POST" else None
        requested_model = self._requested_model_from_payload(payload)
        if self.command == "POST" and self.path.split("?", 1)[0] == "/v1/chat/completions":
            if requested_model not in APPROVED_MODELS and requested_model not in FALLBACK_MODELS and requested_model not in FREYJA5_AGENT_MODELS:
                self._send(
                    400,
                    {"content-type": "application/json"},
                    json.dumps({"error": f"model is not approved for Open WebUI: {requested_model}"}).encode("utf-8"),
                )
                return
            if requested_model in FREYJA5_AGENT_MODELS:
                status, headers, response_body = self._upstream(
                    FREYJA5_BASE_URL,
                    FREYJA5_API_KEY,
                    self.command,
                    self.path.removeprefix("/v1"),
                    body,
                )
                self._send(status, headers, response_body)
                return
            routed_model = self._routed_chat_model(payload)
            if routed_model != requested_model:
                payload["model"] = routed_model
                body = json.dumps(payload).encode("utf-8")
                requested_model = routed_model
            guard_error = self._large_model_guard_error(payload, requested_model)
            if guard_error:
                self._send(
                    400,
                    {"content-type": "application/json"},
                    json.dumps({"error": guard_error}).encode("utf-8"),
                )
                return
            self._unload_other_primary_models(requested_model)
            if requested_model in PROBE_MODELS and self._primary_model_loaded(requested_model):
                if not self._probe_primary_model(requested_model):
                    self._unload_primary_model(requested_model)
                    self._send(
                        503,
                        {"content-type": "application/json"},
                        json.dumps(
                            {
                                "error": (
                                    f"model failed readiness probe and was unloaded: {requested_model}; "
                                    "retry the request to reload it"
                                )
                            }
                        ).encode("utf-8"),
                    )
                    return
        for base_url, api_key, allowed_models in (
            (PRIMARY_BASE_URL, PRIMARY_API_KEY, APPROVED_MODELS),
            (FALLBACK_BASE_URL, FALLBACK_API_KEY, FALLBACK_MODELS),
        ):
            if requested_model and requested_model not in allowed_models:
                continue
            if requested_model and not self._model_available(base_url, api_key, requested_model):
                continue
            status, headers, response_body = self._upstream(base_url, api_key, self.command, self.path.removeprefix("/v1"), body)
            if self.command == "POST" and self.path.split("?", 1)[0] == "/v1/chat/completions" and status == 200:
                response_body = self._adapt_chat_completion_response(response_body)
                guard_error = self._large_model_response_guard_error(response_body, requested_model)
                if guard_error:
                    if requested_model in APPROVED_MODELS:
                        self._unload_primary_model(requested_model)
                    self._send(
                        502,
                        {"content-type": "application/json"},
                        json.dumps({"error": guard_error}).encode("utf-8"),
                    )
                    return
            if status < 500:
                self._send(status, headers, response_body)
                return
        self._send(
            503,
            {"content-type": "application/json"},
            json.dumps({"error": f"no available upstream for model: {requested_model}"}).encode("utf-8"),
        )

    def _request_payload(self, body: bytes) -> dict | None:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _requested_model_from_payload(self, payload: dict | None) -> str | None:
        if payload is None:
            return None
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def _routed_chat_model(self, payload: dict | None) -> str | None:
        requested_model = self._requested_model_from_payload(payload)
        if payload is None:
            return requested_model
        if self._has_tools(payload):
            return TOOL_MODEL
        if self._has_vision_input(payload):
            return next(iter(VISION_MODELS), requested_model)
        return TEXT_MODEL if requested_model in VISION_MODELS else requested_model

    def _large_model_guard_error(self, payload: dict | None, requested_model: str | None) -> str | None:
        if payload is None or requested_model not in GARBAGE_GUARD_MODELS:
            return None
        if payload.get("stream") is True:
            return f"streaming is disabled for guarded large model: {requested_model}"
        max_tokens = payload.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens < GARBAGE_GUARD_MIN_TOKENS:
            return (
                f"max_tokens for guarded large model {requested_model} must be at least "
                f"{GARBAGE_GUARD_MIN_TOKENS}"
            )
        return None

    def _has_tools(self, payload: dict) -> bool:
        tools = payload.get("tools")
        if isinstance(tools, list) and tools:
            return True
        tool_choice = payload.get("tool_choice")
        return tool_choice not in (None, "none")

    def _has_vision_input(self, payload: dict) -> bool:
        return self._contains_any_key(payload.get("messages", []), {"image_url", "input_image", "file", "file_url", "mime_type"})

    def _contains_any_key(self, value, keys: set[str]) -> bool:
        if isinstance(value, dict):
            if any(key in value for key in keys):
                if value.get("mime_type") not in (None, "application/pdf"):
                    return True
                return True
            return any(self._contains_any_key(item, keys) for item in value.values())
        if isinstance(value, list):
            return any(self._contains_any_key(item, keys) for item in value)
        return False

    def _adapt_chat_completion_response(self, body: bytes) -> bytes:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return body
        if not isinstance(payload, dict):
            return body
        changed = False
        choices = payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if not isinstance(message, dict):
                    continue
                if choice.get("finish_reason") == "length":
                    continue
                content = message.get("content")
                reasoning = message.get("reasoning")
                if (content is None or content == "") and isinstance(reasoning, str) and reasoning.strip():
                    message["content"] = reasoning.strip()
                    changed = True
        if changed:
            metadata = payload.setdefault("freyja_adapter", {})
            if isinstance(metadata, dict):
                metadata["reasoning_promoted_to_content"] = True
            return json.dumps(payload).encode("utf-8")
        return body

    def _large_model_response_guard_error(self, body: bytes, requested_model: str | None) -> str | None:
        if requested_model not in GARBAGE_GUARD_MODELS:
            return None
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return f"guarded large model returned malformed JSON: {requested_model}"
        choices = payload.get("choices")
        if not isinstance(choices, list):
            return f"guarded large model returned malformed choices: {requested_model}"
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if choice.get("finish_reason") == "length" and not content:
                return f"guarded large model exhausted output budget before visible content: {requested_model}"
            if isinstance(content, str) and self._looks_like_garbage(content):
                return f"guarded large model returned repetitive or malformed content: {requested_model}"
        return None

    def _looks_like_garbage(self, content: str) -> bool:
        if not content:
            return False
        if content.count("\ufffd") >= 3:
            return True
        printable = sum(1 for char in content if char.isprintable() or char in "\n\r\t")
        if len(content) >= 100 and printable / len(content) < 0.98:
            return True
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if len(lines) >= 8 and len(set(lines)) <= 2:
            return True
        return any(char * 80 in content for char in set(content) if not char.isspace())

    def _model_available(self, base_url: str, api_key: str, model_id: str) -> bool:
        status, _, body = self._upstream(base_url, api_key, "GET", "/models", b"", timeout=MODEL_LIST_TIMEOUT_SECONDS)
        if status >= 400:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return any(isinstance(model, dict) and model.get("id") == model_id for model in payload.get("data", []))

    def _unload_other_primary_models(self, requested_model: str | None) -> None:
        if not requested_model:
            return
        try:
            payload = self._primary_loaded_models()
        except (OSError, json.JSONDecodeError):
            return
        for model in payload:
            model_name = model.get("name") or model.get("model")
            if model_name and model_name != requested_model:
                self._unload_primary_model(model_name)

    def _primary_loaded_models(self) -> list[dict]:
        status, _, body = self._ollama("GET", "/api/ps", b"")
        if status >= 400:
            return []
        payload = json.loads(body.decode("utf-8"))
        models = payload.get("models", [])
        return models if isinstance(models, list) else []

    def _primary_model_loaded(self, requested_model: str) -> bool:
        try:
            return any(
                requested_model in {model.get("name"), model.get("model")}
                for model in self._primary_loaded_models()
                if isinstance(model, dict)
            )
        except (OSError, json.JSONDecodeError):
            return False

    def _probe_primary_model(self, requested_model: str) -> bool:
        body = json.dumps(
            {
                "model": requested_model,
                "prompt": "Reply with exactly: ok",
                "stream": False,
                "options": {"num_predict": 4},
            }
        ).encode("utf-8")
        status, _, response_body = self._ollama("POST", "/api/generate", body, timeout=PROBE_TIMEOUT_SECONDS)
        if status >= 400:
            return False
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError:
            return False
        return payload.get("done") is True

    def _unload_primary_model(self, model_name: str) -> None:
        self._ollama(
            "POST",
            "/api/generate",
            json.dumps({"model": model_name, "prompt": "", "stream": False, "keep_alive": 0}).encode("utf-8"),
        )

    def _ollama(self, method: str, path: str, body: bytes, timeout: float = 30) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(
            f"{PRIMARY_OLLAMA_BASE_URL}{path}",
            data=body or None,
            method=method,
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
        except OSError:
            return 599, {}, b""

    def _upstream(
        self, base_url: str, api_key: str, method: str, path: str, body: bytes, timeout: float = 120
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": self.headers.get("content-type", "application/json"),
        }
        for header in (
            "x-open-webui-user-id",
            "x-open-webui-user-name",
            "x-open-webui-user-email",
            "x-open-webui-user-role",
            "x-openwebui-user-id",
            "x-openwebui-user-name",
            "x-openwebui-user-email",
            "x-openwebui-user-role",
        ):
            value = self.headers.get(header)
            if value:
                headers[header] = value
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=body or None,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
        except OSError as exc:
            return (
                599,
                {"content-type": "application/json"},
                json.dumps({"error": f"upstream connection failed: {exc}"}).encode("utf-8"),
            )

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-length", str(len(body)))
        for key, value in headers.items():
            if key.lower() not in {"content-length", "connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
