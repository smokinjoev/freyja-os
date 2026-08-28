from __future__ import annotations

from pathlib import Path
import yaml


def test_machine_heartbeat_user_units_are_reproducible() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/user/freyja3-machine-heartbeat.service").read_text()
    timer = (root / "deploy/systemd/user/freyja3-machine-heartbeat.timer").read_text()

    assert "EnvironmentFile=%h/.config/freyja/freyja3-machine-heartbeat.env" in service
    assert "ExecStart=%h/freyja-os-freyja3/.heartbeat-venv/bin/freyja3-machine-heartbeat" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "WantedBy=timers.target" in timer


def test_hera_semantic_publisher_user_units_are_reproducible() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/user/freyja3-hera-semantic-publisher.service").read_text()
    timer = (root / "deploy/systemd/user/freyja3-hera-semantic-publisher.timer").read_text()

    assert "EnvironmentFile=%h/.config/freyja/freyja3-hera-semantic-publisher.env" in service
    assert "ExecStart=%h/freyja-os-freyja3/.heartbeat-venv/bin/freyja-hera-semantic-publisher" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "WantedBy=timers.target" in timer


def test_freyja3_compose_includes_litellm_gateway() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((root / "deploy/compose/freyja3/compose.yaml").read_text())

    litellm = compose["services"]["litellm"]
    assert litellm["image"] == "ghcr.io/berriai/litellm:main-stable"
    assert litellm["command"] == ["--config", "/app/config.yaml", "--host", "0.0.0.0", "--port", "4000"]
    assert "./litellm.config.yaml:/app/config.yaml:ro" in litellm["volumes"]
    assert litellm["ports"] == ["${LITELLM_BIND_IP:-0.0.0.0}:${LITELLM_HOST_PORT:-4000}:4000"]
    assert litellm["environment"]["IRIS_OLLAMA_BASE_URL"] == "${IRIS_OLLAMA_BASE_URL:-http://100.115.228.56:11434}"
    assert litellm["environment"]["VULCAN_OLLAMA_BASE_URL"] == "${VULCAN_OLLAMA_BASE_URL:-http://100.94.80.21:11434}"
    assert litellm["environment"]["VULCAN_OPENAI_BASE_URL"] == "${VULCAN_OPENAI_BASE_URL:-http://100.94.80.21:1234/v1}"
    assert litellm["environment"]["OPENROUTER_API_KEY"] == "${OPENROUTER_API_KEY:-}"


def test_litellm_config_exposes_vulcan_model() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "deploy/compose/freyja3/litellm.config.yaml").read_text())

    assert [model["model_name"] for model in config["model_list"]] == [
        "iris-fast",
        "vulcan-general",
        "vulcan-coder",
        "vulcan-vision",
        "vulcan-embeddings",
        "vulcan",
        "vulcan-deep",
        "vulcan-lmstudio",
        "cloud-frontier",
    ]
    assert config["model_list"][0]["litellm_params"] == {
        "model": "ollama_chat/qwen2.5:7b",
        "api_base": "os.environ/IRIS_OLLAMA_BASE_URL",
    }
    assert config["model_list"][1]["litellm_params"] == {
        "model": "ollama_chat/qwen2.5:32b-instruct",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
    }
    assert config["model_list"][2]["litellm_params"] == {
        "model": "ollama_chat/qwen3-coder-next:q4_K_M",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
    }
    assert config["model_list"][3]["litellm_params"] == {
        "model": "ollama_chat/qwen2.5vl:72b",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
        "num_ctx": 65536,
    }
    assert config["model_list"][4]["litellm_params"] == {
        "model": "ollama/nomic-embed-text:latest",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
    }
    assert config["model_list"][5]["model_name"] == "vulcan"
    assert config["model_list"][5]["litellm_params"] == {
        "model": "ollama_chat/qwen2.5:32b-instruct",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
    }
    assert config["model_list"][6]["model_name"] == "vulcan-deep"
    assert config["model_list"][6]["litellm_params"] == {
        "model": "ollama_chat/qwen2.5vl:72b",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
        "num_ctx": 65536,
    }
    assert config["model_list"][7]["model_name"] == "vulcan-lmstudio"
    assert config["model_list"][7]["litellm_params"] == {
        "model": "openai/local-model",
        "api_base": "os.environ/VULCAN_OPENAI_BASE_URL",
        "api_key": "os.environ/VULCAN_OPENAI_API_KEY",
    }
    assert config["model_list"][8]["model_name"] == "cloud-frontier"
    assert config["model_list"][8]["litellm_params"] == {
        "model": "openrouter/openai/gpt-4o-mini",
        "api_key": "os.environ/OPENROUTER_API_KEY",
    }
    assert config["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"


def test_litellm_legacy_vulcan_alias_targets_general_model() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "deploy/compose/freyja3/litellm.config.yaml").read_text())
    legacy = next(model for model in config["model_list"] if model["model_name"] == "vulcan")

    assert legacy["litellm_params"] == {
        "model": "ollama_chat/qwen2.5:32b-instruct",
        "api_base": "os.environ/VULCAN_OLLAMA_BASE_URL",
    }
