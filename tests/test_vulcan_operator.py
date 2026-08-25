from __future__ import annotations

import importlib.util
from pathlib import Path

from freyja.config import Settings


REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_PATH = REPO_ROOT / "scripts" / "vulcan-operator.py"


def _load_operator():
    spec = importlib.util.spec_from_file_location("vulcan_operator", OPERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(**overrides):
    defaults = {
        "_env_file": None,
        "vulcan_base_url": "http://vulcan:11434",
        "model_fast": "qwen2.5:7b",
        "model_reason": "gpt-oss-freyja:20b-analysis-prefill",
        "model_code": "qwen2.5-coder:14b-q3",
        "model_vision": "moondream",
        "cloud_enabled": False,
        "iris_router_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_providers_by_profile_uses_logical_profiles() -> None:
    operator = _load_operator()

    providers = operator._providers_by_profile(_settings())

    assert set(providers) == {"fast", "reason", "code", "vision"}
    assert providers["fast"].model == "qwen2.5:7b"
    assert providers["reason"].model == "gpt-oss-freyja:20b-analysis-prefill"
    assert providers["code"].model == "qwen2.5-coder:14b-q3"
    assert providers["vision"].model == "moondream"


def test_readiness_reports_missing_model(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()

    async def fake_ollama_tags(provider):
        if provider.logical_profile == "vision":
            return {"qwen2.5:7b", "gpt-oss-freyja:20b-analysis-prefill", "qwen2.5-coder:14b-q3"}
        return {provider.model}

    monkeypatch.setattr(operator, "_ollama_tags", fake_ollama_tags)

    result = asyncio.run(operator._readiness(_settings()))

    assert result["report_type"] == "vulcan-readiness"
    assert result["status"] == "blocked"
    assert result["ready_for_certification"] is False
    assert result["checks"]["vision"]["model_available"] is False
    assert result["checks"]["reason"]["ready"] is True
    assert "Install model moondream for the vision profile." in result["missing"]


def test_readiness_passes_when_all_profile_models_are_available(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()

    async def fake_ollama_tags(provider):
        return {provider.model}

    monkeypatch.setattr(operator, "_ollama_tags", fake_ollama_tags)

    result = asyncio.run(operator._readiness(_settings()))

    assert result["status"] == "ready"
    assert result["ready_for_certification"] is True
    assert result["missing"] == []


def test_readiness_treats_untagged_model_as_latest_alias(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()

    async def fake_ollama_tags(provider):
        if provider.logical_profile == "vision":
            return {"moondream:latest"}
        return {provider.model}

    monkeypatch.setattr(operator, "_ollama_tags", fake_ollama_tags)

    result = asyncio.run(operator._readiness(_settings()))

    assert result["status"] == "ready"
    assert result["checks"]["vision"]["model"] == "moondream"
    assert result["checks"]["vision"]["model_available"] is True
    assert result["checks"]["vision"]["ready"] is True


def test_readiness_does_not_match_different_explicit_tag(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()

    async def fake_ollama_tags(provider):
        if provider.logical_profile == "vision":
            return {"moondream:latest"}
        return {provider.model}

    monkeypatch.setattr(operator, "_ollama_tags", fake_ollama_tags)

    result = asyncio.run(operator._readiness(_settings(model_vision="moondream:1b")))

    assert result["status"] == "blocked"
    assert result["checks"]["vision"]["model"] == "moondream:1b"
    assert result["checks"]["vision"]["model_available"] is False
    assert "Install model moondream:1b for the vision profile." in result["missing"]


def test_pull_profile_defaults_to_dry_run() -> None:
    import asyncio

    operator = _load_operator()

    result = asyncio.run(operator._pull_profile(_settings(), profile="vision", dry_run=True))

    assert result["report_type"] == "vulcan-pull-profile"
    assert result["status"] == "dry-run"
    assert result["dry_run"] is True
    assert result["plan"]["profile"] == "vision"
    assert result["plan"]["model"] == "moondream"


def test_pull_profile_requires_yes_before_network_call(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()
    calls = []

    async def fake_pull(provider):
        calls.append(provider.model)
        return 200

    monkeypatch.setattr(operator, "_pull_ollama_model", fake_pull)

    dry_run = asyncio.run(operator._pull_profile(_settings(), profile="vision", dry_run=True))
    pulled = asyncio.run(operator._pull_profile(_settings(), profile="vision", dry_run=False))

    assert dry_run["status"] == "dry-run"
    assert pulled["status"] == "pulled"
    assert pulled["http_status"] == 200
    assert calls == ["moondream"]


def test_readiness_command_writes_report_and_uses_exit_code(tmp_path, monkeypatch) -> None:
    operator = _load_operator()
    output = tmp_path / "vulcan-readiness.json"
    monkeypatch.setattr(operator, "_settings", lambda env_file: _settings())

    async def fake_ollama_tags(provider):
        return set()

    monkeypatch.setattr(operator, "_ollama_tags", fake_ollama_tags)

    result = operator.main(["readiness", "--output", str(output)])

    assert result == 1
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert '"report_type": "vulcan-readiness"' in text
    assert '"ready_for_certification": false' in text
