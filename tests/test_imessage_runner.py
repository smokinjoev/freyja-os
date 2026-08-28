from __future__ import annotations

import importlib.util
from pathlib import Path

from connectors.imessage.config import IMessageSettings
from connectors.imessage.gateway import IMessageGateway
from connectors.imessage.models import IMessage, IMessageReply
from connectors.imessage.transport import _database_message_text


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run-imessage-connector.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("imessage_runner", RUNNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_not_ready_when_gateway_disabled(tmp_path):
    runner = _load_runner()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(tmp_path / "chat.db"),
        imessage_allowed_senders="+15551234567",
    )
    gateway = IMessageGateway()
    gateway._enabled = False

    assert runner._runtime_ready(settings, gateway) is False


def test_runtime_not_ready_without_database(tmp_path):
    runner = _load_runner()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(tmp_path / "missing.db"),
        imessage_allowed_senders="+15551234567",
    )
    gateway = IMessageGateway()
    gateway._enabled = True

    assert runner._runtime_ready(settings, gateway) is False


def test_runtime_not_ready_without_allowlist(tmp_path):
    runner = _load_runner()
    database = tmp_path / "chat.db"
    database.touch()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(database),
        imessage_allowed_senders="",
    )
    gateway = IMessageGateway()
    gateway._enabled = True

    assert runner._runtime_ready(settings, gateway) is False


def test_runtime_ready_with_enabled_gateway_database_and_allowlist(tmp_path):
    runner = _load_runner()
    database = tmp_path / "chat.db"
    database.touch()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(database),
        imessage_allowed_senders="+15551234567",
    )
    gateway = IMessageGateway()
    gateway._enabled = True

    assert runner._runtime_ready(settings, gateway) is True


def test_handle_message_sends_gateway_reply():
    import asyncio

    runner = _load_runner()
    gateway = _FakeGateway(IMessageReply(chat_id=4, text="reply"))
    transport = _FakeTransport()
    settings = IMessageSettings(_env_file=None)
    message = _message()

    asyncio.run(runner._handle_message(gateway, transport, settings, message))

    assert gateway.messages == [message]
    assert transport.replies == [IMessageReply(chat_id=4, text="reply")]


def test_handle_message_skips_when_gateway_returns_none():
    import asyncio

    runner = _load_runner()
    gateway = _FakeGateway(None)
    transport = _FakeTransport()
    settings = IMessageSettings(_env_file=None)

    asyncio.run(runner._handle_message(gateway, transport, settings, _message()))

    assert transport.replies == []


def test_handle_message_sends_provisional_reply_when_director_is_slow():
    import asyncio

    runner = _load_runner()
    final = IMessageReply(chat_id=4, text="final")
    provisional = IMessageReply(chat_id=4, text="Working on it...")
    gateway = _FakeGateway(final, provisional_reply=provisional, delay_seconds=0.02)
    transport = _FakeTransport()
    settings = IMessageSettings(
        _env_file=None,
        imessage_provisional_reply_delay_seconds=0.001,
    )

    asyncio.run(runner._handle_message(gateway, transport, settings, _message()))

    assert transport.replies == [provisional, final]


def test_handle_message_skips_provisional_reply_when_director_is_fast():
    import asyncio

    runner = _load_runner()
    final = IMessageReply(chat_id=4, text="final")
    provisional = IMessageReply(chat_id=4, text="Working on it...")
    gateway = _FakeGateway(final, provisional_reply=provisional)
    transport = _FakeTransport()
    settings = IMessageSettings(
        _env_file=None,
        imessage_provisional_reply_delay_seconds=1,
    )

    asyncio.run(runner._handle_message(gateway, transport, settings, _message()))

    assert transport.replies == [final]


