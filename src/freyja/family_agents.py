from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from freyja.foundation_models import SecurityDomainId


class FamilyRouteConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    member: str = Field(min_length=1)
    actor_principal: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    default_agent: str = Field(min_length=1)
    security_domain_id: SecurityDomainId
    document_scope: str = Field(min_length=1)
    tool_policy: str = Field(min_length=1)
    privacy_policy: str = Field(min_length=1)
    parent_visibility: str = Field(min_length=1)


CHILD_HOMEWORK_POLICY_MODES = frozenset({"hint_first", "check_work", "quiz"})


FAMILY_ROUTE_REGISTRY: dict[str, FamilyRouteConfig] = {
    "joe": FamilyRouteConfig(
        member="joe",
        actor_principal="person:joe",
        display_name="Joe",
        default_agent="cloyd-gibbler",
        security_domain_id=SecurityDomainId.PERSON_JOE,
        document_scope="person:joe/documents",
        tool_policy="adult_personal",
        privacy_policy="person-private",
        parent_visibility="none",
    ),
    "beth": FamilyRouteConfig(
        member="beth",
        actor_principal="person:beth",
        display_name="Beth",
        default_agent="benedict",
        security_domain_id=SecurityDomainId.PERSON_BETH,
        document_scope="person:beth/documents",
        tool_policy="adult_personal",
        privacy_policy="person-private",
        parent_visibility="none",
    ),
    "liam": FamilyRouteConfig(
        member="liam",
        actor_principal="person:liam",
        display_name="Liam",
        default_agent="agent-47",
        security_domain_id=SecurityDomainId.PERSON_LIAM,
        document_scope="person:liam/school",
        tool_policy="child_homework:hint_first",
        privacy_policy="child-private",
        parent_visibility="summary",
    ),
    "jenna": FamilyRouteConfig(
        member="jenna",
        actor_principal="person:jenna",
        display_name="JennaCide",
        default_agent="jennacide",
        security_domain_id=SecurityDomainId.PERSON_JENNA,
        document_scope="person:jenna/school",
        tool_policy="child_homework:hint_first",
        privacy_policy="child-private",
        parent_visibility="summary",
    ),
}


def family_route_config(member: str) -> FamilyRouteConfig | None:
    return FAMILY_ROUTE_REGISTRY.get(member.strip().lower())


def family_tool_policy(config: FamilyRouteConfig, requested_mode: str | None) -> str:
    if not requested_mode:
        return config.tool_policy
    mode = requested_mode.strip().lower()
    if config.tool_policy.startswith("child_homework:"):
        if mode not in CHILD_HOMEWORK_POLICY_MODES:
            raise ValueError("Unsupported child homework policy mode.")
        return f"child_homework:{mode}"
    return config.tool_policy


def resolve_family_agent_alias(config: FamilyRouteConfig, requested_agent: str | None) -> str:
    if not requested_agent:
        return config.default_agent
    agent = requested_agent.strip()
    if not agent.startswith("@"):
        return agent
    prefix, _, alias = agent[1:].partition("/")
    if prefix.strip().lower() != config.member or not alias.strip():
        raise ValueError("Family agent alias does not match this route.")
    return alias.strip()
