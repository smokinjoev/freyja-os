from __future__ import annotations

import json
import stat
import sqlite3

import pytest

from freyja.cli.identity_import import import_document
from freyja.identity import Alias, Identity, IdentityService, Person, Relationship, SQLiteIdentityProvider


def records():
    people = [
        Person("one", "Person One", aliases=(Alias("parent"),), identities=(Identity("email", "one@example.invalid"),)),
        Person("two", "Person Two", identities=(Identity("calendar", "two-calendar"),)),
    ]
    return people, [Relationship("one", "family", "two", {"trusted": True})]


def test_sqlite_provider_persists_and_reloads(tmp_path) -> None:
    provider = SQLiteIdentityProvider(tmp_path / "state" / "identity.sqlite3")
    people, relationships = records()
    provider.replace_all(people, relationships)
    assert stat.S_IMODE(provider.path.stat().st_mode) == 0o600

    service = IdentityService(provider=SQLiteIdentityProvider(provider.path))
    assert service.resolve("parent").person_id == "one"
    assert service.resolve("ONE@example.invalid").person_id == "one"
    assert service.resolve_calendar_owner("two-calendar").person_id == "two"
    assert service.related_people("one", "family")[0].person_id == "two"


def test_provider_rejects_unknown_schema_version(tmp_path) -> None:
    provider = SQLiteIdentityProvider(tmp_path / "identity.sqlite3")
    provider.initialize()
    with sqlite3.connect(provider.path) as connection:
        connection.execute("UPDATE schema_version SET version=99")
    with pytest.raises(RuntimeError, match="unsupported identity schema"):
        provider.load()


def test_import_dry_run_does_not_create_database(tmp_path) -> None:
    source = tmp_path / "contacts.json"
    source.write_text(json.dumps({"people": [{"person_id": "one", "display_name": "One"}]}))
    database = tmp_path / "identity.sqlite3"
    result = import_document(source, database, dry_run=True)
    assert result == {"people": 1, "relationships": 0, "dry_run": True}
    assert not database.exists()


def test_duplicate_import_rolls_back_existing_data(tmp_path) -> None:
    database = tmp_path / "identity.sqlite3"
    provider = SQLiteIdentityProvider(database)
    people, relationships = records()
    provider.replace_all(people, relationships)
    source = tmp_path / "contacts.json"
    source.write_text(json.dumps({"people": [
        {"person_id": "a", "display_name": "A", "identities": [{"kind": "email", "value": "same@example.invalid"}]},
        {"person_id": "b", "display_name": "B", "identities": [{"kind": "email", "value": "same@example.invalid"}]},
    ]}))
    with pytest.raises(ValueError, match="duplicate identity"):
        import_document(source, database)
    assert [person.person_id for person in provider.load()[0]] == ["one", "two"]


def test_duplicate_aliases_are_rejected(tmp_path) -> None:
    source = tmp_path / "contacts.json"
    source.write_text(json.dumps({"people": [
        {"person_id": "a", "display_name": "A", "aliases": ["Shared Name"]},
        {"person_id": "b", "display_name": "B", "aliases": [" shared   name "]},
    ]}))
    with pytest.raises(ValueError, match="duplicate alias"):
        import_document(source, tmp_path / "identity.sqlite3")


def test_equivalent_phone_formats_are_rejected_as_duplicates(tmp_path) -> None:
    source = tmp_path / "contacts.json"
    source.write_text(json.dumps({"people": [
        {"person_id": "a", "display_name": "A", "identities": [{"kind": "signal", "value": "+1 (555) 123-4567"}]},
        {"person_id": "b", "display_name": "B", "identities": [{"kind": "signal", "value": "+15551234567"}]},
    ]}))
    with pytest.raises(ValueError, match="duplicate identity"):
        import_document(source, tmp_path / "identity.sqlite3")


def test_malformed_identity_is_rejected_instead_of_ignored(tmp_path) -> None:
    source = tmp_path / "contacts.json"
    source.write_text(json.dumps({"people": [
        {"person_id": "a", "display_name": "A", "identities": ["not-an-object"]},
    ]}))
    with pytest.raises(ValueError, match="identity requires kind and value"):
        import_document(source, tmp_path / "identity.sqlite3")
