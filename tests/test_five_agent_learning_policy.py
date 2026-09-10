from __future__ import annotations

import yaml

from freyja.agents.household import DEFAULT_HOUSEHOLD_AGENTS


PERSONAL_AGENT_IDS = {"freyja", "cloyd-gibbler", "benedict", "agent-47", "jennacide"}


def test_household_agents_require_scoped_learning_continuity() -> None:
    agents = {agent.agent_id: agent for agent in DEFAULT_HOUSEHOLD_AGENTS}

    for agent_id in PERSONAL_AGENT_IDS:
        prompt = agents[agent_id].prompt_role.lower()
        assert "learn" in prompt
        assert "permitted memory scope" in prompt
        assert "stateless neutral assistant" in prompt
        assert "do not invent" in prompt


def test_open_webui_home_agents_require_learning_continuity() -> None:
    data = yaml.safe_load(open("config/open-webui-home-agents.yaml", encoding="utf-8"))
    agents = {agent["id"]: agent for agent in data["agents"]}

    for agent_id in {"freyja", "cloyd", "benedict", "agent-44", "jenna"}:
        prompt = agents[agent_id]["system_prompt"].lower()
        assert "learn" in prompt
        assert "preferences" in prompt
        assert "corrections" in prompt
        assert "stateless neutral assistant" in prompt or "continuity naturally" in prompt
