from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


SENSITIVE_ARGUMENT_NAMES = {"api_key", "authorization", "bearer", "password", "secret", "token"}


@dataclass
class ToolCallEvidence:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    success: bool | None = None
    error: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": dict(self.arguments),
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class CertificationContext:
    request_id: str | None = None
    interface: str | None = None
    principal: dict[str, Any] | None = None
    person: dict[str, str] | None = None
    provider_selected: str | None = None
    model_selected: str | None = None
    routing_decision: str | None = None
    routing_reason: str | None = None
    fallback_events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallEvidence] = field(default_factory=list)
    capability_authorizations: list[dict[str, Any]] = field(default_factory=list)
    memory_lookups: list[dict[str, Any]] = field(default_factory=list)
    connector_operations: list[dict[str, Any]] = field(default_factory=list)
    vision_executions: list[dict[str, Any]] = field(default_factory=list)
    timing: dict[str, float] = field(default_factory=dict)
    token_counts: dict[str, int] = field(default_factory=dict)
    cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "interface": self.interface,
            "principal": dict(self.principal) if self.principal else None,
            "person": dict(self.person) if self.person else None,
            "provider_selected": self.provider_selected,
            "model_selected": self.model_selected,
            "routing_decision": self.routing_decision,
            "routing_reason": self.routing_reason,
            "fallback_events": list(self.fallback_events),
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "capability_authorizations": list(self.capability_authorizations),
            "memory_lookups": list(self.memory_lookups),
            "connector_operations": list(self.connector_operations),
            "vision_executions": list(self.vision_executions),
            "timing": dict(self.timing),
            "token_counts": dict(self.token_counts),
            "cost": self.cost,
        }


@dataclass(frozen=True)
class CertificationExecution:
    response: str
    error: str | None = None
    context: CertificationContext = field(default_factory=CertificationContext)


def sanitize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in arguments.items():
        lowered = key.lower()
        if any(term in lowered for term in SENSITIVE_ARGUMENT_NAMES):
            sanitized[key] = "[redacted]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_arguments(value)
        elif isinstance(value, list):
            sanitized[key] = ["[redacted]" if isinstance(item, str) and _looks_secret(item) else item for item in value]
        elif isinstance(value, str) and _looks_secret(value):
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = value
    return sanitized


def elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000


def _looks_secret(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ("bearer ", "sk-", "token=", "api_key="))
