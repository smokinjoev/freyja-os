from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def backup_identity_database(source: str | Path, destination: str | Path) -> dict:
    source_path = _existing_database(source)
    destination_path = Path(destination).expanduser()
    manifest_path = _manifest_path(destination_path)
    if destination_path.exists() or manifest_path.exists():
        raise FileExistsError(f"backup already exists: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with sqlite3.connect(source_path) as source_connection, sqlite3.connect(destination_path) as target_connection:
            source_connection.backup(target_connection)
        destination_path.chmod(0o600)
        _require_integrity(destination_path)
        manifest = {
            "format": "freyja-identity-sqlite-backup-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": _sha256(destination_path),
            "size_bytes": destination_path.stat().st_size,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        return manifest
    except Exception:
        if destination_path.exists():
            destination_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()
        raise


def verify_identity_backup(backup: str | Path) -> dict:
    backup_path = _existing_database(backup)
    manifest_path = _manifest_path(backup_path)
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("backup manifest is missing or unsafe")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "freyja-identity-sqlite-backup-v1":
        raise ValueError("unsupported identity backup format")
    if manifest.get("sha256") != _sha256(backup_path):
        raise ValueError("identity backup checksum mismatch")
    _require_integrity(backup_path)
    return {**manifest, "verified": True}


def restore_identity_database(
    backup: str | Path,
    destination: str | Path,
    *,
    replace: bool = False,
) -> dict:
    backup_path = Path(backup).expanduser()
    verify_identity_backup(backup_path)
    destination_path = Path(destination).expanduser()
    rollback_path: Path | None = None
    if destination_path.exists():
        if not replace:
            raise FileExistsError(f"destination already exists: {destination_path}")
        rollback_path = destination_path.with_suffix(destination_path.suffix + ".pre-restore.bak")
        if rollback_path.exists():
            raise FileExistsError(f"rollback backup already exists: {rollback_path}")
        backup_identity_database(destination_path, rollback_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination_path.with_suffix(destination_path.suffix + ".restore.tmp")
    if temporary.exists():
        raise FileExistsError(f"restore temporary file already exists: {temporary}")
    try:
        with sqlite3.connect(backup_path) as source_connection, sqlite3.connect(temporary) as target_connection:
            source_connection.backup(target_connection)
        temporary.chmod(0o600)
        _require_integrity(temporary)
        temporary.replace(destination_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"restored": True, "rollback_path": str(rollback_path) if rollback_path else None}


def _existing_database(path: str | Path) -> Path:
    result = Path(path).expanduser()
    if not result.is_file() or result.is_symlink():
        raise ValueError("identity database must be an existing regular file")
    return result


def _require_integrity(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not result or result[0] != "ok" or "people" not in tables or "schema_version" not in tables:
        raise ValueError("identity database integrity or schema check failed")


def _manifest_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
