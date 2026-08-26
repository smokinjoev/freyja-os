from __future__ import annotations

import pytest

from freyja.foundation_models import AuditEvent, AuditEventType, SecurityDomainId
from freyja.freyja3_audit import Freyja3AuditAccessError, Freyja3AuditQuery, Freyja3AuditStore


def test_audit_store_records_and_filters_events(tmp_path) -> None:
    store = Freyja3AuditStore(tmp_path / "audit.db")
    event = AuditEvent(
        event_type=AuditEventType.AGENT_TOOL_SELECTED,
        actor_id="agent:cloyd-gibbler",
        domain_id=SecurityDomainId.PERSON_JOE,
        target_id="git.inspect",
        allowed=True,
        reason="unit test",
    )

    count = store.record_many([event], writer_domain_id=SecurityDomainId.SYSTEM, trace_id="trace-1", conversation_id="conv-1")
    listed = store.list(Freyja3AuditQuery(trace_id="trace-1"), reader_domain_id=SecurityDomainId.HOUSEHOLD)

    assert count == 1
    assert listed == [event]


def test_audit_store_enforces_system_writer_and_household_reader(tmp_path) -> None:
    store = Freyja3AuditStore(tmp_path / "audit.db")
    event = AuditEvent(
        event_type=AuditEventType.AGENT_RUN_STARTED,
        actor_id="agent:freyja",
        domain_id=SecurityDomainId.HOUSEHOLD,
        allowed=True,
        reason="unit test",
    )

    with pytest.raises(Freyja3AuditAccessError):
        store.record_many([event], writer_domain_id=SecurityDomainId.PERSON_JOE)

    with pytest.raises(Freyja3AuditAccessError):
        store.list(reader_domain_id=SecurityDomainId.PERSON_BETH)
