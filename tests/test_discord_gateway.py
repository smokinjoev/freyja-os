from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from io import BytesIO

import httpx
import pytest
from PIL import Image

from connectors.discord.config import DiscordSettings, parse_seen_reactions, parse_user_agent_bindings
from connectors.discord.gateway import DiscordGateway, DiscordInboundMessage, DiscordOutboundReply

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-freyja-6.2-messaging.py"
ENV_VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate-discord-private-env.py"
DM_RUNNER_SCRIPT = REPO_ROOT / "scripts" / "run-discord-dm-connector.py"


def _settings() -> DiscordSettings:
    return DiscordSettings(
        enabled=True,
        bot_token="not-a-real-token",
        director_url="http://director.test",
        connector_token="connector-token",
        user_agent_bindings=parse_user_agent_bindings("100=cloyd-gibbler,200=agent-47,300=smith"),
    )


def test_discord_user_agent_bindings_reject_duplicate_user() -> None:
    with pytest.raises(ValueError, match="exactly once"):
        parse_user_agent_bindings("100=freyja,100=smith")


def test_discord_user_agent_bindings_allow_shared_default_agent() -> None:
    bindings = parse_user_agent_bindings("100=freyja,101=freyja")

    assert [binding.agent_id for binding in bindings] == ["freyja", "freyja"]


def test_discord_user_agent_bindings_reject_unknown_agent() -> None:
    with pytest.raises(ValueError, match="unapproved"):
        parse_user_agent_bindings("100=jennacide")


def test_discord_seen_reactions_default_to_eyes() -> None:
    assert parse_seen_reactions("") == ("👀", "👀")
    assert parse_seen_reactions("👀,✅") == ("👀", "✅")


@pytest.mark.asyncio
async def test_discord_gateway_ignores_non_dm_and_non_text_messages() -> None:
    gateway = DiscordGateway(_settings())

    assert await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m1",
            author_id="100",
            channel_id="c1",
            channel_type="guild_text",
            content="hello",
        )
    ) is None
    assert gateway.would_route(
        DiscordInboundMessage(
            message_id="m3",
            author_id="100",
            channel_id="c1",
            channel_type="dm",
            content="hello",
        )
    ) is True
    assert await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m2",
            author_id="100",
            channel_id="c1",
            channel_type="dm",
            content="hello",
            attachments=({"filename": "photo.png"},),
        )
    ) is None
    unsupported = gateway.unsupported_message_reply(
        DiscordInboundMessage(
            message_id="m2",
            author_id="100",
            channel_id="c1",
            channel_type="dm",
            content="please read this",
            attachments=({"filename": "archive.zip", "content_type": "application/zip", "url": "https://cdn.test/archive.zip"},),
        )
    )
    assert unsupported is not None
    assert "PDFs and common image files" in unsupported.text


@pytest.mark.asyncio
async def test_discord_gateway_routes_approved_dm_to_bound_agent() -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"text": "final answer"}

    class FakeClient:
        async def post(self, url, *, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m3",
            author_id="200",
            channel_id="dm-channel",
            channel_type="dm",
            content="hello",
        )
    )

    assert reply is not None
    assert reply.text == "final answer"
    assert reply.agent_id == "agent-47"
    assert captured["url"] == "http://director.test/canonical/route"
    assert captured["headers"]["X-Freyja-Agent-Id"] == "agent-47"
    assert captured["headers"]["X-Freyja-Agent-Display-Name"] == "Agent 44"
    assert captured["headers"]["X-Freyja-Client-Type"] == "discord"
    assert captured["json"]["resolved_agent_id"] == "agent-47"
    assert captured["json"]["channel_metadata"]["discord_channel_type"] == "dm"
    assert captured["json"]["channel_metadata"]["discord_text_only"] is True
    assert captured["json"]["channel_metadata"]["discord_final_only"] is True


