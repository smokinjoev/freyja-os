from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "config" / "open-webui-home-agents.yaml"
CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "operations" / "cloyd-runtime-contract.md"


def test_open_webui_home_agents_are_secret_free_and_complete() -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert payload["secrets_included"] is False
    assert set(payload["model_profiles"]) == {"fast_chat", "strong_reasoning", "vision_documents", "coding"}
    agents = {agent["id"]: agent for agent in payload["agents"]}
    assert set(agents) == {"freyja", "cloyd", "smith", "benedict", "agent-44", "jenna"}
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


def test_agent_smith_is_pure_coding_agent() -> None:
    agents = {
        agent["id"]: agent
        for agent in yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["agents"]
    }

    smith = agents["smith"]
    assert smith["display_name"] == "Agent Smith"
    assert smith["purpose"] == "Joe's pure coding runtime wrapper."
    assert smith["model_profile"] == "coding"
    assert "pure coding runtime wrapper" in smith["system_prompt"]
    assert "opencode.status" in smith["system_prompt"]
    assert "opencode.shell" in smith["system_prompt"]
    assert set(smith["tools"]["coding"]) == {
        "opencode.start",
        "opencode.send",
        "opencode.shell",
        "opencode.stop",
    }
    assert smith["tools"]["confirm"] == []
    assert {
        "calendar.create",
        "reminders.create",
        "messaging.send",
        "home.device_action",
        "cloud_fallback",
    }.issubset(set(smith["tools"]["deny"]))


def test_cloyd_delegates_coding_to_agent_smith() -> None:
    agents = {
        agent["id"]: agent
        for agent in yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["agents"]
    }

    cloyd = agents["cloyd"]
    assert cloyd["model_profile"] == "strong_reasoning"
    assert "planning brain" in cloyd["system_prompt"]
    assert "free-running Iris Qwen Code/OpenCode session" in cloyd["system_prompt"]
    assert "send Qwen Code a precise task prompt" in cloyd["system_prompt"]
    assert "family webpage" in cloyd["system_prompt"]
    assert "cloyd-dashboard-web" in cloyd["system_prompt"]
    assert "/home/joe/cloyd-services/dashboard" in cloyd["system_prompt"]
    assert "Prefer `opencode.send`" in cloyd["system_prompt"]
    assert "`opencode.shell` only for small diagnostic checks" in cloyd["system_prompt"]
    assert "docs/operations/cloyd-runtime-contract.md" in cloyd["system_prompt"]
    assert "may outlive the browser connection" in cloyd["system_prompt"]
    assert "resume by checking `opencode.status`" in cloyd["system_prompt"]
    assert "show the diff" in cloyd["system_prompt"]
    assert "verify the served page" in cloyd["system_prompt"]
    assert "Never report success from an edit command alone" in cloyd["system_prompt"]
    assert "opencode.status" in cloyd["tools"]["allow"]
    assert set(cloyd["tools"]["coding"]) == {
        "opencode.start",
        "opencode.send",
        "opencode.shell",
        "opencode.stop",
    }
    assert {
        "children.admin",
        "cloud_fallback",
        "unrestricted_shell",
    }.issubset(set(cloyd["tools"]["deny"]))


def test_cloyd_runtime_contract_is_compact_and_actionable() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert len(text) < 2500
    assert "Cloyd is Joe's technical brain" in text
    assert "free-running" in text
    assert "qwen3:30b-a3b" in text
    assert "qwen3-coder-next:q4_K_M" in text
    assert "http://100.115.228.56:4097" in text
    assert "cloyd-dashboard-web" in text
    assert "/home/joe/cloyd-services/dashboard/index.html" in text
    assert "Do not use sub-agent or handoff-chat loops" in text
    assert "Every Qwen Code prompt must include a hard action budget" in text
    assert "Default budget for read-only checks: at most 3 runtime actions" in text
    assert "detached supervision" in text
    assert "not done yet" in text
    assert "browser, iPad, or OpenWebUI stream disconnects" in text
    assert "If output repeats the same conclusion twice" in text
    assert "A command finishing is not by itself completion" in text
