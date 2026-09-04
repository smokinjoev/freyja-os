from __future__ import annotations

import pytest

from freyja.channels import ChannelMessage, ChannelPolicyError, FreyjaChannels, MemoryChannelStore, RateLimitExceeded


class FakeOpenWebUIClient:
    def __init__(self) -> None:
        self.calls = []

    def send(self, *, agent, thread_key, message, attachments):
        self.calls.append({"agent": agent, "thread_key": thread_key, "message": message, "attachments": attachments})
        return f"response from {agent}"


def _service(**kwargs) -> FreyjaChannels:
    allowlists = {
        "telegram": {"1001"},
        "signal": {"+15550001002"},
        "whatsapp": {"wa-1"},
    }
    identities = {
        "telegram": {"1001": "joe"},
        "signal": {"+15550001002": "beth"},
        "whatsapp": {"wa-1": "joe"},
    }
    return FreyjaChannels(allowlists=allowlists, identity_maps=identities, **kwargs)


def test_telegram_joe_routes_to_default_freyja_without_raw_sender_in_thread() -> None:
    store = MemoryChannelStore()
    route = _service(store=store).route(ChannelMessage(channel="telegram", sender="1001", text="status", chat_id="chat-1001"))

    assert route.identity == "joe"
    assert route.agent == "freyja"
    assert route.thread_key.startswith("telegram:freyja:")
    assert "1001" not in route.thread_key
    assert store.events[0]["message_body_logged"] is False
    assert store.events[0]["raw_sender_logged"] is False


def test_signal_beth_can_route_to_benedict() -> None:
    route = _service().route(ChannelMessage(channel="signal", sender="+15550001002", text="review this", requested_agent="benedict"))

    assert route.identity == "beth"
    assert route.agent == "benedict"
    assert route.thread_key.startswith("signal-conv:")
    assert "+1555" not in route.thread_key


def test_empty_allowlist_denies_all() -> None:
    svc = FreyjaChannels(allowlists={"telegram": set()}, identity_maps={"telegram": {"1001": "joe"}})

    with pytest.raises(ChannelPolicyError, match="allowlist is empty"):
        svc.route(ChannelMessage(channel="telegram", sender="1001", text="hello"))


def test_unmapped_sender_is_denied() -> None:
    svc = FreyjaChannels(allowlists={"telegram": {"1001"}}, identity_maps={"telegram": {}})

    with pytest.raises(ChannelPolicyError, match="identity is not mapped"):
        svc.route(ChannelMessage(channel="telegram", sender="1001", text="hello"))


def test_identity_cannot_request_unpermitted_agent() -> None:
    with pytest.raises(ChannelPolicyError, match="not permitted"):
        _service().route(ChannelMessage(channel="signal", sender="+15550001002", text="code", requested_agent="cloyd"))


def test_whatsapp_is_documented_but_disabled() -> None:
    with pytest.raises(ChannelPolicyError, match="disabled"):
        _service().route(ChannelMessage(channel="whatsapp", sender="wa-1", text="hello"))


def test_rate_limit_is_per_sender() -> None:
    now = iter([1.0, 2.0, 3.0])
    svc = FreyjaChannels(
        allowlists={"telegram": {"1001"}},
        identity_maps={"telegram": {"1001": "joe"}},
        now=lambda: next(now),
    )
    svc.policy["channels"]["telegram"]["rate_limit"]["per_sender_per_minute"] = 2
    svc.route(ChannelMessage(channel="telegram", sender="1001", text="one"))
    svc.route(ChannelMessage(channel="telegram", sender="1001", text="two"))

    with pytest.raises(RateLimitExceeded):
        svc.route(ChannelMessage(channel="telegram", sender="1001", text="three"))


def test_handle_forwards_only_to_open_webui_client() -> None:
    client = FakeOpenWebUIClient()
    response = _service(client=client).handle(ChannelMessage(channel="telegram", sender="1001", text="hello", attachments=({"kind": "image"},)))

    assert response == "response from freyja"
    assert client.calls == [
        {
            "agent": "freyja",
            "thread_key": client.calls[0]["thread_key"],
            "message": "hello",
            "attachments": ({"kind": "image"},),
        }
    ]
