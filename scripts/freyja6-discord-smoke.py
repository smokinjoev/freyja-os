#!/usr/bin/env python3
"""Verify a Freyja 6 Discord reply and record redacted evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
REQUIRED_MANUAL_CONFIRMATION = "DISCORD_REPLY_VERIFIED"
DISCORD_API = "https://discord.com/api/v10"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Freyja 6 Discord reply evidence.")
    parser.add_argument("--bot-token", default=os.environ.get("FREYJA6_DISCORD_BOT_TOKEN", ""))
    parser.add_argument("--channel-id", default=os.environ.get("FREYJA6_DISCORD_CHANNEL_ID", ""))
    parser.add_argument("--message-id", default=os.environ.get("FREYJA6_DISCORD_SMOKE_MESSAGE_ID", ""))
    parser.add_argument("--reply-id", default=os.environ.get("FREYJA6_DISCORD_SMOKE_REPLY_ID", ""))
    parser.add_argument("--message-trace-id", default="")
    parser.add_argument("--reply-trace-id", default="")
    parser.add_argument("--manual-confirmation", default="")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def run_smoke(
    *,
    bot_token: str,
    channel_id: str,
    message_id: str,
    reply_id: str,
    message_trace_id: str,
    reply_trace_id: str,
    manual_confirmation: str,
    timeout: float,
) -> dict[str, Any]:
    trace_id = f"freyja6-discord-{uuid.uuid4().hex[:12]}"
    has_explicit_message_trace = bool(message_trace_id.strip())
    has_explicit_reply_trace = bool(reply_trace_id.strip())
    base = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "channel_id_redacted": _redact_channel_id(channel_id),
        "message_trace_id": message_trace_id or f"{trace_id}-message",
        "reply_trace_id": reply_trace_id or f"{trace_id}-reply",
        "verification": "discord-api" if bot_token else "manual",
    }

    if not channel_id.strip():
        return {**base, "ok": False, "error": "--channel-id or FREYJA6_DISCORD_CHANNEL_ID is required."}
    if not message_id.strip() and not message_trace_id.strip():
        return {**base, "ok": False, "error": "--message-id or --message-trace-id is required."}
    if not reply_id.strip() and not reply_trace_id.strip():
        return {**base, "ok": False, "error": "--reply-id or --reply-trace-id is required."}

    if bot_token and message_id and reply_id:
        return {**base, **_verify_with_discord_api(bot_token, channel_id, message_id, reply_id, timeout=timeout)}

    if manual_confirmation == REQUIRED_MANUAL_CONFIRMATION and not (has_explicit_message_trace and has_explicit_reply_trace):
        return {
            **base,
            "ok": False,
            "error": "Manual Discord confirmation requires explicit --message-trace-id and --reply-trace-id values.",
        }
    if manual_confirmation == REQUIRED_MANUAL_CONFIRMATION:
        return {**base, "ok": True, "verification": "manual-confirmed", "manual_confirmation": REQUIRED_MANUAL_CONFIRMATION}
    return {
        **base,
        "ok": False,
        "error": f"Discord API verification requires token and message/reply IDs, or --manual-confirmation {REQUIRED_MANUAL_CONFIRMATION!r}.",
    }


def update_evidence(path: Path, smoke: dict[str, Any]) -> dict[str, Any]:
    payload = _load_evidence(path)
    acceptance = _acceptance_map(payload)
    if _discord_reply_ok(smoke):
        acceptance["discord_reply"] = {
            "status": "complete",
            "captured_at": smoke["timestamp"],
            "source": "freyja6-discord-smoke",
            "evidence": {
                "discord_channel_id_redacted": smoke["channel_id_redacted"],
                "message_trace_id": smoke["message_trace_id"],
                "reply_trace_id": smoke["reply_trace_id"],
                "verification_method": smoke["verification"],
            },
        }
    payload["last_discord_smoke"] = smoke
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def append_logs(log_root: Path, smoke: dict[str, Any]) -> list[dict[str, Any]]:
    if not _discord_reply_ok(smoke):
        return []
    log_root.mkdir(parents=True, exist_ok=True)
    acceptance_log = log_root / "freyja-test-acceptance.jsonl"
    entry = {
        "timestamp": smoke["timestamp"],
        "event": "acceptance",
        "trace_id": smoke["reply_trace_id"],
        "acceptance_id": "discord_reply",
        "status": "ok",
        "source": "freyja6-discord-smoke",
    }
    _append_jsonl(acceptance_log, entry)
    return [{"log": _redact_log_path(acceptance_log), "trace_id": entry["trace_id"]}]


def preflight_log_writes(log_root: Path) -> None:
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


def _discord_reply_ok(smoke: dict[str, Any]) -> bool:
    message_trace_id = str(smoke.get("message_trace_id") or "")
    reply_trace_id = str(smoke.get("reply_trace_id") or "")
    return (
        smoke.get("ok") is True
        and str(smoke.get("channel_id_redacted") or "").startswith("discord-channel-")
        and bool(message_trace_id)
        and bool(reply_trace_id)
        and message_trace_id != reply_trace_id
        and _trace_id_is_validation_trace(message_trace_id)
        and _trace_id_is_validation_trace(reply_trace_id)
        and smoke.get("verification") == "discord-api"
        and smoke.get("message_from_user") is True
        and smoke.get("reply_from_bot") is True
        and smoke.get("reply_references_message") is True
        and smoke.get("chronological") is True
    )


def _redact_log_path(path: Path) -> str:
    return f"freyja6/logs/{path.name}"


def _verify_with_discord_api(token: str, channel_id: str, message_id: str, reply_id: str, *, timeout: float) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Freyja6Validation/1.0 (+local)",
    }
    with httpx.Client(base_url=DISCORD_API, headers=headers, timeout=timeout) as client:
        message_response = client.get(f"/channels/{channel_id}/messages/{message_id}")
        reply_response = client.get(f"/channels/{channel_id}/messages/{reply_id}")
    message = _safe_json(message_response)
    reply = _safe_json(reply_response)
    if message_response.status_code >= 400 or reply_response.status_code >= 400:
        return {
            "ok": False,
            "status_code": max(message_response.status_code, reply_response.status_code),
            "error": "Could not read one or both Discord messages.",
        }
    if not isinstance(message, dict) or not isinstance(reply, dict):
        return {"ok": False, "error": "Discord returned an unexpected message payload."}

    message_ts = str(message.get("timestamp") or "")
    reply_ts = str(reply.get("timestamp") or "")
    message_author = message.get("author") if isinstance(message.get("author"), dict) else {}
    reply_author = reply.get("author") if isinstance(reply.get("author"), dict) else {}
    reply_reference = reply.get("referenced_message") if isinstance(reply.get("referenced_message"), dict) else {}
    references_message = str(reply_reference.get("id") or "") == message_id
    chronological = _reply_is_chronological(message_ts, reply_ts)
    message_from_user = bool(message_author) and message_author.get("bot") is not True
    reply_from_bot = reply_author.get("bot") is True
    ok = chronological and message_from_user and reply_from_bot and references_message
    return {
        "ok": ok,
        "status_code": 200,
        "message_from_user": message_from_user,
        "reply_from_bot": reply_from_bot,
        "reply_references_message": references_message,
        "chronological": chronological,
    }


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {}


def _reply_is_chronological(message_ts: str, reply_ts: str) -> bool:
    try:
        message_time = datetime.fromisoformat(message_ts.replace("Z", "+00:00"))
        reply_time = datetime.fromisoformat(reply_ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if message_time.tzinfo is None or reply_time.tzinfo is None:
        return False
    return reply_time >= message_time


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


def _redact_channel_id(channel_id: str) -> str:
    value = channel_id.strip()
    if len(value) <= 4:
        return "discord-channel-redacted"
    return "discord-channel-..." + value[-4:]


def _redact_snowflake(value: str, *, prefix: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return f"{prefix}-redacted"
    return f"{prefix}-...{value[-4:]}"


def _trace_id_is_validation_trace(trace_id: str) -> bool:
    trace = trace_id.strip()
    return "..." not in trace and (trace.startswith("trace-") or trace.startswith("freyja6-"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _acceptance_map(_load_evidence(args.evidence))
        preflight_log_writes(args.log_root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    smoke = run_smoke(
        bot_token=args.bot_token,
        channel_id=args.channel_id,
        message_id=args.message_id,
        reply_id=args.reply_id,
        message_trace_id=args.message_trace_id,
        reply_trace_id=args.reply_trace_id,
        manual_confirmation=args.manual_confirmation,
        timeout=args.timeout,
    )
    try:
        update_evidence(args.evidence, smoke)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc), "smoke": smoke}, indent=2, sort_keys=True))
        return 2
    log_writes = append_logs(args.log_root, smoke)
    ok = _discord_reply_ok(smoke)
    print(json.dumps({"ok": ok, "evidence": str(args.evidence), "log_writes": log_writes, "smoke": smoke}, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
