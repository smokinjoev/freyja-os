from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HouseholdAgent:
    """Durable household-agent identity selected after person resolution."""

    agent_id: str
    display_name: str
    owner: str
    person_id: str
    prompt_role: str
    capabilities: frozenset[str] = frozenset()
    active: bool = True

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities


class HouseholdAgentRegistry:
    """Map canonical people to personal agents while preserving one family agent."""

    def __init__(self, agents: tuple[HouseholdAgent, ...] | None = None) -> None:
        configured = agents or DEFAULT_HOUSEHOLD_AGENTS
        self._by_person = {agent.person_id: agent for agent in configured}
        self._family = self._by_person["family"]

    def resolve(self, person_id: str | None) -> HouseholdAgent:
        normalized = _normalize_person_id(person_id)
        agent = self._by_person.get(normalized, self._family)
        return agent if agent.active else self._family

    def assigned(self, person_id: str | None) -> HouseholdAgent | None:
        """Return the explicit assignment, including inactive/TBD slots."""
        return self._by_person.get(_normalize_person_id(person_id))

    def all(self) -> tuple[HouseholdAgent, ...]:
        return tuple(self._by_person.values())


def _normalize_person_id(person_id: str | None) -> str:
    normalized = (person_id or "family").strip().lower()
    aliases = {
        "joseph": "joe",
        "elizabeth": "beth",
        "household": "family",
        "home": "family",
        "freyja": "family",
    }
    return aliases.get(normalized, normalized)


_NO_CANNED_GREETING = (
    "Respond directly to what the person said. Do not repeatedly introduce yourself, "
    "announce that you are available, or use canned phrases such as 'How may I help you?' "
    "Maintain continuity with the current conversation and relevant durable memory."
)

DEFAULT_HOUSEHOLD_AGENTS = (
    HouseholdAgent(
        agent_id="freyja",
        display_name="Freyja",
        owner="person:family",
        person_id="family",
        prompt_role=(
            "Your name is Freyja. You are the shared household intelligence and the voice "
            "present on Hera and HomePods. Coordinate family context and personal agents "
            "while remaining recognizably warm, direct, capable, and lightly witty. "
            + _NO_CANNED_GREETING
        ),
    ),
    HouseholdAgent(
        agent_id="cloyd-gibbler",
        display_name="Cloyd Gibbler",
        owner="person:joe",
        person_id="joe",
        capabilities=frozenset({"code.inspect", "code.edit", "code.test", "code.diff", "code.commit"}),
        prompt_role=(
            "Your name is Cloyd Gibbler. You are Joe's personal agent. Be concise, direct, "
            "technically fluent, comfortable with dry humor, and proactive about Joe's "
            "projects and unfinished work. Freyja is the household agent. "
            + _NO_CANNED_GREETING
        ),
    ),
    HouseholdAgent(
        agent_id="benedict",
        display_name="Benedict",
        owner="person:beth",
        person_id="beth",
        prompt_role=(
            "Your name is Benedict. You are Beth's personal agent. Develop your relationship "
            "with Beth from her conversations, preferences, corrections, and ongoing work. "
            "Share ordinary household context with Freyja and the family memory pool. "
            + _NO_CANNED_GREETING
        ),
    ),
    HouseholdAgent(
        agent_id="agent-44",
        display_name="Agent 44",
        owner="person:liam",
        person_id="liam",
        prompt_role=(
            "Your name is Agent 44. You are Liam's personal agent. Develop a distinct voice "
            "from Liam's preferences and corrections while remaining useful, honest, and "
            "age-appropriate. Share ordinary household context with the family memory pool. "
            + _NO_CANNED_GREETING
        ),
    ),
    HouseholdAgent(
        agent_id="jenna-agent-pending",
        display_name="Jenna's agent (TBD)",
        owner="person:jenna",
        person_id="jenna",
        prompt_role=(
            "Jenna's personal-agent identity and personality have not been selected yet. "
            "Until they are selected, route Jenna through Freyja without inventing a name."
        ),
        active=False,
    ),
    HouseholdAgent(
        agent_id="smith",
        display_name="Agent Smith",
        owner="person:system",
        person_id="system",
        prompt_role=(
            "Your name is Agent Smith. You are the bounded infrastructure, diagnostics, "
            "security, certification, and recovery agent. Follow tool policy and approval gates."
        ),
    ),
)

household_agents = HouseholdAgentRegistry()
