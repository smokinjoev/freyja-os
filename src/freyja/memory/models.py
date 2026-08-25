from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MemoryKind = Literal["fact", "preference", "project_state", "summary"]
MemorySensitivity = Literal["routine", "private", "sensitive"]
MemoryTrustLevel = Literal[
    "trusted_internal",
    "trusted_connector",
    "user_confirmed",
    "untrusted_external_content",
    "inferred",
]
MemoryProvenanceKind = Literal["observation", "user_confirmed_fact", "trusted_system_fact", "derived_fact"]


class MemoryProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1, max_length=128)
    source_id: str | None = Field(default=None, max_length=160)
    source_type: str = Field(default="client", min_length=1, max_length=64)
    trust_level: MemoryTrustLevel = "trusted_connector"
    kind: MemoryProvenanceKind = "trusted_system_fact"
    authoritative: bool = True
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    observation_id: str | None = Field(default=None, max_length=160)
    worker_id: str | None = Field(default=None, max_length=128)
    derivation_links: list[str] = Field(default_factory=list, max_length=20)
    evidence: dict[str, Any] = Field(default_factory=dict)


class MemoryPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_type: str = Field(min_length=1, max_length=32)
    client_subject: str = Field(min_length=1, max_length=128)
    account_owner: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=160)

    @property
    def scope_key(self) -> str:
        owner = self.account_owner or ""
        if self.client_subject.startswith("family-member:"):
            return "\x1f".join(("person", self.client_subject, owner, ""))
        conversation = self.conversation_id or ""
        return "\x1f".join((self.client_type, self.client_subject, owner, conversation))


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


class SharedMemory(BaseModel):
    memory_id: str
    client_type: str
    client_subject: str
    account_owner: str | None = None
    conversation_id: str | None = None
    kind: MemoryKind
    content: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: MemorySensitivity
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    provenance: MemoryProvenance | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PutSharedMemoryRequest(BaseModel):
    memory_id: str | None = Field(default=None, max_length=128)
    kind: MemoryKind
    content: str = Field(min_length=1)
    source: str | None = Field(default=None, max_length=128)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    sensitivity: MemorySensitivity = "private"
    expires_at: datetime | None = None
    provenance: MemoryProvenance | None = None
    metadata: dict[str, Any] | None = None


class SharedMemoryListResponse(BaseModel):
    memories: list[SharedMemory]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
