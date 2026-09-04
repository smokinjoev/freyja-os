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
    assert report["ready"] is False
    assert report["checks"] == {
        "allowlist_configured": False,
        "identity_map_configured": False,
        "open_webui_api_key_configured": False,
        "telegram_bot_token_configured": False,
    }
    assert "TOKEN" not in str(report)


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
