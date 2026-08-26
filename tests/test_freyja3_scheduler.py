from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from freyja.foundation_models import SecurityDomainId
from freyja.freyja3_scheduler import Freyja3ScheduleAccessError, Freyja3ScheduleCreate, Freyja3ScheduleQuery, Freyja3SchedulerStore


def test_scheduler_stores_due_agent_envelopes(tmp_path) -> None:
    store = Freyja3SchedulerStore(tmp_path / "scheduler.db")
    now = datetime.now(UTC)

    created = store.create(
        Freyja3ScheduleCreate(
            due_at=now,
            target_agent_id="freyja",
            resolved_user_id="joe",
            conversation_id="conv-scheduler",
            text="Check household status.",
        ),
        writer_domain_id=SecurityDomainId.HOUSEHOLD,
    )
    due = store.list(Freyja3ScheduleQuery(due_before=now + timedelta(seconds=1)), reader_domain_id=SecurityDomainId.SYSTEM)

    assert due == [created]
    assert due[0].target_agent_id == "freyja"
    assert due[0].text == "Check household status."


def test_scheduler_enforces_household_or_system_access(tmp_path) -> None:
    store = Freyja3SchedulerStore(tmp_path / "scheduler.db")

    with pytest.raises(Freyja3ScheduleAccessError):
        store.create(
            Freyja3ScheduleCreate(
                due_at=datetime.now(UTC),
                target_agent_id="cloyd-gibbler",
                conversation_id="conv-private",
                text="Private reminder.",
            ),
            writer_domain_id=SecurityDomainId.PERSON_BETH,
        )

    with pytest.raises(Freyja3ScheduleAccessError):
        store.list(reader_domain_id=SecurityDomainId.PERSON_JOE)


def test_scheduler_marks_dispatched_once(tmp_path) -> None:
    store = Freyja3SchedulerStore(tmp_path / "scheduler.db")
    schedule = store.create(
        Freyja3ScheduleCreate(
            due_at=datetime.now(UTC),
            target_agent_id="cloyd-gibbler",
            resolved_user_id="joe",
            conversation_id="conv-once",
            text="Run once.",
        ),
        writer_domain_id=SecurityDomainId.SYSTEM,
    )

    dispatched = store.mark_dispatched(schedule.schedule_id, dispatcher_domain_id=SecurityDomainId.SYSTEM)

    assert dispatched.dispatched_at is not None
    assert store.list(reader_domain_id=SecurityDomainId.SYSTEM) == []
    with pytest.raises(KeyError):
        store.mark_dispatched(schedule.schedule_id, dispatcher_domain_id=SecurityDomainId.SYSTEM)
