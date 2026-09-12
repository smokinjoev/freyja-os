#!/usr/bin/env python3
"""Smoke Open WebUI-visible Freyja 5 agent model endpoints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


AGENT_MODEL_IDS = [
    "agent/freyja",
    "agent/cloyd-gibbler",
    "agent/freyja-coder",
    "agent/benedict",
    "agent/benedict-paralegal",
    "agent/agent-47",
    "agent/jennacide",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke Freyja 5 agent models through the Open WebUI proxy.")
    parser.add_argument("--base-url", default=os.environ.get("OPEN_WEBUI_PROXY_BASE_URL", "http://127.0.0.1:8080/v1"))
    parser.add_argument("--token", default=os.environ.get("OPEN_WEBUI_PROXY_API_KEY", ""))
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path)
    return parser


def _request_json(
    method: str,
    url: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    if not raw:
        return status, {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return status, {"raw_response": raw.decode("utf-8", errors="replace")[:500]}
    return status, decoded if isinstance(decoded, dict) else {"response": decoded}


def _chat_payload(model: str, prompt: str, *, user: str) -> dict[str, Any]:
    return {
        "model": model,
        "user": user,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }


def _freyja_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("freyja") if isinstance(payload.get("freyja"), dict) else {}
    trace = metadata.get("trace") if isinstance(metadata.get("trace"), dict) else {}
    return {
        "model": payload.get("model"),
        "agent": metadata.get("agent"),
        "agent_model": metadata.get("agent_model"),
        "route": metadata.get("route"),
        "endpoint": metadata.get("endpoint"),
        "provider": metadata.get("provider"),
        "egress_state": metadata.get("egress_state"),
        "trace_channel": trace.get("channel"),
        "trace_user": trace.get("resolved_user"),
        "inference_status": trace.get("inference_status"),
    }


def run_smoke(*, base_url: str, token: str, timeout: float) -> dict[str, Any]:
    base = base_url.rstrip("/")
    checks: list[dict[str, Any]] = []
    status, models_payload = _request_json("GET", f"{base}/models", token=token, timeout=timeout)
    models = models_payload.get("data") if isinstance(models_payload.get("data"), list) else []
    model_ids = [str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")]
    missing = [model_id for model_id in AGENT_MODEL_IDS if model_id not in model_ids]
    checks.append(
        {
            "name": "models",
            "ok": 200 <= status < 300 and not missing,
            "status_code": status,
            "agent_models": [model_id for model_id in model_ids if model_id.startswith("agent/")],
            "missing_agent_models": missing,
        }
    )
    for name, model_id, user in (
        ("chat_freyja", "agent/freyja", "joe"),
        ("chat_cloyd", "agent/cloyd-gibbler", "joe"),
    ):
        status, payload = _request_json(
            "POST",
            f"{base}/chat/completions",
            token=token,
            timeout=timeout,
            payload=_chat_payload(model_id, f"Smoke check {model_id}; answer briefly.", user=user),
        )
        checks.append({"name": name, "ok": 200 <= status < 300, "status_code": status, **_freyja_metadata(payload)})
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-open-webui-agent-smoke",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "token_configured": bool(token),
        "passed": all(check.get("ok") is True for check in checks),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke(base_url=args.base_url, token=args.token, timeout=args.timeout)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
