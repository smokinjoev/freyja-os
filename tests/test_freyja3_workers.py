from __future__ import annotations

import pytest

from freyja.foundation_models import SecurityDomainId
from freyja.freyja3_workers import (
    Freyja3WorkerAccessError,
    Freyja3WorkerJobComplete,
    Freyja3WorkerJobCreate,
    Freyja3WorkerJobQuery,
    Freyja3WorkerJobStatus,
    Freyja3WorkerJobStore,
)


def test_freyja3_worker_job_lifecycle_targets_mars(tmp_path) -> None:
    store = Freyja3WorkerJobStore(tmp_path / "workers.db")
    created = store.create(
        Freyja3WorkerJobCreate(
            worker_class="ingestion",
            target_machine_id="mars",
            objective="Summarize queued documents.",
            payload={"batch": "docs"},
        ),
        writer_domain_id=SecurityDomainId.HOUSEHOLD,
    )

    assert created.status == Freyja3WorkerJobStatus.PENDING
    assert store.claim_next(machine_id="atlas", worker_class="ingestion", claimer_domain_id=SecurityDomainId.SYSTEM) is None
    claimed = store.claim_next(machine_id="mars", worker_class="ingestion", claimer_domain_id=SecurityDomainId.SYSTEM)
    assert claimed is not None
    assert claimed.job_id == created.job_id
    assert claimed.status == Freyja3WorkerJobStatus.RUNNING
    assert claimed.claimed_by_machine_id == "mars"

    completed = store.complete(
        created.job_id,
        Freyja3WorkerJobComplete(status=Freyja3WorkerJobStatus.COMPLETED, result={"processed": 2}),
        machine_id="mars",
        completer_domain_id=SecurityDomainId.SYSTEM,
    )

    assert completed.status == Freyja3WorkerJobStatus.COMPLETED
    assert completed.result == {"processed": 2}
    assert store.list(reader_domain_id=SecurityDomainId.HOUSEHOLD) == []
    assert store.list(Freyja3WorkerJobQuery(include_completed=True), reader_domain_id=SecurityDomainId.HOUSEHOLD)[0].job_id == created.job_id


def test_freyja3_worker_job_claim_requires_system_domain(tmp_path) -> None:
    store = Freyja3WorkerJobStore(tmp_path / "workers.db")
    store.create(
        Freyja3WorkerJobCreate(worker_class="monitoring", objective="Check worker health."),
        writer_domain_id=SecurityDomainId.SYSTEM,
    )

    with pytest.raises(Freyja3WorkerAccessError):
        store.claim_next(machine_id="mars", worker_class=None, claimer_domain_id=SecurityDomainId.HOUSEHOLD)


def test_freyja3_worker_job_completion_requires_claiming_machine(tmp_path) -> None:
    store = Freyja3WorkerJobStore(tmp_path / "workers.db")
    created = store.create(
        Freyja3WorkerJobCreate(worker_class="monitoring", objective="Check worker health."),
        writer_domain_id=SecurityDomainId.SYSTEM,
    )
    store.claim_next(machine_id="mars", worker_class=None, claimer_domain_id=SecurityDomainId.SYSTEM)

    with pytest.raises(KeyError):
        store.complete(
            created.job_id,
            Freyja3WorkerJobComplete(status=Freyja3WorkerJobStatus.COMPLETED),
            machine_id="atlas",
            completer_domain_id=SecurityDomainId.SYSTEM,
        )
