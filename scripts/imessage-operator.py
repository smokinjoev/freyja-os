#!/usr/bin/env python3
"""Small operator CLI for the native iMessage connector."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = str(_PROJECT_ROOT / "src")
_ROOT_DIR = str(_PROJECT_ROOT)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(1, _ROOT_DIR)

from connectors.imessage.config import IMessageSettings  # noqa: E402
from connectors.imessage.transport import IMessageTransportError  # noqa: E402


def _configured_recipients(settings: IMessageSettings) -> list[str]:
    return sorted(settings.allowed_sender_set)


def _send_to_command(settings: IMessageSettings, recipient: str, text: str) -> list[str]:
    return [
        settings.resolved_imsg_path,
        "send",
        "--db",
        settings.imessage_database_path,
        "--to",
        recipient,
        "--text",
        text,
        "--service",
        "imessage",
        "--json",
    ]


async def _send_to(settings: IMessageSettings, recipient: str, text: str) -> None:
    process = await asyncio.create_subprocess_exec(
        *_send_to_command(settings, recipient, text),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=settings.imessage_send_timeout_seconds,
    )
    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise IMessageTransportError(
            f"imsg send failed for configured recipient with status {process.returncode}"
            + (f": {detail}" if detail else "")
        )


async def _broadcast(
    settings: IMessageSettings,
    text: str,
    *,
    dry_run: bool,
) -> dict[str, object]:
    recipients = _configured_recipients(settings)
    if not recipients:
        return {"status": "error", "error": "allowlist is empty", "sent": 0, "failed": 0}

    if dry_run:
        return {
            "status": "dry-run",
            "recipients": recipients,
            "recipient_count": len(recipients),
            "sent": 0,
            "failed": 0,
        }

    sent = 0
    failures: list[dict[str, str]] = []
    for recipient in recipients:
        try:
            await _send_to(settings, recipient, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - operator summary should continue per recipient
            failures.append({"recipient": recipient, "error": str(exc)})

    return {
        "status": "sent" if not failures else "partial",
        "recipient_count": len(recipients),
        "sent": sent,
        "failed": len(failures),
        "failures": failures,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the native iMessage connector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("allowlist", help="Print configured allowlist recipients")

    broadcast = subparsers.add_parser(
        "broadcast",
        help="Broadcast an operator-authored iMessage to the configured allowlist",
    )
    broadcast.add_argument("--text", required=True, help="Message text to send")
    broadcast.add_argument(
        "--yes",
        action="store_true",
        help="Actually send the broadcast. Without this flag, the command is a dry-run.",
    )
    broadcast.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview recipients without sending. This is the default.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = IMessageSettings()

    if args.command == "allowlist":
        print(
            json.dumps(
                {
                    "status": "ok",
                    "recipients": _configured_recipients(settings),
                    "recipient_count": len(_configured_recipients(settings)),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "broadcast":
        dry_run = args.dry_run or not args.yes
        result = asyncio.run(_broadcast(settings, args.text, dry_run=dry_run))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in {"dry-run", "sent"} else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
