from __future__ import annotations

import pytest

from freyja.foundation_models import MemoryClassification, MemoryScope, SecurityDomainId
from freyja.freyja3_memory import Freyja3MemoryAccessError, Freyja3MemoryQuery, Freyja3MemoryStore, Freyja3MemoryWrite


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
