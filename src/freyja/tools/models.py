import time
import uuid
from enum import StrEnum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class ToolRiskLevel(StrEnum):
    READ_ONLY = "read_only"
    CONTROLLED_WRITE = "controlled_write"
    PRIVILEGED = "privileged"


class ToolDefinition(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY
    enabled: bool = True
    timeout_seconds: int = 30
    tags: list[str] = Field(default_factory=list)


class ToolExecutionRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    actor: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    success: bool
    tool_name: str
    output: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    public_error_message: str | None = None
    duration_ms: int = 0
    request_id: str


ToolImplementation = Callable[[ToolExecutionRequest], Awaitable[dict[str, Any]]]