@pytest.mark.asyncio
async def test_discord_gateway_downloads_pdf_attachment_for_director() -> None:
    captured = {}

    class FakeResponse:
        def __init__(self, *, payload=None, content=b"") -> None:
            self._payload = payload or {}
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        async def get(self, url, **kwargs):
            captured["download_url"] = url
            return FakeResponse(content=b"%PDF-1.4 fake")

        async def post(self, url, *, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse(payload={"text": "I read the PDF."})

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m4",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="what is this?",
            attachments=(
                {
                    "filename": "plan.pdf",
                    "content_type": "application/pdf",
                    "size": 13,
                    "url": "https://cdn.discordapp.test/plan.pdf",
                },
            ),
        )
    )

    assert reply is not None
    assert captured["download_url"] == "https://cdn.discordapp.test/plan.pdf"
    assert captured["json"]["channel_metadata"]["discord_text_only"] is False
    assert captured["json"]["channel_metadata"]["discord_media_intake"] is True
    assert captured["json"]["attachments"][0]["filename"] == "plan.pdf"
    assert captured["json"]["attachments"][0]["data_base64"] == "JVBERi0xLjQgZmFrZQ=="
    assert "documents.process" in captured["json"]["permissions"]
    assert "vision.inspect" in captured["json"]["permissions"]
    assert "Trusted Discord metadata" in captured["json"]["text"]


@pytest.mark.asyncio
async def test_discord_gateway_retries_transient_attachment_download_timeout() -> None:
    captured = {"download_attempts": 0}

    class FakeResponse:
        def __init__(self, *, payload=None, content=b"") -> None:
            self._payload = payload or {}
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        async def get(self, url, **kwargs):
            captured["download_attempts"] += 1
            if captured["download_attempts"] == 1:
                raise httpx.ReadTimeout("slow Discord CDN")
            return FakeResponse(content=b"%PDF-1.4 fake")

        async def post(self, url, *, json, headers):
            captured["json"] = json
            return FakeResponse(payload={"text": "I read it."})

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m4b",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="what is this?",
            attachments=(
                {
                    "filename": "plan.pdf",
                    "content_type": "application/pdf",
                    "size": 13,
                    "url": "https://cdn.discordapp.test/plan.pdf",
                },
            ),
        )
    )

    assert reply is not None
    assert reply.text == "I read it."
    assert captured["download_attempts"] == 2
    assert captured["json"]["attachments"][0]["filename"] == "plan.pdf"


@pytest.mark.asyncio
async def test_discord_gateway_normalizes_large_image_attachment() -> None:
    captured = {}
    image_buffer = BytesIO()
    Image.frombytes("RGB", (1800, 1500), os.urandom(1800 * 1500 * 3)).save(image_buffer, format="JPEG", quality=96)
    image_bytes = image_buffer.getvalue()

    class FakeResponse:
        def __init__(self, *, payload=None, content=b"") -> None:
            self._payload = payload or {}
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        async def get(self, url, **kwargs):
            return FakeResponse(content=image_bytes)

        async def post(self, url, *, json, headers):
            captured["json"] = json
            return FakeResponse(payload={"text": "I can see it."})

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m4d",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="",
            attachments=(
                {
                    "filename": "large.jpeg",
                    "content_type": "image/jpeg",
                    "size": len(image_bytes),
                    "url": "https://cdn.discordapp.test/large.png",
                },
            ),
        )
    )

    assert reply is not None
    attachment = captured["json"]["attachments"][0]
    assert attachment["filename"] == "large.jpg"
    assert attachment["media_type"] == "image/jpeg"
    assert attachment["size"] < len(image_bytes)


@pytest.mark.asyncio
async def test_discord_gateway_returns_director_timeout_reply() -> None:
    class FakeClient:
        async def post(self, url, *, json, headers):
            raise httpx.ReadTimeout("slow director")

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m4e",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="hello",
        )
    )

    assert reply is not None
    assert "timed out" in reply.text
    assert reply.agent_id == "cloyd-gibbler"


@pytest.mark.asyncio
async def test_discord_gateway_returns_download_failure_without_routing() -> None:
    captured = {"post_called": False}

    class FakeClient:
        async def get(self, url, **kwargs):
            raise httpx.ReadTimeout("slow Discord CDN")

        async def post(self, url, *, json, headers):
            captured["post_called"] = True
            raise AssertionError("Director should not be called when attachment download fails.")

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m4c",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="what is this?",
            attachments=(
                {
                    "filename": "plan.pdf",
                    "content_type": "application/pdf",
                    "size": 13,
                    "url": "https://cdn.discordapp.test/plan.pdf",
                },
            ),
        )
    )

    assert reply is not None
    assert "timed out" in reply.text
    assert captured["post_called"] is False


