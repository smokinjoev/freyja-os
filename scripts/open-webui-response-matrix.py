#!/usr/bin/env python3
"""Non-destructive response matrix for Open WebUI/Vulcan/Nexus diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_MODELS = ("qwen2.5:7b", "qwen2.5vl:72b", "qwen2.5:32b-instruct")


@dataclass(frozen=True)
class PromptCase:
    name: str
    content: str
    max_tokens: int


PROMPTS = (
    PromptCase(
        "deterministic",
        "Reply with exactly this sentence and nothing else: The diagnostic path is clean.",
        64,
    ),
    PromptCase(
        "writing",
        "Write two clear sentences about why trains have timetables.",
        160,
    ),
    PromptCase(
        "structured",
        'Return only compact JSON with keys "title" and "summary". '
        'The title must be "Trains and Rainbows Paper" and the summary must be one sentence.',
        160,
    ),
)

IRRELEVANT_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location.",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-base-url", default=os.environ.get("OLLAMA_BASE_URL", "http://100.94.80.21:11434"))
    parser.add_argument("--openai-base-url", default=os.environ.get("VULCAN_OPENAI_BASE_URL", "http://100.94.80.21:8088/v1"))
    parser.add_argument("--nexus-base-url", default=os.environ.get("NEXUS_BASE_URL", "http://100.94.80.21:3939"))
    parser.add_argument("--nexus-api-key", default=os.environ.get("NEXUS_API_KEY", ""))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--include-tools", action="store_true", help="Also send irrelevant tool-schema checks.")
    parser.add_argument("--include-stream", action="store_true", help="Also test OpenAI-compatible streaming.")
    parser.add_argument("--include-nexus", action="store_true", help="Run Nexus checks when a token is configured.")
    parser.add_argument("--unload-tested", action="store_true", help="Unload tested Ollama model names at the end.")
    parser.add_argument("--output", type=Path, default=Path("logs/open-webui-diagnostics/response-matrix-latest.json"))
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "report_type": "open-webui-response-matrix",
        "timestamp": datetime.now(UTC).isoformat(),
        "ollama_base_url": args.ollama_base_url.rstrip("/"),
        "openai_base_url": args.openai_base_url.rstrip("/"),
        "nexus_base_url": args.nexus_base_url.rstrip("/"),
        "nexus_token_configured": bool(args.nexus_api_key),
        "models": args.models,
        "prompts": [case.__dict__ for case in PROMPTS],
        "checks": [],
        "final_ollama_ps": None,
    }

    ollama_base = args.ollama_base_url.rstrip("/")
    openai_base = args.openai_base_url.rstrip("/")
    nexus_base = args.nexus_base_url.rstrip("/")

    report["ollama_version"] = request_json("GET", f"{ollama_base}/api/version", timeout=8)
    report["ollama_tags"] = request_json("GET", f"{ollama_base}/api/tags", timeout=20)
    report["openai_models"] = request_json("GET", f"{openai_base}/models", timeout=20)
    report["nexus_health"] = request_json("GET", f"{nexus_base}/health", timeout=8)
    report["nexus_version"] = request_json("GET", f"{nexus_base}/version", timeout=8)

    for model in args.models:
        for case in PROMPTS:
            report["checks"].append(run_ollama_chat(ollama_base, model, case))
            report["checks"].append(run_openai_chat(openai_base, model, case, stream=False))
            if args.include_stream:
                report["checks"].append(run_openai_chat(openai_base, model, case, stream=True))
            if args.include_tools:
                report["checks"].append(run_openai_chat(openai_base, model, case, stream=False, tools=True))
            if args.include_nexus and args.nexus_api_key:
                nexus_model = model if model.startswith("vulcan-ollama/") else f"vulcan-ollama/{model}"
                report["checks"].append(
                    run_openai_chat(nexus_base.rstrip("/") + "/v1", nexus_model, case, stream=False, token=args.nexus_api_key)
                )

    if args.unload_tested:
        report["unload"] = [unload_ollama(ollama_base, model) for model in args.models]
    report["final_ollama_ps"] = request_json("GET", f"{ollama_base}/api/ps", timeout=20)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(redact(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(args.output))
    print(summary(report))
    return 0


def run_ollama_chat(base: str, model: str, case: PromptCase) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": case.content}],
        "options": {"temperature": 0, "num_predict": case.max_tokens},
    }
    result = request_json("POST", f"{base}/api/chat", payload=payload, timeout=900)
    body = result.get("body")
    message = body.get("message") if isinstance(body, dict) else None
    return {
        "path": "ollama",
        "model": model,
        "case": case.name,
        "stream": False,
        "tools": False,
        "request": payload,
        "response": result,
        "analysis": analyze_message(message, body.get("done_reason") if isinstance(body, dict) else None),
        "ollama_ps_after": request_json("GET", f"{base}/api/ps", timeout=20),
    }


def run_openai_chat(
    base: str,
    model: str,
    case: PromptCase,
    *,
    stream: bool,
    tools: bool = False,
    token: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "stream": stream,
        "messages": [{"role": "user", "content": case.content}],
        "temperature": 0,
        "max_tokens": case.max_tokens,
    }
    if tools:
        payload["tools"] = [IRRELEVANT_TOOL]
        payload["tool_choice"] = "auto"
    result = request_json("POST", f"{base.rstrip('/')}/chat/completions", payload=payload, timeout=900, token=token)
    body = result.get("body")
    message = None
    finish_reason = None
    if stream:
        message, finish_reason = parse_openai_stream(body)
    elif isinstance(body, dict):
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message") or first.get("delta")
                finish_reason = first.get("finish_reason")
    return {
        "path": "openai",
        "model": model,
        "case": case.name,
        "stream": stream,
        "tools": tools,
        "request": payload,
        "response": result,
        "analysis": analyze_message(message, finish_reason),
    }


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
    token: str = "",
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    started = time.monotonic()
    first_byte_ms = None
    body = b""
    status = None
    response_headers: dict[str, str] = {}
    error_type = None
    error = None
    try:
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            response_headers = dict(response.headers.items())
            first = response.read(1)
            first_byte_ms = int((time.monotonic() - started) * 1000)
            body = first + response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_headers = dict(exc.headers.items())
        body = exc.read(500_000)
        error_type = "HTTPError"
    except Exception as exc:  # noqa: BLE001 - diagnostics need error class.
        error_type = type(exc).__name__
        error = str(exc)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    parsed: Any
    text_body = body.decode("utf-8", errors="replace") if body else ""
    if "text/event-stream" in response_headers.get("Content-Type", response_headers.get("content-type", "")):
        parsed = {"event_stream": parse_sse_events(text_body), "bytes": len(body)}
    else:
        try:
            parsed = json.loads(text_body) if body else None
        except Exception:
            parsed = {"non_json_body_preview": text_body[:400], "bytes": len(body)}

    return {
        "ok": isinstance(status, int) and 200 <= status < 300,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "first_byte_ms": first_byte_ms,
        "headers": safe_headers(response_headers),
        "body": parsed,
        "error_type": error_type,
        "error": error,
    }


def analyze_message(message: Any, finish_reason: Any) -> dict[str, Any]:
    content = ""
    reasoning = ""
    tool_calls = None
    if isinstance(message, dict):
        content = str(message.get("content") or "")
        reasoning = str(message.get("reasoning") or message.get("thinking") or "")
        tool_calls = message.get("tool_calls")
    return {
        "finish_reason": finish_reason,
        "content_chars": len(content),
        "reasoning_chars": len(reasoning),
        "content_preview": content[:240],
        "reasoning_preview": reasoning[:240],
        "has_tool_calls": bool(tool_calls),
        "looks_schema_like": looks_schema_like(content) or looks_schema_like(reasoning),
        "empty_content_with_reasoning": not content.strip() and bool(reasoning.strip()),
    }


def parse_sse_events(text: str) -> list[Any]:
    events: list[Any] = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            try:
                events.append(json.loads(data))
            except json.JSONDecodeError:
                events.append({"raw": data[:400]})
    return events


def parse_openai_stream(body: Any) -> tuple[dict[str, Any], Any]:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason = None
    tool_calls: list[Any] = []
    if not isinstance(body, dict):
        return {"content": "", "reasoning": ""}, finish_reason
    events = body.get("event_stream")
    if not isinstance(events, list):
        return {"content": "", "reasoning": ""}, finish_reason
    for event in events:
        if not isinstance(event, dict):
            continue
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        first = choices[0]
        if not isinstance(first, dict):
            continue
        if first.get("finish_reason") is not None:
            finish_reason = first.get("finish_reason")
        delta = first.get("delta")
        if not isinstance(delta, dict):
            continue
        content = delta.get("content")
        if isinstance(content, str):
            content_parts.append(content)
        reasoning = delta.get("reasoning") or delta.get("thinking")
        if isinstance(reasoning, str):
            reasoning_parts.append(reasoning)
        if delta.get("tool_calls"):
            tool_calls.append(delta["tool_calls"])
    return {
        "content": "".join(content_parts),
        "reasoning": "".join(reasoning_parts),
        "tool_calls": tool_calls,
    }, finish_reason


def looks_schema_like(text: str) -> bool:
    lowered = text.lower()
    needles = ("tool_calls", "parameters", "json_schema", "<tool", "</tool", "properties", "required")
    return sum(needle in lowered for needle in needles) >= 2


def unload_ollama(base: str, model: str) -> dict[str, Any]:
    return request_json(
        "POST",
        f"{base}/api/generate",
        payload={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
        timeout=180,
    )


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    safe = {}
    for key, value in headers.items():
        lowered = key.lower()
        if any(word in lowered for word in ("authorization", "token", "key", "secret", "cookie")):
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in {"max_tokens", "completion_tokens", "prompt_tokens", "total_tokens"}:
                result[key] = redact(item)
            elif any(word in lowered for word in ("authorization", "api_key", "secret", "password")) or lowered.endswith(
                "_token"
            ):
                result[key] = "<redacted>" if item else ""
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def summary(report: dict[str, Any]) -> str:
    checks = report.get("checks", [])
    lines = [f"checks={len(checks)}"]
    for check in checks:
        analysis = check.get("analysis", {})
        response = check.get("response", {})
        lines.append(
            "{path} model={model} case={case} stream={stream} tools={tools} "
            "status={status} finish={finish} content={content} reasoning={reasoning} "
            "schema_like={schema_like} empty_content_with_reasoning={empty_reasoning}".format(
                path=check.get("path"),
                model=check.get("model"),
                case=check.get("case"),
                stream=check.get("stream"),
                tools=check.get("tools"),
                status=response.get("status"),
                finish=analysis.get("finish_reason"),
                content=analysis.get("content_chars"),
                reasoning=analysis.get("reasoning_chars"),
                schema_like=analysis.get("looks_schema_like"),
                empty_reasoning=analysis.get("empty_content_with_reasoning"),
            )
        )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
