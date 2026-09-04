from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "config" / "open-webui-home-agents.yaml"


def test_open_webui_home_agents_are_secret_free_and_complete() -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert payload["secrets_included"] is False
    assert set(payload["model_profiles"]) == {"fast_chat", "strong_reasoning", "vision_documents", "coding"}
    agents = {agent["id"]: agent for agent in payload["agents"]}
    assert set(agents) == {"freyja", "cloyd", "benedict", "agent-44", "jenna"}
    assert "token" not in str(payload).lower()
    assert "api_key" not in str(payload).lower()


def test_benedict_and_child_agents_are_constrained() -> None:
    agents = {
        agent["id"]: agent
        for agent in yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["agents"]
    }

    benedict = agents["benedict"]
    assert benedict["memory_policy"]["cloud_fallback"] == "forbidden"
    assert "restricted:benedict" in benedict["permitted_knowledge"]
    assert "cloud_fallback" in benedict["tools"]["deny"]
    assert "personal:joe" in benedict["tools"]["deny"]

    for child_id in ("agent-44", "jenna"):
        child = agents[child_id]
        assert "messaging.send" in child["tools"]["deny"]
        assert "home.device_action" in child["tools"]["deny"]
        assert not child["tools"]["confirm"]
