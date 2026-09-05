from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from freyja.channel_transports import TelegramInbound
from freyja.channels import ChannelMessage


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run-freyja-channels-telegram-pilot.py"


def _module():
    spec = importlib.util.spec_from_file_location("run_freyja_channels_telegram_pilot", SCRIPT)
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


class FakeTransport:
    def __init__(self, updates) -> None:
        self.updates = updates
        self.offsets = []
        self.sent = []

    def get_update_messages(self, *, offset=None):
        self.offsets.append(offset)
        return self.updates

    def send_message(self, *, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})


def test_telegram_pilot_dry_run_fails_closed_without_credentials(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OPEN_WEBUI_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_IDENTITY_MAP", raising=False)
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
        "telegram_bot_token_configured": False,
    }
    assert report["missing_configuration"] == [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USER_IDS",
        "TELEGRAM_IDENTITY_MAP",
        "OPEN_WEBUI_API_KEY",
    ]
    assert report["next_actions"] == [
        "Create or choose the Telegram bot and set TELEGRAM_BOT_TOKEN outside source control.",
        "Set TELEGRAM_ALLOWED_USER_IDS with reviewed family sender IDs; keep an empty allowlist as deny-all.",
        "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
        "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account.",
        "Rerun scripts/run-freyja-channels-telegram-pilot.py --dry-run and require ready=true before live polling.",
    ]
    assert "secret-token" not in str(report)


def test_telegram_pilot_requires_every_allowlisted_sender_to_have_identity(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("OPEN_WEBUI_API_KEY", "secret-key")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1001,1002")
    monkeypatch.setenv("TELEGRAM_IDENTITY_MAP", "1001:joe")
    output = tmp_path / "pilot.json"

    assert _module().main(["--dry-run", "--state-dir", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False
    assert report["checks"]["allowlist_configured"] is True
    assert report["checks"]["identity_map_configured"] is True
    assert report["checks"]["allowlist_identity_map_complete"] is False
    assert report["missing_configuration"] == ["TELEGRAM_IDENTITY_MAP:missing_allowlist_entries"]
    assert report["next_actions"] == [
        "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
        "Rerun scripts/run-freyja-channels-telegram-pilot.py --dry-run and require ready=true before live polling.",
    ]
    assert "secret-token" not in str(report)
    assert "secret-key" not in str(report)


def test_telegram_pilot_invalid_poll_interval_env_uses_default(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FREYJA_CHANNEL_TELEGRAM_POLL_INTERVAL", "not-a-number")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OPEN_WEBUI_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_IDENTITY_MAP", raising=False)
    output = tmp_path / "pilot.json"

    assert _module().main(["--dry-run", "--state-dir", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_telegram_pilot_nonpositive_poll_interval_env_uses_default(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_CHANNEL_TELEGRAM_POLL_INTERVAL", "0")

    args = _module().build_parser().parse_args([])

    assert args.poll_interval == 2.0


def test_telegram_pilot_run_once_sends_replies_and_advances_offset(tmp_path: Path) -> None:
    module = _module()
    service = FakeService()
    transport = FakeTransport(
        [
            TelegramInbound(
                update_id=41,
                message=ChannelMessage(channel="telegram", sender="1001", chat_id="2002", text="hello"),
            )
        ]
    )
    offset = tmp_path / "telegram.offset"

    result = module.run_once(service=service, transport=transport, offset_file=offset)

    assert result == {"updates": 1, "handled": 1, "denied_or_client_failed": 0, "failed": 0}
    assert transport.offsets == [None]
    assert transport.sent == [{"chat_id": "2002", "text": "reply:hello"}]
    assert offset.read_text(encoding="utf-8") == "42\n"


def test_telegram_pilot_run_once_reuses_existing_offset(tmp_path: Path) -> None:
    module = _module()
    offset = tmp_path / "telegram.offset"
    offset.write_text("99\n", encoding="utf-8")
    transport = FakeTransport([])

    result = module.run_once(service=FakeService(), transport=transport, offset_file=offset)

    assert result == {"updates": 0, "handled": 0, "denied_or_client_failed": 0, "failed": 0}
    assert transport.offsets == [99]
    assert offset.read_text(encoding="utf-8") == "99\n"
