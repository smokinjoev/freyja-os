from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from freyja.config import settings

MacAgentCapability = Literal[
    "apple.messages.read",
    "apple.messages.send",
    "apple.calendar.read",
    "apple.calendar.write",
    "apple.contacts.read",
    "apple.shortcuts.run",
]


class MacAgentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reachable: bool = False
    authenticated: bool = False
    host: str = "iris"
    capabilities: list[MacAgentCapability] = Field(default_factory=list)
    error: str | None = None


class MacAgentOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: MacAgentCapability
    operation: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    director_authorized: bool
    required_permission: str | None = None
    approval_granted: bool = False
    principal: dict[str, Any] | None = None
    person: dict[str, Any] | None = None


class MacAgentOperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    capability: MacAgentCapability
    operation: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class MacAgentClient:
    """Authenticated client for Iris Apple-native capability health.

    This client only observes MacAgent availability and capability inventory.
    Atlas Director remains responsible for principal identity, authorization,
    approval policy, memory policy, and final tool dispatch.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.base_url = (base_url or settings.macagent_base_url).rstrip("/")
        self.token = settings.macagent_token if token is None else token
        self.timeout_seconds = timeout_seconds or settings.macagent_timeout_seconds
        self.enabled = settings.macagent_enabled if enabled is None else enabled

    async def health(self) -> MacAgentHealth:
        if not self.enabled:
            return MacAgentHealth(enabled=False, error="macagent disabled")
        if not self.token.strip():
            return MacAgentHealth(enabled=True, error="macagent token not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return MacAgentHealth(enabled=True, error=f"{type(exc).__name__}: {exc}")

        try:
            remote = MacAgentHealth.model_validate(payload)
        except ValidationError as exc:
            return MacAgentHealth(enabled=True, error=f"invalid macagent health payload: {exc}")
        return remote.model_copy(update={"enabled": True, "authenticated": True})

    async def invoke(self, request: MacAgentOperationRequest) -> MacAgentOperationResult:
        if not self.enabled:
            return MacAgentOperationResult(
                ok=False,
                capability=request.capability,
                operation=request.operation,
                error="macagent disabled",
            )
        if not self.token.strip():
            return MacAgentOperationResult(
                ok=False,
                capability=request.capability,
                operation=request.operation,
                error="macagent token not configured",
            )
        if request.director_authorized is not True:
            return MacAgentOperationResult(
                ok=False,
                capability=request.capability,
                operation=request.operation,
                error="director authorization required",
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/capabilities/{request.capability}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=request.model_dump(mode="json"),
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return MacAgentOperationResult(
                ok=False,
                capability=request.capability,
                operation=request.operation,
                error=f"{type(exc).__name__}: {exc}",
            )

        try:
            return MacAgentOperationResult.model_validate(payload)
        except ValidationError as exc:
            return MacAgentOperationResult(
                ok=False,
                capability=request.capability,
                operation=request.operation,
                error=f"invalid macagent operation payload: {exc}",
            )
