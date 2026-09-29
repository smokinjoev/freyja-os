#!/usr/bin/env python3
"""Run a Freyja 6 LiteLLM/Vulcan smoke and record redacted evidence."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
ALLOWED_MODELS = ("vulcan-fast", "vulcan-general", "vulcan-code")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test Freyja 6 LiteLLM to Vulcan routing.")
    parser.add_argument("--base-url", default=os.environ.get("FREYJA6_LITELLM_BASE_URL", "http://127.0.0.1:4600/v1"))
    parser.add_argument("--api-key", default=os.environ.get("LITELLM_MASTER_KEY"))
    parser.add_argument("--models", nargs="+", default=["vulcan-general", "vulcan-fast", "vulcan-code"])
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def run_smoke(*, base_url: str, api_key: str, models: list[str], timeout: float) -> dict[str, Any]:
    requested_models = _validate_requested_models(models)
    _validate_gateway_base_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    trace_prefix = f"freyja6-litellm-{uuid.uuid4().hex[:12]}"
    results: list[dict[str, Any]] = []
    normalized_base = base_url.rstrip("/")
    with httpx.Client(base_url=normalized_base, headers=headers, timeout=timeout) as client:
        listed_models = _list_models(client)
        missing_models = sorted(model for model in requested_models if model not in listed_models)
        if missing_models:
            raise RuntimeError("LiteLLM /models is missing requested Freyja 6 aliases: " + ", ".join(missing_models))
        for index, model in enumerate(requested_models, start=1):
            trace_id = f"{trace_prefix}-{index}"
            response = client.post(
                "/chat/completions",
                headers={"X-Freyja-Trace-Id": trace_id},
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with exactly: gateway ok",
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 16,
                },
            )
            status_code = response.status_code
            body = _safe_json(response)
            results.append(
                {
                    "model": model,
                    "trace_id": trace_id,
                    "status_code": status_code,
                    "ok": 200 <= status_code < 300 and _response_model_matches(model, body) and _response_content_matches(body),
                    "response_model": body.get("model") if isinstance(body, dict) else None,
                    "response_text": _response_text(body),
                    "finish_reason": _finish_reason(body),
                }
            )
            response.raise_for_status()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url_redacted": _redact_base_url(base_url),
        "listed_models": listed_models,
        "results": results,
    }


def update_evidence(path: Path, smoke: dict[str, Any]) -> dict[str, Any]:
    payload = _load_evidence(path)
    acceptance = _acceptance_map(payload)
    successful = _verified_results(smoke)
    successful_by_model = _first_verified_result_per_model(successful)
    distinct_successful_models = _distinct_models(successful_by_model)
    if successful:
        first = successful[0]
        acceptance["litellm_to_vulcan"] = {
            "status": "complete",
            "captured_at": smoke["timestamp"],
            "source": "freyja6-litellm-smoke",
            "evidence": {
                "litellm_request_id": first["trace_id"],
                "model": first["model"],
                "response_model": first["response_model"],
                "vulcan_backend": smoke["base_url_redacted"],
            },
        }
    if len(distinct_successful_models) >= 2:
        acceptance["model_switch"] = {
            "status": "complete",
            "captured_at": smoke["timestamp"],
            "source": "freyja6-litellm-smoke",
            "evidence": {
                "models_tested": distinct_successful_models,
                "response_models": [item["response_model"] for item in successful_by_model],
                "gateway_trace_ids": [item["trace_id"] for item in successful_by_model],
                "listed_models": smoke.get("listed_models", []),
            },
        }
    payload["last_litellm_smoke"] = smoke
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def append_logs(log_root: Path, smoke: dict[str, Any]) -> list[dict[str, Any]]:
    log_root.mkdir(parents=True, exist_ok=True)
    writes = []
    model_log = log_root / "freyja-test-model-calls.jsonl"
    acceptance_log = log_root / "freyja-test-acceptance.jsonl"
    listed_aliases = {str(model) for model in smoke.get("listed_models", [])} if isinstance(smoke.get("listed_models"), list) else set()
    for item in smoke.get("results", []):
        verified = _result_is_verified(item, listed_aliases)
        entry = {
            "timestamp": smoke["timestamp"],
            "event": "model_call",
            "trace_id": item.get("trace_id", ""),
            "model": item.get("model", ""),
            "status": "ok" if verified else "failed",
            "status_code": item.get("status_code"),
            "source": "freyja6-litellm-smoke",
        }
        if not verified:
            entry["error_summary"] = _model_failure_summary(item, listed_aliases)
        _append_jsonl(model_log, entry)
        writes.append({"log": _redact_log_path(model_log), "trace_id": entry["trace_id"]})

    successful = _verified_results(smoke)
    if successful:
        _append_jsonl(
            acceptance_log,
            {
                "timestamp": smoke["timestamp"],
                "event": "acceptance",
                "trace_id": successful[0].get("trace_id", ""),
                "acceptance_id": "litellm_to_vulcan",
                "status": "ok",
                "source": "freyja6-litellm-smoke",
            },
        )
        writes.append({"log": _redact_log_path(acceptance_log), "trace_id": successful[0].get("trace_id", "")})
    successful_by_model = _first_verified_result_per_model(successful)
    if len(_distinct_models(successful_by_model)) >= 2:
        _append_jsonl(
            acceptance_log,
            {
                "timestamp": smoke["timestamp"],
                "event": "acceptance",
                "trace_id": successful_by_model[-1].get("trace_id", ""),
                "acceptance_id": "model_switch",
                "status": "ok",
                "source": "freyja6-litellm-smoke",
            },
        )
        writes.append({"log": _redact_log_path(acceptance_log), "trace_id": successful_by_model[-1].get("trace_id", "")})
    return writes


def preflight_log_writes(log_root: Path) -> None:
    _check_append_path(log_root / "freyja-test-model-calls.jsonl")
    _check_append_path(log_root / "freyja-test-acceptance.jsonl")


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    _check_append_path(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _check_append_path(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"Log file must not be a symlink: {path.name}.")
    if path.exists() and not path.is_file():
        raise ValueError(f"Log file must be a regular file: {path.name}.")


def _redact_log_path(path: Path) -> str:
    return f"freyja6/logs/{path.name}"


def _list_models(client: httpx.Client) -> list[str]:
    response = client.get("/models")
    response.raise_for_status()
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else []
    if not isinstance(data, list):
        return []
    return sorted(str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id"))


def _validate_requested_models(models: list[str]) -> list[str]:
    normalized = [str(model).strip() for model in models if str(model).strip()]
    unexpected = sorted(set(normalized) - set(ALLOWED_MODELS))
    if unexpected:
        raise ValueError("Unexpected Freyja 6 LiteLLM aliases requested: " + ", ".join(unexpected))
    deduped = list(dict.fromkeys(normalized))
    if len(deduped) < 2:
        raise ValueError("Model switch validation requires at least two distinct Freyja 6 aliases.")
    return deduped


def _validate_gateway_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("FREYJA6_LITELLM_BASE_URL must be an HTTP(S) URL.")
    hostname = (parsed.hostname or "").lower()
    if hostname in {"litellm-db", "hermes-freyja-test"}:
        raise ValueError("FREYJA6_LITELLM_BASE_URL must point at the LiteLLM gateway, not internal services.")
    if hostname and not _gateway_host_is_local_or_private(hostname):
        raise ValueError("FREYJA6_LITELLM_BASE_URL must use Atlas loopback, private, tailnet, or explicitly LiteLLM-scoped host.")


def _gateway_host_is_local_or_private(hostname: str) -> bool:
    if hostname in {"localhost", "litellm"} or hostname.startswith("litellm-") or hostname.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or hostname.startswith("100.")


def _response_model_matches(requested_model: str, body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    response_model = body.get("model")
    return response_model == requested_model


def _verified_results(smoke: dict[str, Any]) -> list[dict[str, Any]]:
    listed_models = smoke.get("listed_models")
    if not isinstance(listed_models, list):
        return []
    listed_aliases = {str(model) for model in listed_models}
    verified = [item for item in smoke.get("results", []) if _result_is_verified(item, listed_aliases)]
    seen_traces: set[str] = set()
    distinct_trace_results: list[dict[str, Any]] = []
    for item in verified:
        trace_id = str(item.get("trace_id") or "")
        if trace_id in seen_traces:
            continue
        seen_traces.add(trace_id)
        distinct_trace_results.append(item)
    return distinct_trace_results


def _missing_verified_models(smoke: dict[str, Any], requested_models: list[str]) -> list[str]:
    verified_models = set(_distinct_models(_verified_results(smoke)))
    return [model for model in requested_models if model not in verified_models]


def _first_verified_result_per_model(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = {}
    for item in results:
        model = str(item.get("model") or "")
        if model and model not in by_model:
            by_model[model] = item
    return list(by_model.values())


def _result_is_verified(item: Any, listed_aliases: set[str]) -> bool:
    if not isinstance(item, dict):
        return False
    model = str(item.get("model") or "")
    trace_id = str(item.get("trace_id") or "")
    status_code = item.get("status_code")
    response_model = item.get("response_model")
    return (
        item.get("ok") is True
        and model in ALLOWED_MODELS
        and model in listed_aliases
        and _trace_id_is_validation_trace(trace_id)
        and isinstance(status_code, int)
        and 200 <= status_code < 300
        and response_model == model
        and item.get("finish_reason") == "stop"
        and str(item.get("response_text") or "").strip().lower() == "gateway ok"
    )


def _model_failure_summary(item: Any, listed_aliases: set[str]) -> str:
    if not isinstance(item, dict):
        return "malformed model result"
    model = str(item.get("model") or "")
    trace_id = str(item.get("trace_id") or "")
    status_code = item.get("status_code")
    if model not in ALLOWED_MODELS:
        return "model alias is not approved for Freyja 6 validation"
    if model not in listed_aliases:
        return "model alias was not listed by LiteLLM"
    if not _trace_id_is_validation_trace(trace_id):
        return "trace id is not a Freyja validation trace"
    if not isinstance(status_code, int) or not 200 <= status_code < 300:
        return "LiteLLM response status was not successful"
    if item.get("response_model") != model:
        return "response model did not match requested alias"
    if item.get("finish_reason") != "stop":
        return "response did not finish with stop"
    if str(item.get("response_text") or "").strip().lower() != "gateway ok":
        return "response text did not match validation phrase"
    if item.get("ok") is not True:
        return "model result was not marked ok"
    return "model result failed verification"


def _trace_id_is_validation_trace(trace_id: str) -> bool:
    trace = trace_id.strip()
    return "..." not in trace and (trace.startswith("trace-") or trace.startswith("freyja6-"))


def _distinct_models(results: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(item.get("model")) for item in results if item.get("model")))


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {}


def _finish_reason(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    reason = choices[0].get("finish_reason")
    return str(reason) if reason is not None else None


def _response_text(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content or "")


def _response_content_matches(body: Any) -> bool:
    return _response_text(body).strip().lower() == "gateway ok" and _finish_reason(body) == "stop"


def _redact_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    if not parsed.scheme or not hostname:
        return "redacted-litellm-gateway"
    redacted_host = _redacted_gateway_host(hostname)
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse((parsed.scheme, f"{redacted_host}{port}", parsed.path, "", "", ""))


def _redacted_gateway_host(hostname: str) -> str:
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return "atlas-loopback"
    if hostname in {"litellm", "vulcan"}:
        return hostname
    if hostname.startswith("litellm-"):
        return "litellm-private"
    if hostname.startswith("vulcan-"):
        return "vulcan-private"
    if hostname.endswith(".local"):
        return "atlas-local"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return "atlas-private"
    if address.is_loopback:
        return "atlas-loopback"
    if str(address).startswith("100."):
        return "vulcan-tailnet"
    if address.is_private:
        return "atlas-private"
    return "atlas-private"


def _load_evidence(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("Live evidence file must not be a symlink.")
    if path.exists() and not path.is_file():
        raise ValueError("Live evidence file must be a regular file.")
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("schema_version", "1.0")
            payload.setdefault("report_type", "freyja6-live-evidence")
            return payload
    return {"schema_version": "1.0", "report_type": "freyja6-live-evidence", "acceptance": {}}


def _acceptance_map(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "1.0" or payload.get("report_type") != "freyja6-live-evidence":
        raise ValueError("Live evidence file must be a freyja6-live-evidence schema_version 1.0 artifact.")
    acceptance = payload.setdefault("acceptance", {})
    if not isinstance(acceptance, dict):
        raise ValueError("Live evidence acceptance must be an object before smoke helpers can update it.")
    return acceptance


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.api_key:
        print("LITELLM_MASTER_KEY or --api-key is required.", file=sys.stderr)
        return 2
    try:
        _acceptance_map(_load_evidence(args.evidence))
        preflight_log_writes(args.log_root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    smoke = run_smoke(base_url=args.base_url, api_key=args.api_key, models=args.models, timeout=args.timeout)
    try:
        update_evidence(args.evidence, smoke)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc), "smoke": smoke}, indent=2, sort_keys=True))
        return 2
    log_writes = append_logs(args.log_root, smoke)
    requested_models = _validate_requested_models(args.models)
    missing_verified = _missing_verified_models(smoke, requested_models)
    ok = not missing_verified
    print(
        json.dumps(
            {
                "ok": ok,
                "evidence": str(args.evidence),
                "log_writes": log_writes,
                "missing_verified_models": missing_verified,
                "smoke": smoke,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
