#!/usr/bin/env python3
"""Small operator CLI for the native iMessage connector."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and Path(sys.executable) != _VENV_PYTHON:
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])

_SRC_DIR = str(_PROJECT_ROOT / "src")
_ROOT_DIR = str(_PROJECT_ROOT)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(1, _ROOT_DIR)

import httpx  # noqa: E402
from connectors.imessage.config import IMessageSettings  # noqa: E402
from connectors.imessage.transport import IMessageTransportError  # noqa: E402
from connectors.messaging import AuthorizedSender, household_agent_for_sender  # noqa: E402
from freyja.config import settings as freyja_settings  # noqa: E402
from freyja.identity import default_identity_service  # noqa: E402
from freyja.identity import person_from_legacy_member  # noqa: E402


def _configured_recipients(settings: IMessageSettings) -> list[str]:
    return sorted(settings.allowed_sender_set)


def _configured_senders(settings: IMessageSettings) -> dict[str, AuthorizedSender]:
    return settings.allowed_sender_identities


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
    command = _send_to_command(settings, recipient, text)
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            command,
            text=True,
            capture_output=True,
            timeout=settings.imessage_send_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise IMessageTransportError(
            f"imsg send timed out after {settings.imessage_send_timeout_seconds:.2f}s"
        ) from exc
    if completed.returncode:
        output = completed.stdout.strip()
        detail = completed.stderr.strip()
        diagnostics = []
        if detail:
            diagnostics.append(f"stderr={detail}")
        if output:
            diagnostics.append(f"stdout={output}")
        raise IMessageTransportError(
            f"imsg send failed for configured recipient with status {completed.returncode}"
            + (f": {'; '.join(diagnostics)}" if diagnostics else "")
        )


def _imsg_whois_local(settings: IMessageSettings, address: str) -> dict[str, Any]:
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
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=max(1.0, settings.imessage_command_timeout_seconds),
        check=False,
    )
    if completed.returncode:
        return {"known": False, "service": "unknown", "error": (completed.stderr or completed.stdout).strip()}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"known": False, "service": "unknown", "error": "invalid imsg whois output"}
    return payload if isinstance(payload, dict) else {"known": False, "service": "unknown"}


def _known_imessage_handle(settings: IMessageSettings, address: str) -> bool:
    payload = _imsg_whois_local(settings, address)
    return payload.get("known") is True and str(payload.get("service", "")).lower() == "imessage"


def _safe_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _macagent_contacts(*, include_identifiers: bool = True, limit: int = 1000) -> list[dict[str, Any]]:
    base_url = freyja_settings.macagent_base_url.rstrip("/")
    token = freyja_settings.macagent_token.strip()
    if not base_url or not token:
        return []
    request = {
        "capability": "apple.contacts.read",
        "operation": "list_contacts",
        "arguments": {"include_identifiers": include_identifiers, "limit": limit},
        "request_id": "imessage-live-smoke-contact-resolution",
        "actor": "imessage-operator",
        "director_authorized": True,
        "approval_granted": False,
    }
    response = httpx.post(
        f"{base_url}/capabilities/apple.contacts.read",
        headers={"Authorization": f"Bearer {token}"},
        json=request,
        timeout=max(1.0, freyja_settings.macagent_timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return []
    contacts = (payload.get("output") or {}).get("contacts")
    return [contact for contact in contacts if isinstance(contact, dict)] if isinstance(contacts, list) else []


def _normalized_words(value: object) -> set[str]:
    text = str(value or "").lower()
    return {"".join(char for char in part if char.isalnum()) for part in text.replace("-", " ").split() if part}


def _sender_name_words(sender: AuthorizedSender) -> set[str]:
    words = _normalized_words(sender.member_id)
    person = sender.person
    seeded_person = default_identity_service().resolve(sender.member_id) if sender.member_id else None
    if person is None and sender.member_id:
        person = seeded_person or person_from_legacy_member(sender.member_id)
    if person is not None:
        words.update(_normalized_words(person.person_id))
        words.update(_normalized_words(person.display_name))
        words.update(_normalized_words(person.preferred_name))
        for alias in person.aliases:
            words.update(_normalized_words(alias.value))
    if seeded_person is not None and seeded_person != person:
        words.update(_normalized_words(seeded_person.person_id))
        words.update(_normalized_words(seeded_person.display_name))
        words.update(_normalized_words(seeded_person.preferred_name))
        for alias in seeded_person.aliases:
            words.update(_normalized_words(alias.value))
    return {word for word in words if word}


def _contact_matches_sender(contact: dict[str, Any], sender: AuthorizedSender) -> bool:
    wanted = _sender_name_words(sender)
    if not wanted:
        return False
    contact_words = _normalized_words(contact.get("display_name"))
    contact_words.update(_normalized_words(contact.get("preferred_name")))
    for alias in contact.get("aliases") or []:
        if isinstance(alias, dict):
            contact_words.update(_normalized_words(alias.get("value")))
    return bool(wanted & contact_words)


def _contact_identity_values(contact: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for preferred_kind in ("phone", "imessage", "email"):
        for identity in contact.get("identities") or []:
            if not isinstance(identity, dict) or identity.get("kind") != preferred_kind:
                continue
            value = identity.get("value")
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return values


def _resolve_live_smoke_recipient(
    settings: IMessageSettings,
    target: str,
    sender: AuthorizedSender | None,
) -> tuple[str, dict[str, object]]:
    resolution: dict[str, object] = {
        "requested_recipient": target,
        "recipient_resolution": "configured-recipient",
    }
    if _known_imessage_handle(settings, target):
        return target, resolution
    if sender is None or not sender.member_id:
        raise IMessageTransportError("configured recipient is not locally known as an iMessage handle")

    try:
        contacts = _macagent_contacts()
    except Exception as exc:  # noqa: BLE001 - smoke report should explain contact resolution failure
        raise IMessageTransportError(f"configured recipient is not locally known and contact resolution failed: {exc}") from exc

    for contact in contacts:
        if not _contact_matches_sender(contact, sender):
            continue
        for value in _contact_identity_values(contact):
            if _known_imessage_handle(settings, value):
                resolution.update(
                    {
                        "recipient_resolution": "apple-contacts-local-imessage",
                        "resolved_from_member": sender.member_id,
                        "resolved_contact": contact.get("display_name"),
                    }
                )
                return value, resolution
    raise IMessageTransportError("configured recipient is not locally known and no matching contact iMessage handle was found")


async def _broadcast(
    settings: IMessageSettings,
    text: str,
    *,
    dry_run: bool,
) -> dict[str, object]:
    recipients = _configured_recipients(settings)
    if not recipients:
        return _smoke_report({"status": "error", "error": "allowlist is empty", "sent": 0, "failed": 0}, dry_run=dry_run)

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


def _identity_audit(settings: IMessageSettings) -> dict[str, object]:
    senders = _configured_senders(settings)
    people: dict[str, dict[str, object]] = {
        person_id: {"mapped": False, "sender_count": 0, "agent_id": None}
        for person_id in ("joe", "beth", "liam", "jenna")
    }
    unmapped = 0
    senders_report = []
    for address, sender in sorted(senders.items()):
        agent = household_agent_for_sender(sender)
        person_id = (sender.member_id or "").strip().lower() or None
        if person_id in people:
            people[person_id] = {
                "mapped": True,
                "sender_count": int(people[person_id]["sender_count"]) + 1,
                "agent_id": agent.agent_id,
            }
        else:
            unmapped += 1
        whois = _imsg_whois_local(settings, address)
        senders_report.append(
            {
                "sender_hash": _safe_hash(address),
                "person_id": person_id,
                "agent_id": agent.agent_id,
                "locally_known_imessage": whois.get("known") is True and str(whois.get("service", "")).lower() == "imessage",
                "service": whois.get("service", "unknown"),
            }
        )
    missing_people = [person_id for person_id, item in people.items() if not item["mapped"]]
    return {
        "schema_version": "1.0",
        "report_type": "imessage-identity-audit",
        "timestamp": datetime.now(UTC).isoformat(),
        "ok": not missing_people,
        "allowed_sender_count": len(senders),
        "unmapped_sender_count": unmapped,
        "missing_people": missing_people,
        "people": people,
        "senders": senders_report,
        "raw_addresses_redacted": True,
    }


async def _live_smoke(
    settings: IMessageSettings,
    *,
    recipient: str | None,
    text: str,
    dry_run: bool,
) -> dict[str, object]:
    senders = _configured_senders(settings)
    recipients = sorted(senders)
    if not senders:
        return {"status": "error", "error": "allowlist is empty", "sent": 0, "failed": 0}
    target = recipient or recipients[0]
    if target not in senders:
        return _smoke_report({
            "status": "error",
            "error": "recipient is not in IMESSAGE_ALLOWED_SENDERS",
            "recipient": target,
            "allowed_recipients": recipients,
            "sent": 0,
            "failed": 0,
        }, dry_run=dry_run)
    sender = senders[target]
    try:
        resolved_target, resolution = _resolve_live_smoke_recipient(settings, target, sender)
    except Exception as exc:  # noqa: BLE001 - operator JSON should report reachability failures
        return _smoke_report(
            {
                "status": "failed" if not dry_run else "error",
                "recipient": target,
                "sent": 0,
                "failed": 1 if not dry_run else 0,
                "error": str(exc),
            },
            dry_run=dry_run,
        )
    plan = {
        "recipient": resolved_target,
        "text": text,
        "imsg_path": settings.resolved_imsg_path,
        "database_path": settings.imessage_database_path,
        **resolution,
    }
    if dry_run:
        return _smoke_report({"status": "dry-run", "plan": plan, "sent": 0, "failed": 0}, dry_run=True)
    try:
        await _send_to(settings, resolved_target, text)
    except Exception as exc:  # noqa: BLE001 - operator JSON should report the send failure
        return _smoke_report({"status": "failed", "plan": plan, "sent": 0, "failed": 1, "error": str(exc)}, dry_run=False)
    return _smoke_report({"status": "sent", "plan": plan, "sent": 1, "failed": 0}, dry_run=False)


def _smoke_report(result: dict[str, object], *, dry_run: bool) -> dict[str, object]:
    report = {
        "schema_version": "1.0",
        "report_type": "imessage-live-smoke",
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "sent": 0,
        "failed": 0,
    }
    report.update(result)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the native iMessage connector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("allowlist", help="Print configured allowlist recipients")

    identity_audit = subparsers.add_parser(
        "identity-audit",
        help="Print a redacted iMessage family identity routing audit without sending.",
    )
    identity_audit.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path.",
    )

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

    smoke = subparsers.add_parser(
        "live-smoke",
        help="Send one operator-approved iMessage smoke test to an allowlisted recipient.",
    )
    smoke.add_argument(
        "--recipient",
        help="Allowlisted recipient to send to. Defaults to the first configured recipient.",
    )
    smoke.add_argument(
        "--text",
        default="Freyja 2.0 live smoke test.",
        help="Smoke-test message text.",
    )
    smoke.add_argument(
        "--yes",
        action="store_true",
        help="Actually send the smoke message. Without this flag, the command is a dry-run.",
    )
    smoke.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the exact smoke message without sending. This is the default.",
    )
    smoke.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path for readiness evidence.",
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

    if args.command == "identity-audit":
        result = _identity_audit(settings)
        rendered = json.dumps(result, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if result["ok"] else 1

    if args.command == "broadcast":
        dry_run = args.dry_run or not args.yes
        result = asyncio.run(_broadcast(settings, args.text, dry_run=dry_run))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in {"dry-run", "sent"} else 1

    if args.command == "live-smoke":
        dry_run = args.dry_run or not args.yes
        result = asyncio.run(
            _live_smoke(
                settings,
                recipient=args.recipient,
                text=args.text,
                dry_run=dry_run,
            )
        )
        rendered = json.dumps(result, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if result["status"] in {"dry-run", "sent"} else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
