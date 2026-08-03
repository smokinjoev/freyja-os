from __future__ import annotations

from typing import Any

from freyja.identity import IdentityService, default_identity_service
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


_service: IdentityService | None = None


def get_identity_service() -> IdentityService:
    global _service
    if _service is None:
        _service = default_identity_service()
    return _service


def set_identity_service(service: IdentityService | None) -> None:
    global _service
    _service = service


async def _resolve_identity(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments
    identifier = str(args.get("identifier") or "")
    kind = args.get("kind")
    person = get_identity_service().resolve(identifier, kind=str(kind)) if kind else get_identity_service().resolve(identifier)
    return {
        "resolved": person is not None,
        "person": person.to_dict() if person else None,
    }


async def _relationships(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments
    identifier = str(args.get("person") or "")
    service = get_identity_service()
    person = service.resolve(identifier)
    relationship = args.get("relationship")
    related = service.related_people(person.person_id, str(relationship) if relationship else None) if person else ()
    return {
        "resolved": person is not None,
        "person": person.to_dict() if person else None,
        "relationships": [target.to_dict() for target in related],
    }


def register_identity_tools(registry: ToolRegistry) -> None:
    for definition, implementation in _tool_specs():
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)


def _tool_specs() -> list[tuple[ToolDefinition, Any]]:
    return [
        (
            ToolDefinition(
                name="identity_resolution",
                description="Resolve an alias, phone, email, messaging sender, or calendar owner to a Freyja Person.",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "required": ["identifier"],
                    "properties": {
                        "identifier": {"type": "string"},
                        "kind": {"type": "string"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.READ_ONLY,
                enabled=True,
                timeout_seconds=10,
                tags=["identity", "personal-intelligence"],
            ),
            _resolve_identity,
        ),
        (
            ToolDefinition(
                name="identity_relationships",
                description="Return people related to a known Freyja Person, optionally filtered by relationship type.",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "required": ["person"],
                    "properties": {
                        "person": {"type": "string"},
                        "relationship": {"type": "string"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.READ_ONLY,
                enabled=True,
                timeout_seconds=10,
                tags=["identity", "personal-intelligence"],
            ),
            _relationships,
        ),
    ]
