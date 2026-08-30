#!/usr/bin/env python3
"""Smoke-test a Msty Nexus OpenAI-compatible gateway without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://100.94.80.21:3939"
DEFAULT_MODEL = "@preset/freyja-fast-local"
BAD_MODEL = "@preset/not-a-real-preset"


def _request(
    method: str,
    url: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    started = time.monotonic()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(500_000)
            status = response.status
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read(100_000)
        status = exc.code
        response_headers = dict(exc.headers.items())
    except Exception as exc:  # noqa: BLE001 - smoke report should capture failure class
        return {
            "ok": False,
            "status": None,
            "error_type": type(exc).__name__,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    parsed: Any = None
    if body:
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            parsed = {"non_json_body_bytes": len(body)}
    return {
        "ok": 200 <= status < 300,
        "status": status,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "request_id_present": any(
            key.lower() in {"x-msty-nexus-request-id", "x-request-id", "request-id"}
            for key in response_headers
        ),
        "body": _safe_body(parsed),
    }


def _safe_body(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(secret_word in lowered for secret_word in ("token", "key", "secret", "authorization")):
                safe[key] = "<redacted>"
            elif key in {"choices", "output", "response", "messages"}:
                safe[key] = "<omitted>"
            elif key == "data" and isinstance(item, list):
                safe[key] = [_safe_model(item) for item in item[:50]]
                safe["data_count"] = len(item)
            else:
                safe[key] = _safe_body(item)
        return safe
    if isinstance(value, list):
        return [_safe_body(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 240:
        return value[:240] + "...<truncated>"
    return value


def _safe_model(value: Any) -> Any:
    if not isinstance(value, dict):
        return _safe_body(value)
    return {
        key: value[key]
        for key in ("id", "object", "owned_by")
        if key in value and isinstance(value[key], str)
    }


def _chat_payload(model: str, content: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "max_tokens": 32,
        "temperature": 0,
    }


def run_smoke(base_url: str, token: str, model: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    report = {
        "schema_version": "1.0",
        "report_type": "nexus-smoke",
        "timestamp": datetime.now(UTC).isoformat(),
        "base_url": base,
        "token_configured": bool(token),
        "token_value": "<redacted>" if token else "",
        "model": model,
        "checks": {},
    }
    checks: dict[str, Any] = report["checks"]
    checks["health"] = _request("GET", f"{base}/health", timeout=5.0)
    checks["version"] = _request("GET", f"{base}/version", timeout=5.0)
    checks["models"] = _request("GET", f"{base}/v1/models", token=token, timeout=10.0)
    checks["chat"] = _request(
        "POST",
        f"{base}/v1/chat/completions",
        token=token,
        payload=_chat_payload(model, "Reply exactly: nexus-ok"),
        timeout=60.0,
    )
    checks["bad_token"] = _request("GET", f"{base}/v1/models", token="bad-token", timeout=10.0)
    checks["bad_model"] = _request(
        "POST",
        f"{base}/v1/chat/completions",
        token=token,
        payload=_chat_payload(BAD_MODEL, "test"),
        timeout=20.0,
    )
    report["ready"] = (
        checks["health"].get("ok") is True
        and checks["models"].get("ok") is True
        and checks["chat"].get("ok") is True
        and checks["bad_token"].get("ok") is False
        and checks["bad_model"].get("ok") is False
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Msty Nexus for Freyja.")
    parser.add_argument("--base-url", default=os.environ.get("NEXUS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token", default=os.environ.get("NEXUS_API_KEY", ""))
    parser.add_argument("--model", default=os.environ.get("NEXUS_SMOKE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = run_smoke(args.base_url, args.token, args.model)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
