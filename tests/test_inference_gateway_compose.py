from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_COMPOSE = REPO_ROOT / "deploy" / "compose" / "inference-gateway" / "compose.yaml"


def _load_gateway_compose() -> dict:
    with GATEWAY_COMPOSE.open() as handle:
        return yaml.safe_load(handle)


def test_inference_gateway_compose_uses_standalone_app() -> None:
    compose = _load_gateway_compose()
    service = compose["services"]["inference-gateway"]

    assert service["command"] == [
        "uvicorn",
        "freyja.inference_gateway_app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8010",
    ]
    assert "${FREYJA_INFERENCE_GATEWAY_BIND_IP:-127.0.0.1}:8010:8010" in service["ports"]


def test_inference_gateway_compose_passes_tier_and_budget_settings() -> None:
    compose = _load_gateway_compose()
    environment = compose["services"]["inference-gateway"]["environment"]

    assert environment["INFERENCE_GATEWAY_MONTHLY_HARD_LIMIT"] == "${INFERENCE_GATEWAY_MONTHLY_HARD_LIMIT:-20.0}"
    assert environment["INFERENCE_GATEWAY_FAST_MODEL"] == "${INFERENCE_GATEWAY_FAST_MODEL:-qwen/qwen3.5-flash-02-23}"
    assert environment["INFERENCE_GATEWAY_REASONING_MODEL"] == "${INFERENCE_GATEWAY_REASONING_MODEL:-moonshotai/kimi-k2.5}"
    assert environment["INFERENCE_GATEWAY_DEEP_MODEL"] == "${INFERENCE_GATEWAY_DEEP_MODEL:-z-ai/glm-5}"
    assert environment["INFERENCE_GATEWAY_FREE_MODEL"] == "${INFERENCE_GATEWAY_FREE_MODEL:-}"
    assert environment["INFERENCE_GATEWAY_OLLAMA_CLOUD_MODEL"] == "${INFERENCE_GATEWAY_OLLAMA_CLOUD_MODEL:-}"
