from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkerTrustLevel(StrEnum):
    TRUSTED_INTERNAL = "trusted_internal"
    UNTRUSTED_EXTERNAL_CONTENT = "untrusted_external_content"


class ExternalWorkerClass(StrEnum):
    WEB_RESEARCH = "web_research"
    EMAIL_CONTENT = "email_content"
    DOCUMENT_INGESTION = "document_ingestion"
    SCRAPING = "scraping"


DEFAULT_UNTRUSTED_EXCLUDED_CAPABILITIES = frozenset(
    {
        "memory.authoritative_write",
        "message.send",
        "home.control",
        "admin.configuration",
        "privileged.execution",
    }
)


CAPABILITY_ALIASES = {
    "memory_put_shared": "memory.authoritative_write",
    "memory_write": "memory.authoritative_write",
    "signal_send": "message.send",
    "imessage_send": "message.send",
    "gmail_send": "message.send",
    "home_assistant_control_state": "home.control",
    "restart_director": "admin.configuration",
    "write_pilot_file_write": "privileged.execution",
    "write_pilot_git_add": "privileged.execution",
    "write_pilot_git_commit": "privileged.execution",
    "run_test_suite": "privileged.execution",
}


class WorkerPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str
    worker_class: ExternalWorkerClass
    trust_level: WorkerTrustLevel
    capability: str
    canonical_capability: str


class WorkerObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_class: ExternalWorkerClass
    trust_level: WorkerTrustLevel
    source: str
    summary: str
    facts: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty: str | None = None
    proposed_capabilities: list[str] = Field(default_factory=list)


class WorkerPolicy:
    def __init__(
        self,
        *,
        excluded_capabilities: set[str] | None = None,
    ) -> None:
        self.excluded_capabilities = set(excluded_capabilities or DEFAULT_UNTRUSTED_EXCLUDED_CAPABILITIES)

    def canonical_capability(self, capability: str) -> str:
        return CAPABILITY_ALIASES.get(capability, capability)

    def authorize(
        self,
        *,
        worker_class: ExternalWorkerClass,
        trust_level: WorkerTrustLevel,
        capability: str,
    ) -> WorkerPolicyDecision:
        canonical = self.canonical_capability(capability)
        if trust_level == WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT and canonical in self.excluded_capabilities:
            return WorkerPolicyDecision(
                allowed=False,
                reason="untrusted external content cannot invoke excluded capability",
                worker_class=worker_class,
                trust_level=trust_level,
                capability=capability,
                canonical_capability=canonical,
            )
        return WorkerPolicyDecision(
            allowed=True,
            reason="capability allowed for worker trust level",
            worker_class=worker_class,
            trust_level=trust_level,
            capability=capability,
            canonical_capability=canonical,
        )

    def validate_observation(self, observation: WorkerObservation) -> list[WorkerPolicyDecision]:
        return [
            self.authorize(
                worker_class=observation.worker_class,
                trust_level=observation.trust_level,
                capability=capability,
            )
            for capability in observation.proposed_capabilities
        ]