@pytest.mark.asyncio
async def test_discord_gateway_suppresses_internal_attachment_status_reply() -> None:
    class FakeResponse:
        def __init__(self, *, payload=None, content=b"") -> None:
            self._payload = payload or {}
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        async def get(self, url, **kwargs):
            return FakeResponse(content=b"%PDF-1.4 fake")

        async def post(self, url, *, json, headers):
            return FakeResponse(
                payload={
                    "text": (
                        "Cloyd Gibbler received the objective and selected vision.inspect "
                        "with 8 recalled memory record(s) using vulcan-nexus-vision-docs."
                    )
                }
            )

    gateway = DiscordGateway(_settings(), client=FakeClient())

    reply = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m5",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="what is this?",
            attachments=(
                {
                    "filename": "plan.pdf",
                    "content_type": "application/pdf",
                    "size": 13,
                    "url": "https://cdn.discordapp.test/plan.pdf",
                },
            ),
        )
    )

    assert reply is not None
    assert "attachment" in reply.text
    assert "received the objective" not in reply.text
    assert "vision.inspect" not in reply.text
    assert "vulcan" not in reply.text.lower()


@pytest.mark.asyncio
async def test_discord_gateway_reuses_recent_attachment_for_followup_reference() -> None:
    captured_posts: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, *, payload=None, content=b"") -> None:
            self._payload = payload or {}
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        async def get(self, url, **kwargs):
            return FakeResponse(content=b"fake image bytes")

        async def post(self, url, *, json, headers):
            captured_posts.append(json)
            return FakeResponse(payload={"text": "handled"})

    gateway = DiscordGateway(_settings(), client=FakeClient())

    first = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m6",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="",
            attachments=(
                {
                    "filename": "photo.png",
                    "content_type": "image/png",
                    "size": 16,
                    "url": "https://cdn.discordapp.test/photo.png",
                },
            ),
        )
    )
    followup = await gateway.handle_message(
        DiscordInboundMessage(
            message_id="m7",
            author_id="100",
            channel_id="dm-channel",
            channel_type="dm",
            content="what do you see?",
        )
    )

    assert first is not None
    assert followup is not None
    assert len(captured_posts) == 2
    assert captured_posts[1]["attachments"][0]["filename"] == "photo.png"
    assert captured_posts[1]["attachments"][0]["data_base64"] == "ZmFrZSBpbWFnZSBieXRlcw=="
    assert captured_posts[1]["channel_metadata"]["discord_media_intake"] is True


