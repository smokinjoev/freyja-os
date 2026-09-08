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

    def enrich_attachments(self, message):
        if message.attachments:
            return ChannelMessage(
                channel=message.channel,
                sender=message.sender,
                text=message.text,
                requested_agent=message.requested_agent,
                chat_id=message.chat_id,
                attachments=(*message.attachments, {"kind": "test-enriched"}),
            )
        return message

    def send_message(self, *, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})


class SequencedTransport(FakeTransport):
    def __init__(self, batches) -> None:
        super().__init__([])
        self.batches = list(batches)

    def get_update_messages(self, *, offset=None):
        self.offsets.append(offset)
        return self.batches.pop(0) if self.batches else []


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
        "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control.",
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


def test_telegram_pilot_dry_run_accepts_configured_separate_bot_profile(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_IDENTITY_MAP", raising=False)
    monkeypatch.setenv("OPEN_WEBUI_API_KEY", "secret-key")
    monkeypatch.setenv("TELEGRAM_BOT_PROFILES", "CLOYD_JOE")
    monkeypatch.setenv("TELEGRAM_CLOYD_JOE_BOT_TOKEN", "secret-cloyd-token")
    monkeypatch.setenv("TELEGRAM_CLOYD_JOE_ALLOWED_USER_IDS", "1001")
    monkeypatch.setenv("TELEGRAM_CLOYD_JOE_IDENTITY_MAP", "1001:joe")
    monkeypatch.setenv("TELEGRAM_CLOYD_JOE_AGENT", "cloyd")
    output = tmp_path / "pilot.json"

    assert _module().main(["--dry-run", "--state-dir", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is True
    assert report["missing_configuration"] == []
    assert report["bot_profiles"] == [
        {
            "name": "CLOYD_JOE",
            "bot_token_configured": True,
            "allowlist_configured": True,
            "identity_map_configured": True,
            "allowlist_identity_map_complete": True,
            "forced_agent": "cloyd",
            "configured": True,
            "secrets_included": False,
        }
    ]
    assert "secret-cloyd-token" not in str(report)
    assert "1001" not in str(report)


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


def test_telegram_pilot_run_once_preserves_requested_agent_command(tmp_path: Path) -> None:
    module = _module()
    service = FakeService()
    transport = FakeTransport(
        [
            TelegramInbound(
                update_id=41,
                message=ChannelMessage(channel="telegram", sender="1001", chat_id="2002", text="check the repo", requested_agent="cloyd"),
            )
        ]
    )

    result = module.run_once(service=service, transport=transport, offset_file=tmp_path / "telegram.offset")

    assert result["handled"] == 1
    assert service.messages[0].requested_agent == "cloyd"
    assert service.messages[0].text == "check the repo"


def test_telegram_pilot_run_once_forced_agent_overrides_message_command(tmp_path: Path) -> None:
    module = _module()
    service = FakeService()
    transport = FakeTransport(
        [
            TelegramInbound(
                update_id=41,
                message=ChannelMessage(channel="telegram", sender="1001", chat_id="2002", text="try another agent", requested_agent="benedict"),
            )
        ]
    )

    result = module.run_once_forced_agent(
        service=service,
        transport=transport,
        offset_file=tmp_path / "telegram-cloyd.offset",
        forced_agent="cloyd",
    )

    assert result["handled"] == 1
    assert service.messages[0].requested_agent == "cloyd"


def test_telegram_pilot_run_once_enriches_attachments_before_routing(tmp_path: Path) -> None:
    module = _module()
    service = FakeService()
    transport = FakeTransport(
        [
            TelegramInbound(
                update_id=41,
                message=ChannelMessage(
                    channel="telegram",
                    sender="1001",
                    chat_id="2002",
                    text="see this",
                    attachments=({"kind": "image", "file_id": "photo"},),
                ),
            )
        ]
    )

    result = module.run_once(service=service, transport=transport, offset_file=tmp_path / "telegram.offset")

    assert result["handled"] == 1
    assert service.messages[0].attachments[-1] == {"kind": "test-enriched"}


def test_telegram_pilot_run_once_reuses_existing_offset(tmp_path: Path) -> None:
    module = _module()
    offset = tmp_path / "telegram.offset"
    offset.write_text("99\n", encoding="utf-8")
    transport = FakeTransport([])

    result = module.run_once(service=FakeService(), transport=transport, offset_file=offset)

    assert result == {"updates": 0, "handled": 0, "denied_or_client_failed": 0, "failed": 0}
    assert transport.offsets == [99]
    assert offset.read_text(encoding="utf-8") == "99\n"


def test_telegram_pilot_run_loop_until_handled_stops_after_reply(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    transport = SequencedTransport(
        [
            [],
            [
                TelegramInbound(
                    update_id=41,
                    message=ChannelMessage(channel="telegram", sender="1001", chat_id="2002", text="hello"),
                )
            ],
        ]
    )
    monkeypatch.setattr(module, "TelegramLongPollingTransport", lambda *_args, **_kwargs: transport)
    monkeypatch.setattr(module, "OpenWebUIChatClient", lambda: object())
    monkeypatch.setattr(module, "FreyjaChannels", lambda **kwargs: FakeService())
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1001")
    monkeypatch.setenv("TELEGRAM_IDENTITY_MAP", "1001:joe")
    args = module.build_parser().parse_args(["--state-dir", str(tmp_path), "--max-iterations", "5", "--until-handled", "--poll-interval", "0.1"])

    report = module.run_loop(args)

    assert report["ready"] is True
    assert report["live_round_trip_complete"] is True
    assert report["iterations"] == 2
    assert report["totals"]["handled"] == 1
    assert transport.sent == [{"chat_id": "2002", "text": "reply:hello"}]
