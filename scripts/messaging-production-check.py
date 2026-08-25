#!/usr/bin/env python3
"""Read-only production preflight checks for Freyja messaging connectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and Path(sys.executable) != _VENV_PYTHON:
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])

_SRC_DIR = str(_PROJECT_ROOT / "src")
_ROOT_DIR = str(_PROJECT_ROOT)
_IMESSAGE_RUNTIME_ROOT = Path("/Users/freyja/freyja-os-imessage-runtime")
_IMESSAGE_RUNTIME_MANIFEST = _PROJECT_ROOT / "scripts" / "imessage-runtime-files.txt"
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(1, _ROOT_DIR)

from connectors.imessage.config import IMessageSettings  # noqa: E402
from connectors.signal.config import SignalSettings  # noqa: E402


def _imessage_runtime_source_paths(manifest: Path = _IMESSAGE_RUNTIME_MANIFEST) -> tuple[str, ...]:
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    return tuple(
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    )


class SyntheticRouteIdentity:
    def __init__(
        self,
        *,
        person_id: str = "joe",
        person_display_name: str = "Joe",
        person_preferred_name: str = "Joe",
        agent_id: str = "cloyd-gibbler",
        agent_display_name: str = "Cloyd Gibbler",
        expected_provider: str = "local_reasoning",
    ) -> None:
        self.person_id = person_id
        self.person_display_name = person_display_name
        self.person_preferred_name = person_preferred_name
        self.agent_id = agent_id
        self.agent_display_name = agent_display_name
        self.expected_provider = expected_provider

    @property
    def client_subject(self) -> str:
        return f"agent:{self.agent_id}"

    @property
    def account_owner(self) -> str:
        return f"person:{self.person_id}"


def _run_command(command: list[str], *, timeout: float) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except OSError as exc:
        return {"ok": False, "error": type(exc).__name__}
    return {
        "ok": completed.returncode == 0,
        "status_code": completed.returncode,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _imessage_runtime_source_drift(
    *,
    checkout_root: Path = _PROJECT_ROOT,
    runtime_root: Path = _IMESSAGE_RUNTIME_ROOT,
    manifest: Path = _IMESSAGE_RUNTIME_MANIFEST,
) -> dict[str, object]:
    files = []
    drift_count = 0
    source_paths = _imessage_runtime_source_paths(manifest)
    if not source_paths:
        return {
            "ok": False,
            "checkout_root": str(checkout_root),
            "runtime_root": str(runtime_root),
            "drift_count": 1,
            "files": [{"path": str(manifest), "status": "missing-manifest"}],
        }
    for rel_path in source_paths:
        checkout_file = checkout_root / rel_path
        runtime_file = runtime_root / rel_path
        entry: dict[str, object] = {"path": rel_path}
        if not checkout_file.exists():
            entry["status"] = "missing-checkout"
            drift_count += 1
        elif not runtime_file.exists():
            entry["status"] = "missing-runtime"
            drift_count += 1
        else:
            checkout_sha = _sha256(checkout_file)
            runtime_sha = _sha256(runtime_file)
            entry["checkout_sha256"] = checkout_sha
            entry["runtime_sha256"] = runtime_sha
            if checkout_sha == runtime_sha:
                entry["status"] = "ok"
            else:
                entry["status"] = "diff"
                drift_count += 1
        files.append(entry)

    return {
        "ok": drift_count == 0,
        "checkout_root": str(checkout_root),
        "runtime_root": str(runtime_root),
        "drift_count": drift_count,
        "files": files,
    }


def _imessage_runtime_import_check(runtime_root: Path = _IMESSAGE_RUNTIME_ROOT) -> dict[str, object]:
    python = runtime_root / ".venv" / "bin" / "python"
    if not python.exists():
        return {
            "ok": False,
            "error": "missing-runtime-python",
            "python": str(python),
        }
    command = [
        str(python),
        "-c",
        (
            "import importlib; "
            "[importlib.import_module(name) for name in "
            "('freyja.router', 'connectors.imessage.gateway')]"
        ),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{runtime_root / 'src'}:{runtime_root}"
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "python": str(python)}
    except OSError as exc:
        return {"ok": False, "python": str(python), **_safe_error(exc)}
    result: dict[str, object] = {
        "ok": completed.returncode == 0,
        "status_code": completed.returncode,
        "python": str(python),
        "modules": ["freyja.router", "connectors.imessage.gateway"],
    }
    if completed.returncode != 0:
        result["stderr"] = _clip_tail(completed.stderr, limit=500)
    return result


def _http_health(url: str, *, timeout: float = 5.0, headers: dict[str, str] | None = None) -> dict[str, object]:
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code}
    except Exception as exc:  # noqa: BLE001 - operator output should stay compact
        return {"ok": False, **_safe_error(exc)}


def _http_json(url: str, *, timeout: float = 5.0, headers: dict[str, str] | None = None) -> dict[str, object]:
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "payload": payload if isinstance(payload, dict) else {},
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code}
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid-json"}
    except Exception as exc:  # noqa: BLE001 - operator output should stay compact
        return {"ok": False, **_safe_error(exc)}


def _http_post_json(
    url: str,
    *,
    payload: dict[str, object],
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    try:
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "payload": parsed if isinstance(parsed, dict) else {},
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code}
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid-json"}
    except Exception as exc:  # noqa: BLE001 - operator output should stay compact
        return {"ok": False, **_safe_error(exc)}


def _director_rev2_health(base_url: str, token: str, *, timeout: float) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    checks = {"/providers/health": _providers_health(f"{base_url.rstrip('/')}/providers/health", timeout=timeout, headers=headers)}
    for path in ("/iris-router/health", "/macagent/health"):
        checks[path] = _http_health(f"{base_url.rstrip('/')}{path}", timeout=timeout, headers=headers)
    return {
        "ok": all(status.get("ok") is True for status in checks.values()),
        "checks": checks,
    }


def _synthetic_route_smoke(
    settings: IMessageSettings,
    *,
    identity: SyntheticRouteIdentity,
    interface: str,
    conversation_id: str,
    timeout: float,
    post_json: Callable[..., dict[str, object]] = _http_post_json,
) -> dict[str, object]:
    headers = {
        "X-Freyja-Client-Type": interface,
        "X-Freyja-Client-Subject": identity.client_subject,
        "X-Freyja-Account-Owner": identity.account_owner,
        "X-Freyja-Conversation-Id": conversation_id,
        "X-Freyja-Agent-Id": identity.agent_id,
        "X-Freyja-Agent-Display-Name": identity.agent_display_name,
        "X-Freyja-Person-Id": identity.person_id,
        "X-Freyja-Person-Display-Name": identity.person_display_name,
        "X-Freyja-Person-Preferred-Name": identity.person_preferred_name,
    }
    if settings.freyja_connector_token:
        headers["Authorization"] = f"Bearer {settings.freyja_connector_token}"
    response = post_json(
        f"{settings.freyja_director_url.rstrip('/')}/route",
        payload={
            "request_id": f"{interface}-synthetic-route-smoke",
            "prompt": "Freyja 2.0 synthetic route smoke. Reply with a short acknowledgement.",
            "provider": "auto",
            "include_trace": True,
        },
        timeout=timeout,
        headers=headers,
    )
    if response.get("ok") is not True:
        return {key: value for key, value in response.items() if key != "payload"}
    payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    person = trace.get("person") if isinstance(trace.get("person"), dict) else {}
    principal = trace.get("principal") if isinstance(trace.get("principal"), dict) else {}
    checks = {
        "response_present": bool(str(payload.get("response") or "").strip()),
        "provider_matches": payload.get("provider") == identity.expected_provider,
        "interface_matches": trace.get("interface") == interface,
        "person_matches": person.get("person_id") == identity.person_id,
        "principal_matches": principal.get("client_subject") == identity.client_subject,
    }
    return {
        "ok": all(checks.values()),
        "status_code": response.get("status_code"),
        "checks": checks,
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "privacy_classification": payload.get("privacy_classification"),
        "expected_provider": identity.expected_provider,
        "expected_person_id": identity.person_id,
        "expected_client_subject": identity.client_subject,
    }


def _imessage_route_smoke(
    settings: IMessageSettings,
    *,
    timeout: float,
    identity: SyntheticRouteIdentity | None = None,
    post_json: Callable[..., dict[str, object]] = _http_post_json,
) -> dict[str, object]:
    route_identity = identity or SyntheticRouteIdentity()
    imessage = _synthetic_route_smoke(
        settings,
        identity=route_identity,
        interface="imessage",
        conversation_id=f"imessage-synthetic-smoke:{route_identity.person_id}",
        timeout=timeout,
        post_json=post_json,
    )
    terminal = _synthetic_route_smoke(
        settings,
        identity=route_identity,
        interface="terminal",
        conversation_id=f"terminal-synthetic-smoke:{route_identity.person_id}",
        timeout=timeout,
        post_json=post_json,
    )
    equivalent = (
        imessage.get("ok") is True
        and terminal.get("ok") is True
        and imessage.get("provider") == terminal.get("provider") == route_identity.expected_provider
        and imessage.get("model") == terminal.get("model")
    )
    return {
        "ok": equivalent,
        "imessage": imessage,
        "terminal": terminal,
        "terminal_equivalent": equivalent,
    }


def _imessage_inprocess_route_smoke(
    settings: IMessageSettings,
    *,
    timeout: float,
    identity: SyntheticRouteIdentity | None = None,
) -> dict[str, object]:
    """Exercise Director routing without opening a network socket.

    This is not a substitute for the live LaunchAgent smoke test. It proves the
    source-level Director path sees iMessage and terminal as the same trusted
    person/agent request even in sandboxes that cannot connect to localhost.
    """
    try:
        from fastapi.testclient import TestClient
        from freyja.main import app
    except Exception as exc:  # noqa: BLE001 - diagnostic script should keep running
        return {"ok": False, **_safe_error(exc)}

    captured_prompts: list[str] = []

    async def fake_chat(*args: object, **kwargs: object) -> dict[str, object]:
        captured_prompts.append(str(kwargs.get("prompt") or ""))
        return {
            "model": kwargs.get("model") or "synthetic-local-reasoning",
            "message": {"role": "assistant", "content": "synthetic acknowledgement"},
            "prompt_eval_count": 12,
            "eval_count": 2,
            "latency_ms": 10,
        }

    client = TestClient(app)

    def post_json(
        url: str,
        *,
        payload: dict[str, object],
        timeout: float = 5.0,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        response = client.post("/route", json=payload, headers=headers or {})
        parsed = response.json() if response.content else {}
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "payload": parsed if isinstance(parsed, dict) else {},
        }

    with patch("freyja.ollama_client.OllamaClient.chat", fake_chat):
        status = _imessage_route_smoke(settings, timeout=timeout, identity=identity, post_json=post_json)

    normalized_prompts = [_normalize_inprocess_prompt(prompt) for prompt in captured_prompts]
    prompt_equivalent = len(normalized_prompts) == 2 and normalized_prompts[0] == normalized_prompts[1]
    context_present = all("BEGIN FREYJA DIRECT AGENT CONTEXT" in prompt for prompt in captured_prompts)
    status["source"] = "inprocess"
    status["prompt_context_equivalent"] = prompt_equivalent
    status["direct_agent_context_present"] = context_present
    status["ok"] = status.get("ok") is True and prompt_equivalent and context_present
    return status


def _normalize_inprocess_prompt(prompt: str) -> str:
    return "\n".join(
        "<interface>"
        if line.startswith("Interface: ")
        else line
        for line in prompt.splitlines()
    )


def _providers_health(url: str, *, timeout: float, headers: dict[str, str]) -> dict[str, object]:
    response = _http_json(url, timeout=timeout, headers=headers)
    if response.get("ok") is not True:
        return {key: value for key, value in response.items() if key != "payload"}
    payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
    providers = payload.get("providers") if isinstance(payload.get("providers"), list) else []
    by_id = {
        str(provider.get("provider_id")): provider
        for provider in providers
        if isinstance(provider, dict) and provider.get("provider_id")
    }
    # Qwen coding is optional; require the production-critical local profiles only.
    required = ("legacy_ollama", "heavy_local")
    readiness = {
        provider_id: bool(by_id.get(provider_id, {}).get("ready"))
        for provider_id in required
    }
    missing = [provider_id for provider_id in required if provider_id not in by_id]
    unavailable = [provider_id for provider_id, ready in readiness.items() if not ready]
    return {
        "ok": not missing and not unavailable,
        "status_code": response.get("status_code"),
        "required_provider_readiness": readiness,
        "missing_required_providers": missing,
        "unavailable_required_providers": unavailable,
    }


def _imsg_whois_local(settings: IMessageSettings, address: str, *, timeout: float) -> dict[str, object]:
    command = [
        settings.resolved_imsg_path,
        "whois",
        "--db",
        settings.imessage_database_path,
        "--address",
        address,
        "--local",
        "--json",
    ]
    if "@" in address:
        command.extend(["--type", "email"])
    elif any(char.isdigit() for char in address):
        command.extend(["--type", "phone"])
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"known": False, "service": "unknown", "error": "timeout"}
    except OSError as exc:
        return {"known": False, "service": "unknown", **_safe_error(exc)}
    if completed.returncode != 0:
        return {"known": False, "service": "unknown", "error": "failed"}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"known": False, "service": "unknown", "error": "invalid-json"}
    return payload if isinstance(payload, dict) else {"known": False, "service": "unknown"}


def _messages_applescript_status(*, timeout: float) -> dict[str, object]:
    return _run_command(
        ["osascript", "-e", 'tell application "Messages" to count chats'],
        timeout=timeout,
    )


def _safe_error(exc: BaseException) -> dict[str, object]:
    detail = _safe_error_detail(exc)
    payload: dict[str, object] = {"error": type(exc).__name__}
    if detail:
        payload["detail"] = detail
    return payload


def _safe_error_detail(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, BaseException):
            return _safe_error_detail(reason)
        if reason:
            return _clip(str(reason))
    if isinstance(exc, OSError):
        parts = []
        if getattr(exc, "errno", None) is not None:
            parts.append(f"errno={exc.errno}")
        if getattr(exc, "strerror", None):
            parts.append(str(exc.strerror))
        return _clip(" ".join(parts))
    return ""


def _clip(value: str, limit: int = 120) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:limit]


def _clip_tail(value: str, limit: int = 500) -> str:
    cleaned = " ".join(value.split())
    return cleaned[-limit:]


def _imessage_status(
    *,
    check_director: bool,
    check_rev2_director: bool,
    check_route_smoke: bool,
    check_inprocess_route_smoke: bool,
    route_identity: SyntheticRouteIdentity | None = None,
    env_file: str | None = None,
) -> dict[str, object]:
    settings = IMessageSettings(_env_file=env_file) if env_file else IMessageSettings()
    imsg_path = Path(settings.resolved_imsg_path)
    database_path = Path(settings.imessage_database_path)
    status: dict[str, object] = {
        "enabled": settings.imessage_enabled,
        "host_role": "iris-macos-launchagent",
        "director_url": settings.freyja_director_url,
        "connector_token_configured": bool(settings.freyja_connector_token),
        "imsg_path": str(imsg_path),
        "imsg_exists": imsg_path.exists(),
        "database_path": str(database_path),
        "database_exists": database_path.exists(),
        "allowed_sender_count": len(settings.allowed_sender_set),
        "watch_enabled": settings.imessage_watch_enabled,
        "poll_interval_seconds": settings.imessage_poll_interval_seconds,
        "family_observer_enabled": settings.imessage_family_observer_enabled,
        "family_chat_count": len(settings.family_chat_identifier_set),
        "provisional_reply_enabled": settings.imessage_provisional_reply_enabled,
    }
    status["runtime_source_drift"] = _imessage_runtime_source_drift()
    status["runtime_import_check"] = _imessage_runtime_import_check()
    allowed_identities = settings.allowed_sender_identities
    whois_timeout = min(max(1.0, settings.imessage_command_timeout_seconds), 5.0)
    local_reachable = []
    for address in allowed_identities:
        whois = _imsg_whois_local(settings, address, timeout=whois_timeout)
        if whois.get("known") is True and str(whois.get("service", "")).lower() == "imessage":
            local_reachable.append(address)
    status["locally_known_imessage_sender_count"] = len(local_reachable)
    status["imsg_status"] = _run_command([settings.resolved_imsg_path, "status"], timeout=whois_timeout)
    status["messages_applescript"] = _messages_applescript_status(timeout=whois_timeout)
    if check_director:
        status["director_health"] = _http_health(
            f"{settings.freyja_director_url.rstrip('/')}/health",
            timeout=settings.imessage_request_timeout_seconds,
        )
    if check_rev2_director:
        status["director_rev2_health"] = _director_rev2_health(
            settings.freyja_director_url,
            settings.freyja_connector_token,
            timeout=settings.imessage_request_timeout_seconds,
        )
    if check_route_smoke:
        status["synthetic_route_smoke"] = _imessage_route_smoke(
            settings,
            timeout=settings.imessage_request_timeout_seconds,
            identity=route_identity,
        )
    if check_inprocess_route_smoke:
        status["inprocess_route_smoke"] = _imessage_inprocess_route_smoke(
            settings,
            timeout=settings.imessage_request_timeout_seconds,
            identity=route_identity,
        )
    status["ready_for_live_smoke"] = all(
        [
            status["enabled"],
            status["connector_token_configured"],
            status["imsg_exists"],
            status["database_exists"],
            status["allowed_sender_count"],
            status["runtime_source_drift"]["ok"],
            status["runtime_import_check"]["ok"],
            bool(settings.freyja_director_url.strip()),
            not check_director or status.get("director_health", {}).get("ok") is True,
            not check_rev2_director or status.get("director_rev2_health", {}).get("ok") is True,
            not check_route_smoke or status.get("synthetic_route_smoke", {}).get("ok") is True,
            not check_inprocess_route_smoke or status.get("inprocess_route_smoke", {}).get("ok") is True,
        ]
    )
    return status


def _signal_status(
    *,
    check_director: bool,
    check_rev2_director: bool,
    check_rest: bool,
    env_file: str | None = None,
) -> dict[str, object]:
    settings = SignalSettings(_env_file=env_file) if env_file else SignalSettings()
    status: dict[str, object] = {
        "enabled": settings.signal_enabled,
        "host_role": "atlas-compose",
        "director_url": settings.freyja_director_url,
        "connector_token_configured": bool(settings.freyja_connector_token),
        "rest_api_url": settings.signal_rest_api_url,
        "account_number_configured": settings.transport_configured,
        "allowed_sender_count": len(settings.allowed_sender_set),
        "poll_interval_seconds": settings.signal_poll_interval_seconds,
        "max_message_chars": settings.signal_max_message_chars,
    }
    if check_director:
        status["director_health"] = _http_health(
            f"{settings.freyja_director_url.rstrip('/')}/health",
            timeout=min(settings.signal_request_timeout_seconds, 5.0),
        )
    if check_rev2_director:
        status["director_rev2_health"] = _director_rev2_health(
            settings.freyja_director_url,
            settings.freyja_connector_token,
            timeout=min(settings.signal_request_timeout_seconds, 5.0),
        )
    if check_rest:
        status["signal_rest_health"] = _http_health(
            f"{settings.signal_rest_api_url.rstrip('/')}/v1/about",
            timeout=min(settings.signal_transport_timeout_seconds, 5.0),
        )
    status["ready_for_live_smoke"] = all(
        [
            status["enabled"],
            status["connector_token_configured"],
            status["account_number_configured"],
            status["allowed_sender_count"],
            bool(settings.freyja_director_url.strip()),
            bool(settings.signal_rest_api_url.strip()),
            not check_director or status.get("director_health", {}).get("ok") is True,
            not check_rev2_director or status.get("director_rev2_health", {}).get("ok") is True,
            not check_rest or status.get("signal_rest_health", {}).get("ok") is True,
        ]
    )
    return status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Freyja iMessage and Signal production readiness without printing secrets."
    )
    parser.add_argument(
        "--connector",
        choices=("all", "imessage", "signal"),
        default="all",
        help="Connector to check.",
    )
    parser.add_argument(
        "--env-file",
        help="Optional connector environment file to read, such as the Iris runtime .env or Atlas Compose .env.",
    )
    parser.add_argument(
        "--check-director",
        action="store_true",
        help="Call the configured Director /health endpoint.",
    )
    parser.add_argument(
        "--check-rev2-director",
        action="store_true",
        help="Call protected Rev 2 Director health endpoints using the connector token.",
    )
    parser.add_argument(
        "--check-imessage-route-smoke",
        action="store_true",
        help="Call Director /route with synthetic iMessage headers and require local_reasoning trace evidence.",
    )
    parser.add_argument(
        "--check-inprocess-route-smoke",
        action="store_true",
        help="Exercise Director /route in-process with synthetic iMessage and terminal headers; does not prove live transport.",
    )
    parser.add_argument("--route-smoke-person-id", default="joe", help="Person ID used by --check-imessage-route-smoke.")
    parser.add_argument("--route-smoke-person-display-name", default="Joe", help="Person display name used by --check-imessage-route-smoke.")
    parser.add_argument("--route-smoke-person-preferred-name", default="Joe", help="Person preferred name used by --check-imessage-route-smoke.")
    parser.add_argument("--route-smoke-agent-id", default="cloyd-gibbler", help="Agent ID used by --check-imessage-route-smoke.")
    parser.add_argument("--route-smoke-agent-display-name", default="Cloyd Gibbler", help="Agent display name used by --check-imessage-route-smoke.")
    parser.add_argument("--route-smoke-expected-provider", default="local_reasoning", help="Expected provider for synthetic route smoke.")
    parser.add_argument(
        "--check-signal-rest",
        action="store_true",
        help="Call the configured signal-cli-rest-api /v1/about endpoint.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON report for Rev 2 readiness evidence.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report: dict[str, object] = {}
    route_identity = SyntheticRouteIdentity(
        person_id=args.route_smoke_person_id,
        person_display_name=args.route_smoke_person_display_name,
        person_preferred_name=args.route_smoke_person_preferred_name,
        agent_id=args.route_smoke_agent_id,
        agent_display_name=args.route_smoke_agent_display_name,
        expected_provider=args.route_smoke_expected_provider,
    )

    if args.connector in {"all", "imessage"}:
        report["imessage"] = _imessage_status(
            check_director=args.check_director,
            check_rev2_director=args.check_rev2_director,
            check_route_smoke=args.check_imessage_route_smoke,
            check_inprocess_route_smoke=args.check_inprocess_route_smoke,
            route_identity=route_identity,
            env_file=args.env_file,
        )
    if args.connector in {"all", "signal"}:
        report["signal"] = _signal_status(
            check_director=args.check_director,
            check_rev2_director=args.check_rev2_director,
            check_rest=args.check_signal_rest,
            env_file=args.env_file,
        )

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    connector_reports = [value for value in report.values() if isinstance(value, dict)]
    return 0 if all(value.get("ready_for_live_smoke") for value in connector_reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
