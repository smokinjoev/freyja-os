from __future__ import annotations

import stat
from pathlib import Path

import pytest

from freyja.identity import Person, SQLiteIdentityProvider
from freyja.identity.backup import backup_identity_database, restore_identity_database, verify_identity_backup


def _database(path, person_id="one"):
    provider = SQLiteIdentityProvider(path)
    provider.replace_all([Person(person_id, person_id.title())], [])
    return provider


def test_backup_verify_and_restore_round_trip(tmp_path) -> None:
    source = _database(tmp_path / "source.sqlite3")
    backup = tmp_path / "private" / "backup.sqlite3"
    manifest = backup_identity_database(source.path, backup)
    assert len(manifest["sha256"]) == 64
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.with_suffix(".sqlite3.manifest.json").stat().st_mode) == 0o600
    assert verify_identity_backup(backup)["verified"] is True
    destination = tmp_path / "restored.sqlite3"
    assert restore_identity_database(backup, destination)["restored"] is True
    people, _ = SQLiteIdentityProvider(destination).load()
    assert [person.person_id for person in people] == ["one"]


def test_tampered_backup_is_rejected(tmp_path) -> None:
    source = _database(tmp_path / "source.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    backup_identity_database(source.path, backup)
    with backup.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_identity_backup(backup)


def test_restore_requires_replace_and_creates_rollback(tmp_path) -> None:
    source = _database(tmp_path / "source.sqlite3", "new")
    backup = tmp_path / "backup.sqlite3"
    backup_identity_database(source.path, backup)
    destination = _database(tmp_path / "destination.sqlite3", "old")
    with pytest.raises(FileExistsError, match="destination already exists"):
        restore_identity_database(backup, destination.path)
    result = restore_identity_database(backup, destination.path, replace=True)
    assert result["rollback_path"]
    assert Path(result["rollback_path"]).exists()
    people, _ = SQLiteIdentityProvider(destination.path).load()
    assert [person.person_id for person in people] == ["new"]


def test_missing_or_non_identity_database_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="existing regular file"):
        backup_identity_database(tmp_path / "missing.sqlite3", tmp_path / "backup.sqlite3")
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_bytes(b"not sqlite")
    with pytest.raises(Exception):
        backup_identity_database(invalid, tmp_path / "backup.sqlite3")
