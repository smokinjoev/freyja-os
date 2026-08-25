from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CanonicalAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    media_type: str | None = None
    filename: str | None = None
    size: int | None = Field(default=None, ge=0)
    source: str | None = None
    reference: str | None = None
    data_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalSender(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: str
    display_name: str | None = None
    address: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: str
    conversation_id: str
    sender: CanonicalSender
    resolved_user_id: str | None = None
    resolved_agent_id: str | None = None
    text: str = ""
    attachments: list[CanonicalAttachment] = Field(default_factory=list)
    reply_context: dict[str, Any] = Field(default_factory=dict)
    channel_metadata: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)


class CanonicalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    request_message_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: str
    conversation_id: str
    resolved_user_id: str | None = None
    resolved_agent_id: str | None = None
    text: str = ""
    attachments: list[CanonicalAttachment] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    channel_metadata: dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False
    status: str = "ok"
