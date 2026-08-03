from __future__ import annotations

import pytest

from freyja.identity import Alias, IdentityService, Person, Relationship
from freyja.tools.identity import register_identity_tools, set_identity_service
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def identity_service() -> None:
    service = IdentityService(
        people=[
            Person(person_id="joe", display_name="Joe", aliases=(Alias("Dad"),)),
            Person(person_id="beth", display_name="Beth"),
        ],
        relationships=[Relationship("joe", "spouse", "beth")],
    )
    set_identity_service(service)
    yield
    set_identity_service(None)


@pytest.mark.asyncio
async def test_identity_resolution_tool_returns_person_without_identifiers() -> None:
    registry = ToolRegistry(audit_enabled=False)
    register_identity_tools(registry)

    result = await registry.execute(ToolExecutionRequest(tool_name="identity_resolution", arguments={"identifier": "Dad"}))

    assert result.success is True
    assert result.output["resolved"] is True
    assert result.output["person"]["person_id"] == "joe"
    assert "identities" not in result.output["person"]


@pytest.mark.asyncio
async def test_identity_relationships_tool_returns_related_people() -> None:
    registry = ToolRegistry(audit_enabled=False)
    register_identity_tools(registry)

    result = await registry.execute(
        ToolExecutionRequest(tool_name="identity_relationships", arguments={"person": "Joe", "relationship": "spouse"})
    )

    assert result.success is True
    assert result.output["relationships"][0]["person_id"] == "beth"
