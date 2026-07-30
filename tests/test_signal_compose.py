from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNAL_COMPOSE = REPO_ROOT / "deploy" / "compose" / "signal" / "compose.yaml"


def _load_signal_compose() -> dict:
    with SIGNAL_COMPOSE.open() as handle:
        return yaml.safe_load(handle)


def test_signal_api_has_private_connector_network_and_egress() -> None:
    compose = _load_signal_compose()
    signal_api = compose["services"]["signal-api"]

    assert signal_api["networks"] == ["signal-private", "atlas-egress"]
    assert "ports" not in signal_api
    assert signal_api["expose"] == ["8080"]
    assert compose["networks"]["signal-private"]["internal"] is True


def test_signal_connector_uses_private_api_and_director_egress() -> None:
    compose = _load_signal_compose()
    connector = compose["services"]["signal-connector"]

    assert connector["networks"] == ["signal-private", "atlas-egress"]
    assert connector["environment"]["SIGNAL_REST_API_URL"] == "http://signal-api:8080"
