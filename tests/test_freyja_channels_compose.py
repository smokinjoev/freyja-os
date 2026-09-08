from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "deploy" / "compose" / "freyja-channels" / "compose.yaml"
ENV_EXAMPLE = REPO_ROOT / "deploy" / "compose" / "freyja-channels" / ".env.example"
README = REPO_ROOT / "deploy" / "compose" / "freyja-channels" / "README.md"
DOCKERFILE = REPO_ROOT / "deploy" / "docker" / "freyja-channels.Dockerfile"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_freyja_channels_compose_uses_profiles_and_no_published_ports() -> None:
    compose = _compose()
    services = compose["services"]

    assert set(services) == {"telegram-pilot", "telegram-dry-run", "signal-pilot", "signal-dry-run"}
    assert services["telegram-pilot"]["profiles"] == ["telegram"]
    assert services["signal-pilot"]["profiles"] == ["signal"]
    assert services["telegram-dry-run"]["profiles"] == ["operator"]
    assert services["signal-dry-run"]["profiles"] == ["operator"]
    assert all("ports" not in service for service in services.values())
    assert all(service["user"] == "${FREYJA_CHANNELS_UID:-1000}:${FREYJA_CHANNELS_GID:-1000}" for service in services.values())
    assert "signal-private" not in services["telegram-pilot"]["networks"]
    assert "signal-private" in services["signal-pilot"]["networks"]
    assert _compose()["networks"]["signal-private"] == {
        "external": True,
        "name": "${SIGNAL_PRIVATE_NETWORK:-freyja-signal-atlas_signal-private}",
    }
    assert compose["secrets"]["open_webui_api_key"]["file"] == "${OPEN_WEBUI_API_KEY_HOST_FILE:-/home/joe/.freyja/open-webui-api-key}"


def test_freyja_channels_compose_defaults_to_key_file_and_deny_all_allowlists() -> None:
    values = _env_values()

    assert values["OPEN_WEBUI_API_KEY"] == ""
    assert values["OPEN_WEBUI_API_KEY_FILE"] == "/run/secrets/open_webui_api_key"
    assert values["FREYJA_CHANNELS_UID"] == "1000"
    assert values["FREYJA_CHANNELS_GID"] == "1000"
    assert values["FREYJA_CHANNEL_STATE_DIR"] == "../../../data/freyja-channels"
    assert values["TELEGRAM_ENABLED"] == "false"
    assert values["TELEGRAM_ALLOWED_USER_IDS"] == ""
    assert values["TELEGRAM_IDENTITY_MAP"] == ""
    assert values["TELEGRAM_BOT_PROFILES"] == "FREYJA_JOE,CLOYD_JOE,BENEDICT_BETH,AGENT44_LIAM,JENNA"
    assert values["TELEGRAM_FREYJA_JOE_AGENT"] == "freyja"
    assert values["TELEGRAM_CLOYD_JOE_AGENT"] == "cloyd"
    assert values["TELEGRAM_BENEDICT_BETH_AGENT"] == "benedict"
    assert values["TELEGRAM_AGENT44_LIAM_AGENT"] == "agent-44"
    assert values["TELEGRAM_JENNA_AGENT"] == "jenna"
    assert values["TELEGRAM_MAX_ATTACHMENT_BYTES"] == "8388608"
    assert values["SIGNAL_ENABLED"] == "false"
    assert values["SIGNAL_PRIVATE_NETWORK"] == "freyja-signal-atlas_signal-private"
    assert values["SIGNAL_ALLOWED_SENDERS"] == ""
    assert values["SIGNAL_IDENTITY_MAP"] == ""

    compose = _compose()
    telegram_env = compose["services"]["telegram-pilot"]["environment"]
    signal_env = compose["services"]["signal-pilot"]["environment"]
    assert telegram_env["OPEN_WEBUI_API_KEY_FILE"] == "${OPEN_WEBUI_API_KEY_FILE:-/run/secrets/open_webui_api_key}"
    assert signal_env["OPEN_WEBUI_API_KEY_FILE"] == "${OPEN_WEBUI_API_KEY_FILE:-/run/secrets/open_webui_api_key}"
    assert telegram_env["TELEGRAM_ALLOWED_USER_IDS"] == "${TELEGRAM_ALLOWED_USER_IDS:-}"
    assert telegram_env["TELEGRAM_CLOYD_JOE_BOT_TOKEN"] == "${TELEGRAM_CLOYD_JOE_BOT_TOKEN:-}"
    assert telegram_env["TELEGRAM_CLOYD_JOE_AGENT"] == "${TELEGRAM_CLOYD_JOE_AGENT:-cloyd}"
    assert telegram_env["TELEGRAM_MAX_ATTACHMENT_BYTES"] == "${TELEGRAM_MAX_ATTACHMENT_BYTES:-8388608}"
    assert signal_env["SIGNAL_ALLOWED_SENDERS"] == "${SIGNAL_ALLOWED_SENDERS:-}"
    assert compose["services"]["telegram-pilot"]["volumes"] == ["${FREYJA_CHANNEL_STATE_DIR:-../../../data/freyja-channels}:/state"]


def test_freyja_channels_compose_runs_channel_scripts_directly() -> None:
    compose = _compose()

    assert "scripts/run-freyja-channels-telegram-pilot.py" in compose["services"]["telegram-pilot"]["command"]
    assert "--dry-run" in compose["services"]["telegram-dry-run"]["command"]
    assert "/state/telegram-dry-run.json" in compose["services"]["telegram-dry-run"]["command"]
    assert "scripts/run-freyja-channels-signal-pilot.py" in compose["services"]["signal-pilot"]["command"]
    assert "--dry-run" in compose["services"]["signal-dry-run"]["command"]
    assert "/state/signal-dry-run.json" in compose["services"]["signal-dry-run"]["command"]
    assert "COPY scripts/run-freyja-channels-telegram-pilot.py" in DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY scripts/run-freyja-channels-signal-pilot.py" in DOCKERFILE.read_text(encoding="utf-8")


def test_freyja_channels_readme_documents_secret_free_operator_flow() -> None:
    text = README.read_text(encoding="utf-8")

    assert "deterministic Open WebUI messaging gateway" in text
    assert "does not route models" in text
    assert "independent agent intelligence" in text
    assert "OPEN_WEBUI_API_KEY_HOST_FILE=/home/joe/.freyja/open-webui-api-key" in text
    assert "An empty allowlist is deny-all" in text
    assert "--profile operator run --rm telegram-dry-run" in text
    assert "--profile telegram up -d --build telegram-pilot" in text
    assert "--profile signal up -d --build signal-pilot" in text
    assert "WhatsApp stays disabled" in text
    assert "TELEGRAM_CLOYD_JOE_BOT_TOKEN" in text
    assert "Each profile uses its own bot token and offset file" in text
