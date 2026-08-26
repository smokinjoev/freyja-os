from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from freyja.foundation_models import AuditEvent, AuditEventType, MemoryClassification, PersistentAgent


_SECRET_PATTERNS = (
    re.compile(r"\b(api[_-]?key|token|password|secret)\s*[:=]", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)
_PII_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{16}\b"),
)


class EgressDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    allowed: bool
    classification: MemoryClassification
    destination_provider: str
    redacted_prompt: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_event: AuditEvent


class PrivacyEgressGate:
    """Mandatory cloud AI egress policy for Freyja 3 agents."""

    def evaluate(
        self,
        *,
        agent: PersistentAgent,
        prompt: str,
        destination_provider: str,
        requested_classification: MemoryClassification | None = None,
        one_request_override: bool = False,
    ) -> EgressDecision:
        classification = requested_classification or self.classify(prompt)
        redacted = self.redact(prompt)
        if classification in {MemoryClassification.RESTRICTED, MemoryClassification.SENSITIVE} and not one_request_override:
            return self._decision(
                agent=agent,
                allowed=False,
                classification=classification,
                destination_provider=destination_provider,
                redacted_prompt=redacted,
                reason=f"{classification.value} data cannot leave trusted local machines without override",
            )
        if classification == MemoryClassification.PRIVATE and not one_request_override:
            return self._decision(
                agent=agent,
                allowed=False,
                classification=classification,
                destination_provider=destination_provider,
                redacted_prompt=redacted,
                reason="private data defaults to local inference",
            )
        return self._decision(
            agent=agent,
            allowed=True,
            classification=classification,
            destination_provider=destination_provider,
            redacted_prompt=redacted,
            reason="cloud egress allowed by policy after minimization",
        )

    def classify(self, prompt: str) -> MemoryClassification:
        if any(pattern.search(prompt) for pattern in _SECRET_PATTERNS):
            return MemoryClassification.RESTRICTED
        lowered = prompt.lower()
        if any(term in lowered for term in ("ssn", "social security", "medical", "legal case")):
            return MemoryClassification.SENSITIVE
        if any(pattern.search(prompt) for pattern in _PII_PATTERNS):
            return MemoryClassification.PRIVATE
        return MemoryClassification.ROUTINE

    def redact(self, prompt: str) -> str:
        redacted = prompt
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED_SECRET]=", redacted)
        for pattern in _PII_PATTERNS:
            redacted = pattern.sub("[REDACTED_PII]", redacted)
        return redacted

    def _decision(
        self,
        *,
        agent: PersistentAgent,
        allowed: bool,
        classification: MemoryClassification,
        destination_provider: str,
        redacted_prompt: str,
        reason: str,
    ) -> EgressDecision:
        audit_event = AuditEvent(
            event_type=AuditEventType.PRIVACY_EGRESS_ALLOWED if allowed else AuditEventType.PRIVACY_EGRESS_DENIED,
            actor_id=f"agent:{agent.agent_id}",
            domain_id=agent.security_domain_id,
            target_id=destination_provider,
            allowed=allowed,
            reason=reason,
            metadata={"classification": classification.value},
        )
        return EgressDecision(
            allowed=allowed,
            classification=classification,
            destination_provider=destination_provider,
            redacted_prompt=redacted_prompt,
            reason=reason,
            audit_event=audit_event,
        )
