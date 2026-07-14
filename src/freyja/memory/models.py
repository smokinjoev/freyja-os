from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class MemoryMessage(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    timestamp: datetime
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSummary(BaseModel):
    conversation_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class CreateConversationRequest(BaseModel):
    conversation_id: str | None = None


class CreateConversationResponse(BaseModel):
    conversation_id: str


class AppendMessageRequest(BaseModel):
    conversation_id: str
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] | None = None


class AppendMessageResponse(BaseModel):
    message_id: str


class ConversationMessagesResponse(BaseModel):
    conversation_id: str
    messages: list[MemoryMessage]


class ListConversationsResponse(BaseModel):
    conversations: list[ConversationSummary]


class PruneResponse(BaseModel):
    deleted_records: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
