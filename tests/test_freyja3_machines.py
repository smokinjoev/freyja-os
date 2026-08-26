from __future__ import annotations

import pytest

from freyja.foundation_models import SecurityDomainId
from freyja.freyja3_machines import Freyja3MachineAccessError, Freyja3MachineHeartbeat, Freyja3MachineStatusStore


def test_machine_status_store_records_latest_heartbeat(tmp_path) -> None:
    store = Freyja3MachineStatusStore(tmp_path / "machines.db")

    first = store.heartbeat(
        Freyja3MachineHeartbeat(machine_id="mars", role="worker-ingestion-monitoring", status="ok", commit_sha="abc123"),
        writer_domain_id=SecurityDomainId.SYSTEM,
    )
    second = store.heartbeat(
        Freyja3MachineHeartbeat(machine_id="mars", role="worker-ingestion-monitoring", status="degraded", commit_sha="def456"),
        writer_domain_id=SecurityDomainId.SYSTEM,
    )
    listed = store.list(reader_domain_id=SecurityDomainId.HOUSEHOLD)

    assert first.machine_id == "mars"
    assert listed == [second]
    assert listed[0].status == "degraded"
    assert listed[0].commit_sha == "def456"


def test_machine_status_store_enforces_system_writer_and_household_reader(tmp_path) -> None:
    store = Freyja3MachineStatusStore(tmp_path / "machines.db")

    with pytest.raises(Freyja3MachineAccessError):
        store.heartbeat(
            Freyja3MachineHeartbeat(machine_id="atlas", role="persistent-infrastructure"),
            writer_domain_id=SecurityDomainId.PERSON_JOE,
        )

    with pytest.raises(Freyja3MachineAccessError):
        store.list(reader_domain_id=SecurityDomainId.PERSON_BETH)