def test_discord_verifier_checks_connector_token_leaks(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location("verify_freyja_62_messaging", VERIFY_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._tracked_secret_failures({"FREYJA_CONNECTOR_TOKEN": "fake-connector-token-for-test"}) == []

    fake_root = tmp_path
    for relative in (
        "docs/discord/freyja-6.2-five-agent-runbook.md",
        "connectors/discord/config.py",
        "connectors/discord/gateway.py",
    ):
        path = fake_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("nothing secret here\n", encoding="utf-8")
    module.ROOT = fake_root
    (fake_root / "docs/discord/freyja-6.2-five-agent-runbook.md").write_text(
        "fake-connector-token-for-test\n",
        encoding="utf-8",
    )

    failures = module._tracked_secret_failures({"FREYJA_CONNECTOR_TOKEN": "fake-connector-token-for-test"})

    assert failures == ["A live FREYJA_CONNECTOR_TOKEN value appears in tracked Freyja 6.2 files."]


def test_discord_private_env_validator_reports_redacted_readiness() -> None:
    spec = importlib.util.spec_from_file_location("validate_discord_private_env", ENV_VALIDATE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.validate(
        {
            "DISCORD_ENABLED": "false",
            "DISCORD_BOT_TOKEN": "not-a-real-token",
            "FREYJA_CONNECTOR_TOKEN": "connector-token",
            "DISCORD_USER_AGENT_MAP": (
                "100=freyja,101=cloyd-gibbler,102=benedict,103=agent-47,104=smith"
            ),
        }
    )

    assert result["ok"] is True
    assert result["discord_enabled"] is False
    assert result["ready_for_live_transport"] is False
    assert result["binding_count"] == 5
    assert result["missing_agents"] == []
    assert result["failures"] == []


def test_discord_private_env_validator_allows_shared_freyja_default() -> None:
    spec = importlib.util.spec_from_file_location("validate_discord_private_env", ENV_VALIDATE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.validate(
        {
            "DISCORD_BOT_TOKEN": "not-a-real-token",
            "FREYJA_CONNECTOR_TOKEN": "connector-token",
            "DISCORD_USER_AGENT_MAP": "100=freyja",
        }
    )

    assert result["ok"] is True
    assert result["binding_count"] == 1
    assert result["missing_agents"] == ["agent-47", "benedict", "cloyd-gibbler", "smith"]
    assert result["failures"] == []


def test_discord_private_env_validator_can_require_all_agents() -> None:
    spec = importlib.util.spec_from_file_location("validate_discord_private_env", ENV_VALIDATE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.validate(
        {
            "DISCORD_BOT_TOKEN": "not-a-real-token",
            "FREYJA_CONNECTOR_TOKEN": "connector-token",
            "DISCORD_USER_AGENT_MAP": "100=freyja",
        },
        require_all_agents=True,
    )

    assert result["ok"] is False
    assert result["binding_count"] == 1
    assert result["missing_agents"] == ["agent-47", "benedict", "cloyd-gibbler", "smith"]
    assert "DISCORD_USER_AGENT_MAP is missing approved agents." in result["failures"]


def test_discord_dm_runner_translates_dm_payload_and_intents() -> None:
    spec = importlib.util.spec_from_file_location("run_discord_dm_connector", DM_RUNNER_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    message = module._message_from_gateway_payload(
        {
            "id": "m1",
            "channel_id": "dm1",
            "content": "hello",
            "author": {"id": "u1"},
            "attachments": [],
            "embeds": [],
        }
    )
    guild_message = module._message_from_gateway_payload(
        {
            "id": "m2",
            "guild_id": "g1",
            "channel_id": "c1",
            "content": "hello",
            "author": {"id": "u1"},
        }
    )
    identify = module._identify_payload("not-a-real-token")

    assert message.channel_type == "dm"
    assert message.author_id == "u1"
    assert guild_message.channel_type == "guild_text"
    assert identify["d"]["intents"] == module.INTENT_DIRECT_MESSAGES | module.INTENT_MESSAGE_CONTENT


@pytest.mark.asyncio
async def test_discord_dm_runner_sends_seen_reactions_before_reply() -> None:
    spec = importlib.util.spec_from_file_location("run_discord_dm_connector", DM_RUNNER_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events: list[tuple[str, str]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def put(self, url, *, headers, **kwargs):
            events.append(("put", url))
            return FakeResponse()

        async def get(self, url, **kwargs):
            events.append(("get", url))
            return FakeResponse()

        async def post(self, url, *, headers, json):
            events.append(("post", url))
            return FakeResponse()

    class FakeGateway:
        def would_route(self, message):
            return True

        def unsupported_message_reply(self, message):
            return None

        async def handle_message(self, message):
            events.append(("handle", message.message_id))
            return DiscordOutboundReply(
                text="final",
                message_reference_id=message.message_id,
                agent_id="freyja",
                trace_id="trace",
            )

    settings = DiscordSettings(
        enabled=True,
        bot_token="not-a-real-token",
        director_url="http://director.test",
        connector_token="connector-token",
        user_agent_bindings=parse_user_agent_bindings("100=freyja"),
        seen_reactions=("👀", "✅"),
    )
    runner = module.DiscordDmRunner(settings=settings, gateway=FakeGateway(), client=FakeClient())
    await runner._handle_gateway_event(
        {
            "op": 0,
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "m1",
                "channel_id": "dm1",
                "content": "hello",
                "author": {"id": "100"},
                "attachments": [],
                "embeds": [],
            },
        }
    )

    assert [event[0] for event in events] == ["put", "put", "handle", "post"]
    assert "%F0%9F%91%80" in events[0][1]
    assert "%E2%9C%85" in events[1][1]


@pytest.mark.asyncio
async def test_discord_dm_runner_sends_unsupported_attachment_notice_without_routing() -> None:
    spec = importlib.util.spec_from_file_location("run_discord_dm_connector", DM_RUNNER_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events: list[tuple[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def put(self, url, *, headers, **kwargs):
            events.append(("put", url))
            return FakeResponse()

        async def post(self, url, *, headers, json):
            events.append(("post", json))
            return FakeResponse()

    class FakeGateway:
        def would_route(self, message):
            return False

        def unsupported_message_reply(self, message):
            return DiscordGateway(_settings()).unsupported_message_reply(message)

        async def handle_message(self, message):
            events.append(("handle", message.message_id))
            return None

    runner = module.DiscordDmRunner(settings=_settings(), gateway=FakeGateway(), client=FakeClient())
    await runner._handle_gateway_event(
        {
            "op": 0,
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "m1",
                "channel_id": "dm1",
                "content": "please read this",
                "author": {"id": "100"},
                "attachments": [{"filename": "plan.pdf"}],
                "embeds": [],
            },
        }
    )

    assert [event[0] for event in events] == ["post"]
    assert "PDFs and common image files" in events[0][1]["content"]
