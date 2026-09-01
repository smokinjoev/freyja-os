#!/usr/bin/env python3
"""Read-only Freyja 5 side-by-side gateway smoke checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only Freyja 5 gateway smoke checks.")
    parser.add_argument("--base-url", default=os.environ.get("FREYJA5_BASE_URL", "http://127.0.0.1:8500"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-media", action="store_true", help="Skip inline image/PDF WebGUI media checks.")
    return parser


def _request_json(
    method: str,
    url: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
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


def _chat_payload(content: Any, *, user: str = "joe") -> dict[str, Any]:
    return {
        "model": "freyja-5",
        "user": user,
        "stream": False,
        "messages": [{"role": "user", "content": content}],
    }


def _freyja_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("freyja") if isinstance(payload.get("freyja"), dict) else {}
    trace = metadata.get("trace") if isinstance(metadata.get("trace"), dict) else {}
    return {
        "trace_id": metadata.get("trace_id"),
        "agent": metadata.get("agent"),
        "route": metadata.get("route"),
        "endpoint": metadata.get("endpoint"),
        "provider": metadata.get("provider"),
        "egress_state": metadata.get("egress_state"),
        "attachment_count": metadata.get("attachment_count"),
        "trace_route": trace.get("requested_route"),
        "trace_channel": trace.get("channel"),
        "trace_user": trace.get("resolved_user"),
        "inference_status": trace.get("inference_status"),
    }


def _check(
    name: str,
    method: str,
    url: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    try:
        status, response_payload = _request_json(method, url, token=token, payload=payload, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - smoke output should keep moving across failed checks
        return {"name": name, "ok": False, "error": type(exc).__name__}
    result: dict[str, Any] = {"name": name, "ok": 200 <= status < 300, "status_code": status}
    if name == "readiness":
        result["readiness_ok"] = response_payload.get("ok")
        result["version"] = response_payload.get("version")
        result["openai_model"] = response_payload.get("openai_model")
        mcp = response_payload.get("mcp") if isinstance(response_payload.get("mcp"), dict) else {}
        webgui = response_payload.get("webgui") if isinstance(response_payload.get("webgui"), dict) else {}
        certification = (
            response_payload.get("certification")
            if isinstance(response_payload.get("certification"), dict)
            else {}
        )
        mcp_servers = mcp.get("servers") if isinstance(mcp.get("servers"), list) else []
        targets = certification.get("targets") if isinstance(certification.get("targets"), list) else []
        result["mcp_hosts"] = [str(host) for host in mcp.get("hosts") or []]
        result["mcp_server_ids"] = [
            str(server.get("id"))
            for server in mcp_servers
            if isinstance(server, dict) and server.get("id")
        ]
        result["certification_targets"] = [
            str(target.get("target"))
            for target in targets
            if isinstance(target, dict) and target.get("target")
        ]
        result["webgui_default_model"] = webgui.get("default_model_preserved")
        result["webgui_freyja5_opt_in"] = webgui.get("freyja5_opt_in")
    elif name == "models":
        models = response_payload.get("data") if isinstance(response_payload.get("data"), list) else []
        result["models"] = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
    elif name.startswith("chat_"):
        result.update(_freyja_metadata(response_payload))
    return result


def run_smoke(*, base_url: str, token: str, timeout: float, skip_media: bool = False) -> dict[str, Any]:
    base = base_url.rstrip("/")
    checks = [
        _check("health", "GET", f"{base}/health", timeout=timeout),
        _check("readiness", "GET", f"{base}/freyja5/readiness", token=token, timeout=timeout),
        _check("models", "GET", f"{base}/v1/models", token=token, timeout=timeout),
        _check(
            "chat_text",
            "POST",
            f"{base}/v1/chat/completions",
            token=token,
            timeout=timeout,
            payload=_chat_payload("Joe asks Freyja to summarize the architecture status."),
        ),
    ]
    if not skip_media:
        checks.extend(
            [
                _check(
                    "chat_image",
                    "POST",
                    f"{base}/v1/chat/completions",
                    token=token,
                    timeout=timeout,
                    payload=_chat_payload(
                        [
                            {"type": "text", "text": "What useful text or objects are visible?"},
                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmFrZQ=="}},
                        ]
                    ),
                ),
                _check(
                    "chat_pdf",
                    "POST",
                    f"{base}/v1/chat/completions",
                    token=token,
                    timeout=timeout,
                    payload=_chat_payload(
                        [
                            {"type": "text", "text": "Summarize this PDF."},
                            {
                                "type": "file",
                                "file": {"filename": "brief.pdf", "file_data": "data:application/pdf;base64,JVBERi0xLjQK"},
                            },
                        ]
                    ),
                ),
            ]
        )
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-smoke",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "token_configured": bool(token),
        "passed": all(check.get("ok") is True for check in checks),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke(base_url=args.base_url, token=args.token, timeout=args.timeout, skip_media=args.skip_media)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
