from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HOMEBRIDGE_COMPOSE = REPO_ROOT / "deploy" / "compose" / "homebridge" / "compose.yaml"


def _load_homebridge_compose() -> dict:
    with HOMEBRIDGE_COMPOSE.open() as handle:
        return yaml.safe_load(handle)


def test_homebridge_uses_host_network_for_homekit_discovery() -> None:
    compose = _load_homebridge_compose()
    service = compose["services"]["homebridge"]

    assert service["network_mode"] == "host"
    assert service["build"]["dockerfile"] == "deploy/docker/homebridge.Dockerfile"
    assert "ports" not in service


def test_homebridge_persists_config_and_ui_port() -> None:
    compose = _load_homebridge_compose()
    service = compose["services"]["homebridge"]

    assert "homebridge-data:/homebridge" in service["volumes"]
    assert service["environment"]["HOMEBRIDGE_CONFIG_UI_PORT"] == "${HOMEBRIDGE_CONFIG_UI_PORT:-8581}"
