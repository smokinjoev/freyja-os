from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FREYJA5_COMPOSE = REPO_ROOT / "deploy" / "compose" / "freyja5" / "compose.yaml"
FREYJA5_ENV_EXAMPLE = REPO_ROOT / "deploy" / "compose" / "freyja5" / ".env.example"


def _load_freyja5_compose() -> dict:
    return yaml.safe_load(FREYJA5_COMPOSE.read_text(encoding="utf-8"))


def test_freyja5_compose_runs_side_by_side_gateway() -> None:
    compose = _load_freyja5_compose()
    service = compose["services"]["gateway"]

    assert compose["name"] == "freyja5"
    assert service["command"] == ["uvicorn", "freyja.main:app", "--host", "0.0.0.0", "--port", "8500"]
    assert service["ports"] == ["${FREYJA5_BIND_IP:-0.0.0.0}:${FREYJA5_HOST_PORT:-8500}:8500"]
    assert "../../../data:/app/data" in service["volumes"]
    assert service["read_only"] is True
    assert "no-new-privileges:true" in service["security_opt"]


def test_freyja5_compose_keeps_live_inference_and_cloud_explicit() -> None:
    environment = _load_freyja5_compose()["services"]["gateway"]["environment"]

    assert environment["FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED"] == "${FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED:-false}"
    assert environment["NEXUS_BASE_URL"] == "${NEXUS_BASE_URL:-}"
    assert environment["NEXUS_API_KEY"] == "${NEXUS_API_KEY:-}"
    assert environment["CLOUD_ENABLED"] == "${CLOUD_ENABLED:-false}"
    assert environment["FREYJA3_CANONICAL_ENABLED"] == "${FREYJA3_CANONICAL_ENABLED:-true}"
    assert environment["FREYJA3_INFERENCE_ENABLED"] == "${FREYJA3_INFERENCE_ENABLED:-false}"


def test_freyja5_env_example_contains_no_committed_secret() -> None:
    content = FREYJA5_ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "FREYJA_CONNECTOR_TOKEN=\n" in content
    assert "NEXUS_API_KEY=\n" in content
    assert "OPENROUTER_API_KEY=\n" in content
    assert "FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED=false" in content
