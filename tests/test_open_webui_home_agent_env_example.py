from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _env_lines() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_env_example_contains_open_webui_home_agent_activation_placeholders() -> None:
    values = _env_lines()

    assert values["OPEN_WEBUI_URL"] == "http://127.0.0.1:3001"
    assert values["OPEN_WEBUI_API_KEY"] == ""
    assert values["OPEN_WEBUI_CHAT_SMOKE_TIMEOUT"] == "120"
    assert values["FREYJA_CHANNEL_OPEN_WEBUI_TIMEOUT"] == "120"


def test_env_example_contains_channel_pilot_identity_placeholders() -> None:
    values = _env_lines()

    assert values["TELEGRAM_ALLOWED_USER_IDS"] == ""
    assert values["TELEGRAM_IDENTITY_MAP"] == ""
    assert values["FREYJA_CHANNEL_TELEGRAM_POLL_INTERVAL"] == "2"
    assert values["SIGNAL_ALLOWED_SENDERS"] == ""
    assert values["SIGNAL_IDENTITY_MAP"] == ""
    assert values["FREYJA_CHANNEL_SIGNAL_POLL_INTERVAL"] == "5"
