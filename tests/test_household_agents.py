from freyja.agents.household import household_agents


def test_household_agent_assignments() -> None:
    assert household_agents.resolve("joe").agent_id == "cloyd-gibbler"
    assert household_agents.resolve("beth").agent_id == "benedict"
    assert household_agents.resolve("liam").agent_id == "agent-44"
    assert household_agents.resolve("family").agent_id == "freyja"
    assert household_agents.resolve("system").agent_id == "smith"


def test_legacy_person_aliases_resolve_to_personal_agents() -> None:
    assert household_agents.resolve("Joseph").agent_id == "cloyd-gibbler"
    assert household_agents.resolve("Elizabeth").agent_id == "benedict"
    assert household_agents.resolve("home").agent_id == "freyja"


def test_jenna_routes_to_freyja_until_agent_is_named() -> None:
    pending = household_agents.assigned("jenna")

    assert pending is not None
    assert pending.active is False
    assert pending.display_name == "Jenna's agent (TBD)"
    assert household_agents.resolve("jenna").agent_id == "freyja"


def test_unknown_people_fail_to_household_freyja() -> None:
    assert household_agents.resolve("guest").agent_id == "freyja"


def test_conversational_agents_reject_canned_reset_greetings() -> None:
    for person_id in ("family", "joe", "beth", "liam"):
        prompt = household_agents.resolve(person_id).prompt_role
        assert "How may I help you?" in prompt
        assert "Maintain continuity" in prompt
