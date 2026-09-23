from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from connectors.discord.config import DiscordSettings, parse_user_agent_bindings
from connectors.discord.gateway import DiscordGateway, DiscordInboundMessage

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
