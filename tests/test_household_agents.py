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


def test_jenna_has_active_personal_agent() -> None:
    agent = household_agents.assigned("jenna")

    assert agent is not None
    assert agent.active is True
    assert agent.display_name == "Jenna"
    assert household_agents.resolve("jenna").agent_id == "jenna"


def test_family_agents_have_local_presets_and_no_cloud_routes() -> None:
    expected_presets = {
        "family": "@preset/freyja-fast-local",
        "joe": "@preset/freyja-coder",
        "beth": "@preset/freyja-private-local",
        "liam": "@preset/freyja-private-local",
        "jenna": "@preset/freyja-private-local",
    }

    for person_id, preset in expected_presets.items():
        agent = household_agents.resolve(person_id)
        assert agent.default_model_preset == preset
        assert agent.cloud_routes_allowed is False
        assert agent.memory_scope in {"family", f"person:{person_id}"}


def test_family_agents_do_not_receive_legal_enclave_scope() -> None:
    for person_id in ("family", "joe", "beth", "liam", "jenna"):
        agent = household_agents.resolve(person_id)
        assert "legal_research" not in agent.capabilities
        assert agent.memory_scope != "enclave:paralegal"


def test_unknown_people_fail_to_household_freyja() -> None:
    assert household_agents.resolve("guest").agent_id == "freyja"


def test_conversational_agents_reject_canned_reset_greetings() -> None:
    for person_id in ("family", "joe", "beth", "liam", "jenna"):
        prompt = household_agents.resolve(person_id).prompt_role
        assert "How may I help you?" in prompt
        assert "Maintain continuity" in prompt
