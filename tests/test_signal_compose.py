from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNAL_COMPOSE = REPO_ROOT / "deploy" / "compose" / "signal" / "compose.yaml"
SIGNAL_DOCKERFILE = REPO_ROOT / "deploy" / "docker" / "signal-connector.Dockerfile"


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


def test_signal_operator_is_private_one_shot_profile() -> None:
    compose = _load_signal_compose()
    operator = compose["services"]["signal-operator"]

    assert operator["profiles"] == ["operator"]
    assert operator["depends_on"]["signal-api"]["condition"] == "service_healthy"
    assert operator["environment"]["SIGNAL_REST_API_URL"] == "http://signal-api:8080"
    assert operator["networks"] == ["signal-private", "atlas-egress"]
    assert operator["read_only"] is True
    assert operator["command"] == [
        "python",
        "scripts/signal-operator.py",
        "readiness",
        "--check-registered",
    ]


def test_signal_image_packages_operator_cli() -> None:
    dockerfile = SIGNAL_DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY scripts/run-signal-connector.py ./scripts/run-signal-connector.py" in dockerfile
    assert "COPY scripts/signal-operator.py ./scripts/signal-operator.py" in dockerfile
