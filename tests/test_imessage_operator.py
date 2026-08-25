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


def test_operator_script_is_executable() -> None:
    assert OPERATOR_PATH.stat().st_mode & 0o111


def test_operator_reexecs_under_repo_venv_for_direct_execution() -> None:
    source = OPERATOR_PATH.read_text(encoding="utf-8")

    assert "os.execv" in source
    assert ".venv" in source


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


def test_live_smoke_defaults_to_dry_run_for_first_allowlisted_recipient(monkeypatch):
    import asyncio

    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="+15550000002,+15550000001",
        imessage_imsg_path="/usr/local/bin/imsg",
        imessage_database_path="/tmp/chat.db",
    )
    monkeypatch.setattr(
        operator,
        "_resolve_live_smoke_recipient",
        lambda settings_arg, target, sender: (
            target,
            {"requested_recipient": target, "recipient_resolution": "configured-recipient"},
        ),
    )

    result = asyncio.run(
        operator._live_smoke(
            settings,
            recipient=None,
            text="Freyja 2.0 live smoke test.",
            dry_run=True,
        )
    )

    assert result["schema_version"] == "1.0"
    assert result["report_type"] == "imessage-live-smoke"
    assert result["dry_run"] is True
    assert result["status"] == "dry-run"
    assert result["plan"] == {
        "recipient": "+15550000001",
        "text": "Freyja 2.0 live smoke test.",
        "imsg_path": "/usr/local/bin/imsg",
        "database_path": "/tmp/chat.db",
        "requested_recipient": "+15550000001",
        "recipient_resolution": "configured-recipient",
    }
    assert result["sent"] == 0
    assert result["failed"] == 0


def test_live_smoke_rejects_non_allowlisted_recipient():
    import asyncio

    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="+15550000001",
    )

    result = asyncio.run(
        operator._live_smoke(
            settings,
            recipient="+15550000002",
            text="hello",
            dry_run=True,
        )
    )

    assert result["status"] == "error"
    assert result["error"] == "recipient is not in IMESSAGE_ALLOWED_SENDERS"
    assert result["sent"] == 0


def test_live_smoke_sends_only_when_not_dry_run(monkeypatch):
    import asyncio

    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="+15550000001",
    )
    sent = {}
    monkeypatch.setattr(
        operator,
        "_resolve_live_smoke_recipient",
        lambda settings_arg, target, sender: (
            target,
            {"requested_recipient": target, "recipient_resolution": "configured-recipient"},
        ),
    )

    async def fake_send_to(settings_arg, recipient, text):
        sent["recipient"] = recipient
        sent["text"] = text

    monkeypatch.setattr(operator, "_send_to", fake_send_to)

    result = asyncio.run(
        operator._live_smoke(
            settings,
            recipient="+15550000001",
            text="hello",
            dry_run=False,
        )
    )

    assert result["status"] == "sent"
    assert result["dry_run"] is False
    assert result["sent"] == 1
    assert sent == {"recipient": "+15550000001", "text": "hello"}


def test_send_to_reports_timeout(monkeypatch):
    import asyncio
    import subprocess

    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="+15550000001",
        imessage_send_timeout_seconds=0.01,
    )

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(operator.subprocess, "run", fake_run)

    try:
        asyncio.run(operator._send_to(settings, "+15550000001", "hello"))
    except operator.IMessageTransportError as exc:
        assert "imsg send timed out after 0.01s" in str(exc)
    else:
        raise AssertionError("expected timeout to fail")


def test_send_to_reports_stdout_when_stderr_is_empty(monkeypatch):
    import asyncio
    import subprocess

    operator = _load_operator()
    settings = IMessageSettings(_env_file=None, imessage_allowed_senders="+15550000001")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout='{"status":"failed"}\n', stderr="")

    monkeypatch.setattr(operator.subprocess, "run", fake_run)

    try:
        asyncio.run(operator._send_to(settings, "+15550000001", "hello"))
    except operator.IMessageTransportError as exc:
        assert "status 1" in str(exc)
        assert 'stdout={"status":"failed"}' in str(exc)
    else:
        raise AssertionError("expected failed send to raise")


def test_live_smoke_can_write_json_report(tmp_path, monkeypatch):
    operator = _load_operator()
    output = tmp_path / "smoke.json"
    monkeypatch.setattr(
        operator,
        "IMessageSettings",
        lambda: IMessageSettings(_env_file=None, imessage_allowed_senders="+15550000001"),
    )
    monkeypatch.setattr(
        operator,
        "_resolve_live_smoke_recipient",
        lambda settings_arg, target, sender: (
            target,
            {"requested_recipient": target, "recipient_resolution": "configured-recipient"},
        ),
    )

    result = operator.main(["live-smoke", "--dry-run", "--output", str(output)])

    assert result == 0
    assert output.exists()
    assert '"report_type": "imessage-live-smoke"' in output.read_text(encoding="utf-8")


def test_live_smoke_resolves_alias_to_known_contact_imessage_handle(monkeypatch):
    operator = _load_operator()
    settings = IMessageSettings(
        _env_file=None,
        imessage_allowed_senders="joe=joe@example.com",
    )

    monkeypatch.setattr(
        operator,
        "_imsg_whois_local",
        lambda settings_arg, address: {
            "known": address == "+15550000001",
            "service": "imessage" if address == "+15550000001" else "unknown",
        },
    )
    monkeypatch.setattr(
        operator,
        "_macagent_contacts",
        lambda: [
            {
                "display_name": "Joseph Verant",
                "aliases": [],
                "identities": [{"kind": "phone", "value": "+15550000001"}],
            }
        ],
    )

    sender = settings.allowed_sender_identities["joe@example.com"]
    resolved, evidence = operator._resolve_live_smoke_recipient(settings, "joe@example.com", sender)

    assert resolved == "+15550000001"
    assert evidence == {
        "requested_recipient": "joe@example.com",
        "recipient_resolution": "apple-contacts-local-imessage",
        "resolved_from_member": "joe",
        "resolved_contact": "Joseph Verant",
    }
