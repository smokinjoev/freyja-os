from __future__ import annotations

import pytest

from freyja.foundation_models import MemoryClassification, MemoryScope, SecurityDomainId
from freyja.freyja3_memory import (
    Freyja3MemoryAccessError,
    Freyja3MemoryCandidateQuery,
    Freyja3MemoryCandidateReview,
    Freyja3MemoryCandidateStatus,
    Freyja3MemoryCandidateWrite,
    Freyja3MemoryQuery,
    Freyja3MemoryStore,
    Freyja3MemoryWrite,
)


def test_freyja3_private_memory_is_owner_scoped(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    record = store.put(
        Freyja3MemoryWrite(
            owner_domain_id=SecurityDomainId.PERSON_JOE,
            scope=MemoryScope.PERSONAL,
            source_agent_id="cloyd-gibbler",
            content="Joe prefers concise status updates.",
            provenance="unit-test",
            classification=MemoryClassification.PRIVATE,
        ),
        writer_domain_id=SecurityDomainId.PERSON_JOE,
    )

    joe = store.get(record.memory_id, reader_domain_id=SecurityDomainId.PERSON_JOE)
    assert joe is not None
    assert joe.content == "Joe prefers concise status updates."
    with pytest.raises(Freyja3MemoryAccessError):
        store.get(record.memory_id, reader_domain_id=SecurityDomainId.PERSON_BETH)


def test_freyja3_shared_memory_allows_explicit_household_reader(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    store.put(
        Freyja3MemoryWrite(
            owner_domain_id=SecurityDomainId.PERSON_JOE,
            scope=MemoryScope.HOUSEHOLD,
            source_agent_id="cloyd-gibbler",
            content="The family prefers the downstairs thermostat at 71.",
            provenance="unit-test",
            classification=MemoryClassification.ROUTINE,
            allowed_reader_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD}),
        ),
        writer_domain_id=SecurityDomainId.PERSON_JOE,
    )

    records = store.list(Freyja3MemoryQuery(scope=MemoryScope.HOUSEHOLD), reader_domain_id=SecurityDomainId.HOUSEHOLD)

    assert len(records) == 1
    assert records[0].scope == MemoryScope.HOUSEHOLD


def test_freyja3_paralegal_memory_is_separate_from_household(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    store.put(
        Freyja3MemoryWrite(
            owner_domain_id=SecurityDomainId.PARALEGAL,
            scope=MemoryScope.ENCLAVE,
            source_agent_id="legal-agent",
            content="Privileged legal case note.",
            provenance="unit-test",
            classification=MemoryClassification.RESTRICTED,
        ),
        writer_domain_id=SecurityDomainId.PARALEGAL,
    )

    assert store.list(reader_domain_id=SecurityDomainId.HOUSEHOLD) == []
    with pytest.raises(Freyja3MemoryAccessError):
        store.put(
            Freyja3MemoryWrite(
                owner_domain_id=SecurityDomainId.PARALEGAL,
                scope=MemoryScope.ENCLAVE,
                source_agent_id="benedict",
                content="Benedict must not write here.",
                provenance="unit-test",
                classification=MemoryClassification.RESTRICTED,
            ),
            writer_domain_id=SecurityDomainId.PERSON_BETH,
        )


def test_freyja3_memory_candidate_requires_review_before_durable_write(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    candidate = store.propose_candidate(
        Freyja3MemoryCandidateWrite(
            owner_domain_id=SecurityDomainId.PERSON_JOE,
            scope=MemoryScope.PERSONAL,
            source_agent_id="cloyd-gibbler",
            content="Joe likely prefers architecture-first status.",
            provenance="model-assisted-candidate",
            classification=MemoryClassification.PRIVATE,
            metadata={"conversation_id": "conv-candidate"},
        ),
        proposer_domain_id=SecurityDomainId.PERSON_JOE,
    )

    assert candidate.status == Freyja3MemoryCandidateStatus.PENDING
    assert store.list(reader_domain_id=SecurityDomainId.PERSON_JOE) == []
    pending = store.list_candidates(
        Freyja3MemoryCandidateQuery(status=Freyja3MemoryCandidateStatus.PENDING),
        reader_domain_id=SecurityDomainId.PERSON_JOE,
    )
    assert [item.candidate_id for item in pending] == [candidate.candidate_id]


def test_freyja3_memory_candidate_approval_creates_memory(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    candidate = store.propose_candidate(
        Freyja3MemoryCandidateWrite(
            owner_domain_id=SecurityDomainId.PERSON_JOE,
            scope=MemoryScope.PERSONAL,
            source_agent_id="cloyd-gibbler",
            content="Joe prefers five-point readiness checks.",
            provenance="model-assisted-candidate",
            classification=MemoryClassification.PRIVATE,
        ),
        proposer_domain_id=SecurityDomainId.PERSON_JOE,
    )

    reviewed, memory = store.review_candidate(
        candidate.candidate_id,
        Freyja3MemoryCandidateReview(decision="approve", reason="Joe confirmed this preference."),
        reviewer_domain_id=SecurityDomainId.PERSON_JOE,
    )

    assert reviewed.status == Freyja3MemoryCandidateStatus.APPROVED
    assert memory is not None
    assert reviewed.approved_memory_id == memory.memory_id
    assert memory.provenance == f"approved-memory-candidate:{candidate.candidate_id}"
    assert memory.metadata["candidate_id"] == candidate.candidate_id


def test_freyja3_memory_candidate_review_denies_other_private_domain(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    candidate = store.propose_candidate(
        Freyja3MemoryCandidateWrite(
            owner_domain_id=SecurityDomainId.PERSON_JOE,
            scope=MemoryScope.PERSONAL,
            source_agent_id="cloyd-gibbler",
            content="Joe prefers private memory.",
            provenance="model-assisted-candidate",
            classification=MemoryClassification.PRIVATE,
        ),
        proposer_domain_id=SecurityDomainId.PERSON_JOE,
    )

    with pytest.raises(Freyja3MemoryAccessError):
        store.review_candidate(
            candidate.candidate_id,
            Freyja3MemoryCandidateReview(decision="approve"),
            reviewer_domain_id=SecurityDomainId.PERSON_BETH,
        )


def test_freyja3_paralegal_memory_candidates_are_separate_from_household(tmp_path) -> None:
    store = Freyja3MemoryStore(tmp_path / "memory.db")
    candidate = store.propose_candidate(
        Freyja3MemoryCandidateWrite(
            owner_domain_id=SecurityDomainId.PARALEGAL,
            scope=MemoryScope.ENCLAVE,
            source_agent_id="legal-agent",
            content="Privileged legal memory candidate.",
            provenance="model-assisted-candidate",
            classification=MemoryClassification.RESTRICTED,
        ),
        proposer_domain_id=SecurityDomainId.PARALEGAL,
    )

    assert store.list_candidates(reader_domain_id=SecurityDomainId.HOUSEHOLD) == []
    with pytest.raises(Freyja3MemoryAccessError):
        store.review_candidate(
            candidate.candidate_id,
            Freyja3MemoryCandidateReview(decision="approve"),
            reviewer_domain_id=SecurityDomainId.PERSON_BETH,
        )
