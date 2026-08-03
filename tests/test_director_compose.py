from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DIRECTOR_COMPOSE = REPO_ROOT / "deploy" / "compose" / "director" / "compose.yaml"


def _load_director_compose() -> dict:
    with DIRECTOR_COMPOSE.open() as handle:
        return yaml.safe_load(handle)


def test_director_passes_local_reasoning_ollama_settings() -> None:
    compose = _load_director_compose()
    environment = compose["services"]["director"]["environment"]

    assert environment["OLLAMA_BASE_URL"] == "${OLLAMA_BASE_URL}"
    assert environment["OLLAMA_REASONING_MODEL"] == "${OLLAMA_REASONING_MODEL:-gpt-oss:20b}"
    assert environment["OLLAMA_DEFAULT_OUTPUT_TOKENS"] == "${OLLAMA_DEFAULT_OUTPUT_TOKENS:-512}"
    assert environment["OLLAMA_MIN_OUTPUT_TOKENS"] == "${OLLAMA_MIN_OUTPUT_TOKENS:-160}"
    assert environment["OLLAMA_RETRY_OUTPUT_TOKENS"] == "${OLLAMA_RETRY_OUTPUT_TOKENS:-1024}"


def test_director_uses_persistent_shared_memory_configuration() -> None:
    compose = _load_director_compose()
    service = compose["services"]["director"]
    environment = service["environment"]

    assert environment["MEMORY_DATABASE_PATH"] == "/app/data/freyja.db"
    assert "../../../data:/app/data" in service["volumes"]
    assert environment["MEMORY_SHARED_ENABLED"] == "${MEMORY_SHARED_ENABLED:-true}"
    assert environment["MEMORY_SHARED_MAX_ITEMS_PER_PRINCIPAL"] == "${MEMORY_SHARED_MAX_ITEMS_PER_PRINCIPAL:-200}"
    assert environment["MEMORY_SHARED_MAX_GLOBAL_ITEMS"] == "${MEMORY_SHARED_MAX_GLOBAL_ITEMS:-10000}"
    assert environment["MEMORY_RECALL_INCLUDE_IN_CLOUD"] == "${MEMORY_RECALL_INCLUDE_IN_CLOUD:-false}"
