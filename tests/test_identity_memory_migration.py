from __future__ import annotations

import sqlite3
import stat

import pytest

from freyja.identity import Identity, IdentityService, Person, person_memory_subject
from freyja.memory.identity_migration import migrate_memory_principals
from freyja.memory.models import MemoryPrincipal, PutSharedMemoryRequest
from freyja.memory.principal import stable_identity
from freyja.memory.store import MemoryStore


def _setup(tmp_path):
    database = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(database))
    legacy = MemoryPrincipal(client_type="signal", client_subject=stable_identity("signal", "+15551234567"), conversation_id="signal-conv:one")
    store.put_shared_memory(legacy, PutSharedMemoryRequest(memory_id="timezone", kind="preference", content="Eastern", source="test"))
    identity = IdentityService(people=[Person("person-one", "Person One", identities=(Identity("phone", "+15551234567"),))])
    return database, store, legacy, identity


def test_dry_run_does_not_change_memory(tmp_path) -> None:
    database, store, legacy, identity = _setup(tmp_path)
    report = migrate_memory_principals(database, identity)
    assert report.migratable == 1 and report.applied is False
    assert store.list_shared_memories(legacy).memories


def test_apply_backs_up_and_unifies_connector_scope(tmp_path) -> None:
    database, store, _legacy, identity = _setup(tmp_path)
    backup = tmp_path / "backup.sqlite3"
    report = migrate_memory_principals(database, identity, apply=True, backup_path=backup)
    assert report.applied and backup.exists()
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    subject = person_memory_subject(identity.require_person("person-one"))
    signal = MemoryPrincipal(client_type="signal", client_subject=subject, conversation_id="signal-conv:one")
    imessage = MemoryPrincipal(client_type="imessage", client_subject=subject, conversation_id="imessage-conv:two")
    assert store.list_shared_memories(signal).memories[0].content == "Eastern"
    assert store.list_shared_memories(imessage).memories[0].content == "Eastern"
    assert migrate_memory_principals(database, identity).migratable == 0


def test_conflict_refuses_apply_without_backup(tmp_path) -> None:
    database, store, _legacy, identity = _setup(tmp_path)
    canonical = MemoryPrincipal(client_type="imessage", client_subject=person_memory_subject(identity.require_person("person-one")))
    store.put_shared_memory(canonical, PutSharedMemoryRequest(memory_id="timezone", kind="preference", content="Other", source="test"))
    backup = tmp_path / "backup.sqlite3"
    report = migrate_memory_principals(database, identity)
    assert report.conflicts
    with pytest.raises(ValueError, match="ambiguous mappings or conflicts"):
        migrate_memory_principals(database, identity, apply=True, backup_path=backup)
    assert not backup.exists()


def test_ambiguous_mapping_is_reported(tmp_path) -> None:
    database, _store, _legacy, _identity = _setup(tmp_path)
    identity = IdentityService(people=[
        Person("one", "One", identities=(Identity("phone", "+15551234567"),)),
        Person("two", "Two", identities=(Identity("phone", "+15551234567"),)),
    ])
    report = migrate_memory_principals(database, identity)
    assert report.ambiguous and not report.safe_to_apply


def test_missing_or_invalid_database_is_rejected(tmp_path) -> None:
    identity = IdentityService(people=[Person("one", "One")])
    with pytest.raises(ValueError, match="existing regular file"):
        migrate_memory_principals(tmp_path / "missing.sqlite3", identity)
    invalid = tmp_path / "invalid.sqlite3"
    sqlite3.connect(invalid).close()
    with pytest.raises(ValueError, match="does not contain shared_memories"):
        migrate_memory_principals(invalid, identity)


def test_apply_with_nothing_to_change_is_verified_without_backup(tmp_path) -> None:
    database, _store, _legacy, identity = _setup(tmp_path)
    first_backup = tmp_path / "first.sqlite3"
    migrate_memory_principals(database, identity, apply=True, backup_path=first_backup)
    unused_backup = tmp_path / "unused.sqlite3"
    report = migrate_memory_principals(database, identity, apply=True, backup_path=unused_backup)
    assert report.applied and report.verified
    assert not unused_backup.exists()
