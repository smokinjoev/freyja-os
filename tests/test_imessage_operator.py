from __future__ import annotations

import importlib.util
from pathlib import Path

from connectors.imessage.config import IMessageSettings


REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_PATH = REPO_ROOT / "scripts" / "imessage-operator.py"


def _load_operator():
    spec = importlib.util.spec_from_file_location("imessage_operator", OPERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configured_recipients_are_sorted():
    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="+15550000002,+15550000001",
    )

    assert operator._configured_recipients(settings) == [
        "+15550000001",
        "+15550000002",
    ]


def test_broadcast_defaults_to_dry_run_without_sending():
    import asyncio

    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="+15550000001,+15550000002",
    )

    result = asyncio.run(operator._broadcast(settings, "hello", dry_run=True))

    assert result == {
        "status": "dry-run",
        "recipients": ["+15550000001", "+15550000002"],
        "recipient_count": 2,
        "sent": 0,
        "failed": 0,
    }


def test_send_to_command_uses_recipient_not_chat_id():
    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_imsg_path="/usr/local/bin/imsg",
        imessage_database_path="/tmp/chat.db",
    )

    command = operator._send_to_command(settings, "+15550000001", "hello")

    assert command == [
        "/usr/local/bin/imsg",
        "send",
        "--db",
        "/tmp/chat.db",
        "--to",
        "+15550000001",
        "--text",
        "hello",
        "--service",
        "imessage",
        "--json",
    ]
