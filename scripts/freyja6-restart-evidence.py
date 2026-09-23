#!/usr/bin/env python3
"""Collect Freyja 6 restart, memory, and Atlas return evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_HERMES_DATA = Path(os.environ.get("FREYJA6_HERMES_DATA", "/srv/freyja6/hermes"))
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
AGENT_ID = "freyja-test"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record redacted Freyja 6 restart and reboot evidence.")
    parser.add_argument("--hermes-data", type=Path, default=DEFAULT_HERMES_DATA)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--before-identity-sha256", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--stored-fact-label", default="")
    parser.add_argument("--memory-recall-trace-id", default="")
    parser.add_argument("--memory-fact-file", type=Path)
    parser.add_argument("--container-status", default="")
    parser.add_argument("--container-status-json", type=Path)
    parser.add_argument("--reboot-start", default="")
    parser.add_argument("--reboot-end", default="")
    parser.add_argument("--discord-reply-trace-id", default="")
    parser.add_argument("--discord-reply-verification", default="")
    return parser


def collect_evidence(
    *,
    hermes_data: Path,
    log_root: Path,
    before_identity_sha256: str = "",
    session_id: str = "",
    stored_fact_label: str = "",
    memory_recall_trace_id: str = "",
    memory_fact_file: Path | None = None,
    container_status: str = "",
    container_status_json: Path | None = None,
    reboot_start: str = "",
    reboot_end: str = "",
    discord_reply_trace_id: str = "",
    discord_reply_verification: str = "",
) -> dict[str, Any]:
    agent_root = hermes_data / "agents" / AGENT_ID
    identity_file = agent_root / "identity.md"
    sessions_dir = agent_root / "sessions"
    fact_file = memory_fact_file or agent_root / "memory" / "private" / "freyja6-validation-fact.json"
    identity_after = _sha256_file(identity_file)
    session_restored = _session_marker_valid(sessions_dir, session_id)
    fact_present = _memory_fact_valid(fact_file, stored_fact_label) if stored_fact_label else False
    restart_trace_id = f"freyja6-restart-{uuid.uuid4().hex[:12]}"
    fact_recalled = fact_present and _memory_recall_ok(memory_recall_trace_id, restart_trace_id)
    status_after = _container_status(container_status=container_status, container_status_json=container_status_json)
    logs_present = all((log_root / name).exists() for name in ("freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl"))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": AGENT_ID,
        "restart_trace_id": restart_trace_id,
        "identity_file_redacted": f"hermes/agents/{AGENT_ID}/identity.md",
        "identity_before_sha256": _normalize_hash(before_identity_sha256),
        "identity_after_sha256": identity_after,
        "identity_matches_before": bool(before_identity_sha256 and identity_after == _normalize_hash(before_identity_sha256)),
        "session_id_redacted": session_id or _latest_session_name(sessions_dir),
        "session_restored": session_restored,
        "stored_fact_label": stored_fact_label,
        "memory_fact_file_redacted": f"hermes/agents/{AGENT_ID}/memory/private/{fact_file.name}",
        "memory_fact_present": fact_present,
        "memory_recall_trace_id": memory_recall_trace_id,
        "memory_fact_recalled": fact_recalled,
        "memory_provider": "hermes-native",
        "logs_present": logs_present,
        "container_status_after": status_after,
        "reboot_window": _reboot_window(reboot_start, reboot_end),
        "discord_reply_after_reboot": discord_reply_trace_id,
        "discord_reply_after_reboot_verification": discord_reply_verification,
    }


def update_evidence(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    payload = _load_evidence(path)
    acceptance = _acceptance_map(payload)

    if _restart_identity_ok(report):
        acceptance["restart_identity_session"] = {
            "status": "complete",
            "captured_at": report["timestamp"],
            "source": "freyja6-restart-evidence",
            "evidence": {
                "restart_trace_id": report["restart_trace_id"],
                "identity_before": "sha256:" + report["identity_before_sha256"],
                "identity_after": "sha256:" + report["identity_after_sha256"],
                "session_restored": True,
            },
        }

    if _remember_fact_ok(report):
        acceptance["remember_fact"] = {
            "status": "complete",
            "captured_at": report["timestamp"],
            "source": "freyja6-restart-evidence",
            "evidence": {
                "stored_fact_label": report["stored_fact_label"],
                "recall_trace_id": report["memory_recall_trace_id"],
                "memory_provider": report["memory_provider"],
            },
        }

    if _reboot_return_ok(report, payload):
        acceptance["atlas_reboot_return"] = {
            "status": "complete",
            "captured_at": report["timestamp"],
            "source": "freyja6-restart-evidence",
            "evidence": {
                "reboot_window": report["reboot_window"],
                "container_status_after": report["container_status_after"],
                "discord_reply_after_reboot": report["discord_reply_after_reboot"],
                "discord_reply_after_reboot_verification": report["discord_reply_after_reboot_verification"],
            },
        }

    payload["last_restart_evidence"] = report
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def append_logs(log_root: Path, report: dict[str, Any], existing_evidence: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    log_root.mkdir(parents=True, exist_ok=True)
    acceptance_log = log_root / "freyja-test-acceptance.jsonl"
    writes: list[dict[str, Any]] = []
    completed: list[tuple[str, str]] = []
    if _restart_identity_ok(report):
        completed.append(("restart_identity_session", str(report["restart_trace_id"])))
    if _remember_fact_ok(report):
        completed.append(("remember_fact", str(report["memory_recall_trace_id"])))
    if _reboot_return_ok(report, existing_evidence):
        completed.append(("atlas_reboot_return", str(report["discord_reply_after_reboot"])))
    for acceptance_id, trace_id in completed:
        entry = {
            "timestamp": report["timestamp"],
            "event": "acceptance",
            "trace_id": trace_id,
            "acceptance_id": acceptance_id,
            "status": "ok",
            "source": "freyja6-restart-evidence",
        }
        _append_jsonl(acceptance_log, entry)
        writes.append({"log": _redact_log_path(acceptance_log), "trace_id": entry["trace_id"], "acceptance_id": acceptance_id})
    return writes


def preflight_log_writes(log_root: Path) -> None:
    _check_append_path(log_root / "freyja-test-acceptance.jsonl")


def _restart_report_ok(report: dict[str, Any], existing_evidence: dict[str, Any] | None = None) -> bool:
    return (
        _restart_identity_ok(report)
        and _remember_fact_ok(report)
        and _reboot_return_ok(report, existing_evidence)
    )


def _restart_identity_ok(report: dict[str, Any]) -> bool:
    before_hash = str(report.get("identity_before_sha256") or "")
    after_hash = str(report.get("identity_after_sha256") or "")
    restart_trace = str(report.get("restart_trace_id") or "")
    return (
        bool(report.get("identity_matches_before"))
        and bool(report.get("session_restored"))
        and _hash_is_sha256(before_hash)
        and _hash_is_sha256(after_hash)
        and before_hash == after_hash
        and _trace_id_is_validation_trace(restart_trace)
    )


def _remember_fact_ok(report: dict[str, Any]) -> bool:
    stored_fact_label = str(report.get("stored_fact_label") or "")
    return (
        bool(report.get("memory_fact_present"))
        and bool(report.get("memory_fact_recalled"))
        and _safe_local_identifier(stored_fact_label)
        and report.get("memory_provider") == "hermes-native"
        and _memory_recall_ok(str(report.get("memory_recall_trace_id") or ""), str(report.get("restart_trace_id") or ""))
    )


def _hash_is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


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


def _sha256_file(path: Path) -> str:
    import hashlib

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _normalize_hash(value: str) -> str:
    value = value.strip()
    if value.startswith("sha256:"):
        return value.split(":", 1)[1]
    return value


def _session_restored(sessions_dir: Path, session_id: str) -> bool:
    return _session_marker_valid(sessions_dir, session_id)


def _session_marker_valid(sessions_dir: Path, session_id: str) -> bool:
    if not session_id:
        return False
    payload = _load_json_file(sessions_dir / session_id)
    if not payload:
        return False
    return (
        payload.get("schema_version") == "1.0"
        and payload.get("type") == "freyja6-validation-session-marker"
        and payload.get("agent_id") == AGENT_ID
        and payload.get("session_id") == session_id
    )


def _any_session_exists(sessions_dir: Path) -> bool:
    try:
        return any(sessions_dir.iterdir())
    except OSError:
        return False


def _latest_session_name(sessions_dir: Path) -> str:
    try:
        sessions = sorted(sessions_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return ""
    return sessions[0].name if sessions else ""


def _memory_fact_valid(path: Path, label: str) -> bool:
    if not _safe_local_identifier(label):
        return False
    payload = _load_json_file(path)
    if not payload:
        return False
    return (
        payload.get("schema_version") == "1.0"
        and payload.get("type") == "freyja6-validation-memory-fact"
        and payload.get("agent_id") == AGENT_ID
        and payload.get("label") == label
    )


def _safe_local_identifier(value: str) -> bool:
    text = str(value).strip()
    if not text or text in {".", ".."}:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return all(character in allowed for character in text)


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _container_status(*, container_status: str, container_status_json: Path | None) -> str:
    if container_status.strip():
        return _redact_status(container_status)
    if not container_status_json:
        return ""
    try:
        payload = json.loads(container_status_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or item.get("Service") or item.get("name") or item.get("service") or "")
        if name and "hermes-freyja-test" not in name:
            continue
        for key in ("Health", "State", "Status", "status"):
            if item.get(key):
                return _redact_status(str(item[key]))
    return ""


def _redact_status(value: str) -> str:
    return " ".join(value.strip().split())[:120]


def _container_is_ok(status: str) -> bool:
    lowered = status.lower()
    if any(marker in lowered for marker in ("exited", "dead", "created", "paused", "restarting", "not running", "unhealthy", "not healthy")):
        return False
    return lowered in {"running", "healthy", "up"} or lowered.startswith("running ") or "running (" in lowered


def _reboot_return_ok(report: dict[str, Any], existing_evidence: dict[str, Any] | None = None) -> bool:
    reply_trace = str(report.get("discord_reply_after_reboot") or "")
    restart_trace = str(report.get("restart_trace_id") or "")
    initial_reply = _initial_discord_reply_trace(existing_evidence or {})
    return (
        bool(report.get("reboot_window"))
        and _container_is_ok(str(report.get("container_status_after", "")))
        and _trace_id_is_validation_trace(reply_trace)
        and reply_trace != restart_trace
        and (not initial_reply or reply_trace != initial_reply)
        and report.get("discord_reply_after_reboot_verification") == "discord-api"
    )


def _memory_recall_ok(memory_recall_trace_id: str, restart_trace_id: str) -> bool:
    return _trace_id_is_validation_trace(memory_recall_trace_id) and memory_recall_trace_id != restart_trace_id


def _initial_discord_reply_trace(existing_evidence: dict[str, Any]) -> str:
    acceptance = existing_evidence.get("acceptance")
    if not isinstance(acceptance, dict):
        return ""
    discord = acceptance.get("discord_reply")
    payload = discord.get("evidence") if isinstance(discord, dict) and isinstance(discord.get("evidence"), dict) else {}
    return str(payload.get("reply_trace_id") or "")


def _trace_id_is_validation_trace(trace_id: str) -> bool:
    trace = trace_id.strip()
    return "..." not in trace and (trace.startswith("trace-") or trace.startswith("freyja6-"))


def _reboot_window(start: str, end: str) -> str:
    if not start or not end:
        return ""
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
    except ValueError:
        return ""
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        return ""
    if end_time.tzinfo is None or end_time.utcoffset() is None:
        return ""
    if end_time <= start_time:
        return ""
    now = datetime.now(timezone.utc)
    if start_time.astimezone(timezone.utc) > now or end_time.astimezone(timezone.utc) > now:
        return ""
    return f"{start}/{end}"


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
    try:
        existing_evidence = _load_evidence(args.evidence)
        _acceptance_map(existing_evidence)
        preflight_log_writes(args.log_root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    report = collect_evidence(
        hermes_data=args.hermes_data,
        log_root=args.log_root,
        before_identity_sha256=args.before_identity_sha256,
        session_id=args.session_id,
        stored_fact_label=args.stored_fact_label,
        memory_recall_trace_id=args.memory_recall_trace_id,
        memory_fact_file=args.memory_fact_file,
        container_status=args.container_status,
        container_status_json=args.container_status_json,
        reboot_start=args.reboot_start,
        reboot_end=args.reboot_end,
        discord_reply_trace_id=args.discord_reply_trace_id,
        discord_reply_verification=args.discord_reply_verification,
    )
    try:
        update_evidence(args.evidence, report)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc), "report": report}, indent=2, sort_keys=True))
        return 2
    log_writes = append_logs(args.log_root, report, existing_evidence)
    ok = _restart_report_ok(report, existing_evidence)
    print(json.dumps({"ok": ok, "evidence": str(args.evidence), "log_writes": log_writes, "report": report}, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
