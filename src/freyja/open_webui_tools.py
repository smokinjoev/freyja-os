from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


REPO_ROOT = Path(os.environ.get("REPOSITORY_ROOT") or Path(__file__).resolve().parents[2])
RESOURCE_MANIFEST = REPO_ROOT / "config" / "open-webui-home-resources.yaml"
AGENT_MANIFEST = REPO_ROOT / "config" / "open-webui-home-agents.yaml"


class ToolOperation(BaseModel):
    operation: str
    resource_id: str
    boundary: str
    allowed_agents: list[str]
    confirmation_required: bool = False
    children_allowed: bool = False
    destructive_default: str = "deny"


class ToolCatalogResponse(BaseModel):
    operations: list[ToolOperation]
    secrets_included: bool = False
    private_content_included: bool = False


class ToolInvocationRequest(BaseModel):
    operation: str
    agent_id: str
    actor: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
    request_id: str | None = None


class ToolInvocationResponse(BaseModel):
    ok: bool
    status: str
    operation: str
    agent_id: str
    request_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class OperationPolicy:
    operation: str
    resource_id: str
    boundary: str
    allowed_agents: frozenset[str]
    confirmation_required: bool
    children_allowed: bool
    destructive_default: str


def _load_manifest(path: Path = RESOURCE_MANIFEST) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("secrets_included") is not False:
        raise ValueError("Open WebUI tool manifest must be explicit and secret-free")
    return data


def load_agent_tool_policies(path: Path = AGENT_MANIFEST) -> dict[str, dict[str, set[str]]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("secrets_included") is not False:
        raise ValueError("Open WebUI agent manifest must be explicit and secret-free")
    policies: dict[str, dict[str, set[str]]] = {}
    for agent in data.get("agents") or []:
        tools = agent.get("tools") or {}
        policies[agent["id"]] = {
            "allow": set(tools.get("allow") or []),
            "confirm": set(tools.get("confirm") or []),
            "deny": set(tools.get("deny") or []),
        }
    return policies


def load_operation_policies(path: Path = RESOURCE_MANIFEST) -> dict[str, OperationPolicy]:
    manifest = _load_manifest(path)
    policies: dict[str, OperationPolicy] = {}
    for resource in manifest.get("resources", {}).get("tools", []):
        children = set(resource.get("children_allowed_operations") or [])
        confirmations = set(resource.get("confirmation_required") or [])
        for operation in resource.get("operations") or []:
            policies[operation] = OperationPolicy(
                operation=operation,
                resource_id=resource["id"],
                boundary=resource["boundary"],
                allowed_agents=frozenset(resource.get("allowed_agents") or []),
                confirmation_required=operation in confirmations,
                children_allowed=operation in children,
                destructive_default=resource.get("destructive_default", "deny"),
            )
    return policies


def _policy_to_model(policy: OperationPolicy) -> ToolOperation:
    return ToolOperation(
        operation=policy.operation,
        resource_id=policy.resource_id,
        boundary=policy.boundary,
        allowed_agents=sorted(policy.allowed_agents),
        confirmation_required=policy.confirmation_required,
        children_allowed=policy.children_allowed,
        destructive_default=policy.destructive_default,
    )


def _redacted_argument_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "keys": sorted(arguments),
        "size_bytes": len(json.dumps(arguments, sort_keys=True, default=str).encode("utf-8")),
    }


def authorize_tool_invocation(
    request: ToolInvocationRequest,
    policies: dict[str, OperationPolicy] | None = None,
    agent_policies: dict[str, dict[str, set[str]]] | None = None,
) -> OperationPolicy:
    policies = policies or load_operation_policies()
    agent_policies = agent_policies or load_agent_tool_policies()
    policy = policies.get(request.operation)
    if policy is None:
        raise HTTPException(status_code=404, detail="Unknown Open WebUI tool operation.")
    if request.agent_id not in policy.allowed_agents:
        raise HTTPException(status_code=403, detail="Agent is not permitted to use this tool operation.")
    agent_policy = agent_policies.get(request.agent_id)
    if agent_policy is None:
        raise HTTPException(status_code=403, detail="Unknown agent.")
    if request.operation in agent_policy["deny"]:
        raise HTTPException(status_code=403, detail="Agent policy denies this tool operation.")
    if request.operation not in agent_policy["allow"] and request.operation not in agent_policy["confirm"]:
        raise HTTPException(status_code=403, detail="Agent policy does not grant this tool operation.")
    if request.agent_id in {"agent-44", "jenna"} and not policy.children_allowed:
        raise HTTPException(status_code=403, detail="Child agents are not permitted to use this tool operation.")
    if (policy.confirmation_required or request.operation in agent_policy["confirm"]) and not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required before invoking this operation.")
    if policy.destructive_default != "deny":
        raise HTTPException(status_code=500, detail="Tool policy is not fail-closed.")
    return policy


def invoke_policy_stub(policy: OperationPolicy, request: ToolInvocationRequest) -> ToolInvocationResponse:
    status = "authorized"
    result: dict[str, Any] = {
        "boundary": policy.boundary,
        "resource_id": policy.resource_id,
        "execution": "not_configured",
    }
    read_only_status = {
        "search",
        "recent-events",
        "calendar.read",
        "reminders.read",
        "home.status",
        "weather.read",
        "files.household.read",
        "files.beth.read",
        "infrastructure.health",
        "pdf.analyze",
        "image.analyze",
    }
    if policy.operation in read_only_status:
        status = "stubbed"
    return ToolInvocationResponse(
        ok=True,
        status=status,
        operation=policy.operation,
        agent_id=request.agent_id,
        request_id=request.request_id,
        result=result,
        audit={
            "timestamp_unix": int(time.time()),
            "actor": request.actor,
            "argument_summary": _redacted_argument_summary(request.arguments),
            "private_content_included": False,
            "secrets_included": False,
        },
    )


open_webui_tools_router = APIRouter(prefix="/open-webui-tools", tags=["open-webui-tools"])


@open_webui_tools_router.get("", response_model=ToolCatalogResponse)
async def open_webui_tool_catalog() -> ToolCatalogResponse:
    return ToolCatalogResponse(operations=[_policy_to_model(policy) for policy in load_operation_policies().values()])


@open_webui_tools_router.post("/invoke", response_model=ToolInvocationResponse)
async def invoke_open_webui_tool(body: ToolInvocationRequest, _: Request) -> ToolInvocationResponse:
    policy = authorize_tool_invocation(body)
    return invoke_policy_stub(policy, body)