def test_seed_seen_messages_reads_recent_message_ids(tmp_path):
    import asyncio

    runner = _load_runner()
    transport = _FakeTransport(recent_messages=[_message(message_id="msg-001")])
    seen_store = runner.SeenMessageStore(tmp_path / "seen.json", limit=100)

    asyncio.run(runner._seed_seen_messages(transport, seen_store))

    assert seen_store.message_ids == {"msg-001"}


def test_seen_message_store_round_trips_and_prunes(tmp_path):
    runner = _load_runner()
    state_path = tmp_path / "state" / "imessage-seen.json"
    seen_store = runner.SeenMessageStore(state_path, limit=2)

    seen_store.add("msg-001")
    seen_store.add("msg-002")
    seen_store.add("msg-003")

    reloaded = runner.SeenMessageStore(state_path, limit=2)
    reloaded.load()

    assert reloaded.message_ids == {"msg-002", "msg-003"}


def test_poll_recent_messages_skips_seeded_messages(tmp_path):
    import asyncio

    runner = _load_runner()
    shutdown_event = asyncio.Event()
    gateway = _FakeGateway(None)
    old_message = _message(message_id="msg-old")
    new_message = _message(message_id="msg-new")
    transport = _FakeTransport(
        recent_messages=[old_message, new_message],
        on_recent_messages=shutdown_event.set,
    )
    settings = IMessageSettings(
        _env_file=None,
        imessage_poll_interval_seconds=60,
    )
    seen_store = runner.SeenMessageStore(tmp_path / "seen.json", limit=100)
    seen_store.add("msg-old", persist=False)

    asyncio.run(
        runner._poll_recent_messages(
            shutdown_event,
            gateway,
            transport,
            settings,
            seen_store,
        )
    )

    assert gateway.messages == [new_message]
    assert seen_store.message_ids == {"msg-old", "msg-new"}


def test_database_message_text_falls_back_to_attributed_body() -> None:
    attributed_body = (
        b"streamtyped\x00NSMutableAttributedString\x00NSObject\x00"
        b"Freyja, create family dinner Friday at 6 PM.\x00"
        b"NSKeyedArchiver\x00__kIMMessagePartAttributeName"
    )

    assert _database_message_text("", attributed_body) == "Freyja, create family dinner Friday at 6 PM."


def test_run_watch_loop_keeps_process_alive_when_watch_fails(tmp_path):
    import asyncio

    runner = _load_runner()
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    gateway = _FakeGateway(None)
    transport = _FakeTransport(watch_error=runner.IMessageTransportError("boom"))
    seen_store = runner.SeenMessageStore(tmp_path / "seen.json", limit=100)

    asyncio.run(
        runner._run_watch_loop(
            shutdown_event,
            gateway,
            transport,
            IMessageSettings(_env_file=None),
            seen_store,
        )
    )

    assert gateway.messages == []


class _FakeGateway:
    def __init__(self, reply, *, provisional_reply=None, delay_seconds=0):
        self.reply = reply
        self.provisional_reply = provisional_reply
        self.delay_seconds = delay_seconds
        self.messages = []

    def provisional_reply_for(self, message):
        return self.provisional_reply

    async def handle(self, message):
        import asyncio

        self.messages.append(message)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return self.reply


class _FakeTransport:
    def __init__(
        self,
        recent_messages=None,
        on_recent_messages=None,
        watch_error=None,
    ):
        self.replies = []
        self._recent_messages = list(recent_messages or [])
        self._on_recent_messages = on_recent_messages
        self._watch_error = watch_error

    async def send(self, reply):
        self.replies.append(reply)

    async def recent_messages(self):
        if self._on_recent_messages is not None:
            self._on_recent_messages()
        return self._recent_messages

    async def watch(self):
        if self._watch_error is not None:
            raise self._watch_error
        if False:
            yield None


def _message(message_id: str = "msg-001") -> IMessage:
    return IMessage(
        sender="+15551234567",
        text="hello",
        message_id=message_id,
        chat_id=4,
        chat_identifier="+15551234567",
        timestamp="2026-07-30T04:09:38.511Z",
    )
