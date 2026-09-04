from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from freyja.channels import ChannelMessage


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run-freyja-channels-signal-pilot.py"


def _module():
    spec = importlib.util.spec_from_file_location("run_freyja_channels_signal_pilot", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeService:
    def __init__(self) -> None:
        self.messages = []

    def handle(self, message):
        self.messages.append(message)
        return f"reply:{message.text}"


class FakeSignalTransport:
    def __init__(self, messages) -> None:
        self.messages = messages
        self.sent = []

    def receive(self):
        return self.messages

    def send(self, *, recipient, text):
        self.sent.append({"recipient": recipient, "text": text})


def test_signal_pilot_dry_run_fails_closed_without_credentials(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("SIGNAL_ACCOUNT_NUMBER", raising=False)
    monkeypatch.delenv("SIGNAL_REST_API_URL", raising=False)
    monkeypatch.delenv("OPEN_WEBUI_API_KEY", raising=False)
    monkeypatch.delenv("SIGNAL_ALLOWED_SENDERS", raising=False)
    monkeypatch.delenv("SIGNAL_IDENTITY_MAP", raising=False)
    output = tmp_path / "pilot.json"

    assert _module().main(["--dry-run", "--state-dir", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["ready"] is False
    assert report["checks"] == {
        "allowlist_configured": False,
        "allowlist_identity_map_complete": False,
        "identity_map_configured": False,
        "open_webui_api_key_configured": False,
        "signal_account_configured": False,
        "signal_rest_api_configured": False,
    }


def test_signal_pilot_requires_every_allowlisted_sender_to_have_identity(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "+15550001000")
    monkeypatch.setenv("SIGNAL_REST_API_URL", "http://signal.local")
    monkeypatch.setenv("OPEN_WEBUI_API_KEY", "secret-key")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "+15550001002,+15550001003")
    monkeypatch.setenv("SIGNAL_IDENTITY_MAP", "+15550001002:beth")
    output = tmp_path / "pilot.json"

    assert _module().main(["--dry-run", "--state-dir", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False
    assert report["checks"]["allowlist_configured"] is True
    assert report["checks"]["identity_map_configured"] is True
    assert report["checks"]["allowlist_identity_map_complete"] is False
    assert "secret-key" not in str(report)
    assert "+15550001002" not in str(report)


def test_signal_pilot_invalid_poll_interval_env_uses_default(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FREYJA_CHANNEL_SIGNAL_POLL_INTERVAL", "not-a-number")
    monkeypatch.delenv("SIGNAL_ACCOUNT_NUMBER", raising=False)
    monkeypatch.delenv("SIGNAL_REST_API_URL", raising=False)
    monkeypatch.delenv("OPEN_WEBUI_API_KEY", raising=False)
    monkeypatch.delenv("SIGNAL_ALLOWED_SENDERS", raising=False)
    monkeypatch.delenv("SIGNAL_IDENTITY_MAP", raising=False)
    output = tmp_path / "pilot.json"

    assert _module().main(["--dry-run", "--state-dir", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_signal_pilot_nonpositive_poll_interval_env_uses_default(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_CHANNEL_SIGNAL_POLL_INTERVAL", "-1")

    args = _module().build_parser().parse_args([])

    assert args.poll_interval == 5.0


def test_signal_pilot_run_once_sends_replies() -> None:
    module = _module()
    service = FakeService()
    transport = FakeSignalTransport([ChannelMessage(channel="signal", sender="+15550001002", chat_id="uuid-1", text="hello")])

    result = module.run_once(service=service, transport=transport)

    assert result == {"messages": 1, "handled": 1, "denied_or_client_failed": 0, "failed": 0}
    assert transport.sent == [{"recipient": "+15550001002", "text": "reply:hello"}]
