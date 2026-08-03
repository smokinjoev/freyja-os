from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from freyja.identity import IdentityService, Person, person_memory_subject
from freyja.memory.models import MemoryPrincipal
from freyja.memory.principal import stable_identity


@dataclass
class MigrationReport:
    scanned: int = 0
    migratable: int = 0
    unchanged: int = 0
    unresolved: int = 0
    ambiguous: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    applied: bool = False
    backup_path: str | None = None

    @property
    def safe_to_apply(self) -> bool:
        return not self.ambiguous and not self.conflicts

    @property
    def verified(self) -> bool:
        return self.safe_to_apply and self.migratable == 0

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "migratable": self.migratable,
            "unchanged": self.unchanged,
            "unresolved": self.unresolved,
            "ambiguous_count": len(self.ambiguous),
            "conflict_count": len(self.conflicts),
            "safe_to_apply": self.safe_to_apply,
            "verified": self.verified,
            "applied": self.applied,
            "backup_path": self.backup_path,
        }


def migrate_memory_principals(
    memory_database: str | Path,
    identities: IdentityService,
    *,
    apply: bool = False,
    backup_path: str | Path | None = None,
) -> MigrationReport:
    database = Path(memory_database).expanduser()
    if not database.is_file() or database.is_symlink():
        raise ValueError("memory database must be an existing regular file")
    candidates = _candidate_subjects(identities)
    report = MigrationReport()
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "shared_memories" not in tables:
            raise ValueError("memory database does not contain shared_memories")
        rows = connection.execute("SELECT * FROM shared_memories ORDER BY row_id").fetchall()
        report.scanned = len(rows)
        plans: list[tuple[sqlite3.Row, Person, str]] = []
        target_keys: dict[tuple[str, str], str] = {}
        for row in rows:
            matches = candidates.get(row["client_subject"], [])
            if not matches:
                report.unresolved += 1
                continue
            if len(matches) > 1:
                report.ambiguous.append(row["row_id"])
                continue
            person = matches[0]
            subject = person_memory_subject(person)
            target_scope = MemoryPrincipal(
                client_type=row["client_type"], client_subject=subject,
                account_owner=row["account_owner"], conversation_id=row["conversation_id"],
            ).scope_key
            if row["client_subject"] == subject and row["principal_scope"] == target_scope:
                report.unchanged += 1
                continue
            key = (target_scope, row["memory_id"])
            existing = target_keys.get(key)
            if existing or connection.execute(
                "SELECT row_id FROM shared_memories WHERE principal_scope=? AND memory_id=? AND row_id<>?",
                (target_scope, row["memory_id"], row["row_id"]),
            ).fetchone():
                report.conflicts.append(row["row_id"])
                continue
            target_keys[key] = row["row_id"]
            plans.append((row, person, target_scope))
        report.migratable = len(plans)
        if not apply:
            return report
        if not report.safe_to_apply:
            raise ValueError("identity-memory migration has ambiguous mappings or conflicts")
        if not plans:
            report.applied = True
            return report
        destination = Path(backup_path) if backup_path else database.with_suffix(database.suffix + ".pre-identity-migration.bak")
        if destination.exists():
            raise FileExistsError(f"backup already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(destination) as backup_connection:
            connection.backup(backup_connection)
        destination.chmod(0o600)
        report.backup_path = str(destination)
        try:
            connection.execute("BEGIN IMMEDIATE")
            for row, person, target_scope in plans:
                metadata = json.loads(row["metadata"] or "{}")
                metadata["identity_migration"] = {
                    "person_id": person.person_id,
                    "migrated_at": datetime.now(UTC).isoformat(),
                    "source": "canonical_identity",
                }
                connection.execute(
                    "UPDATE shared_memories SET principal_scope=?, client_subject=?, metadata=? WHERE row_id=?",
                    (target_scope, person_memory_subject(person), json.dumps(metadata, sort_keys=True), row["row_id"]),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        report.applied = True
        return report


def _candidate_subjects(service: IdentityService) -> dict[str, list[Person]]:
    candidates: dict[str, list[Person]] = {}
    for person in service.people.values():
        values = {person.person_id, person.display_name, person.preferred_name or ""}
        values.update(alias.value for alias in person.aliases)
        subjects = {person_memory_subject(person)}
        for value in values:
            if value:
                safe = "-".join(part for part in value.strip().lower().replace("_", "-").split("-") if part)
                subjects.add(stable_identity("family-member", safe))
        for identity in person.identities:
            subjects.add(stable_identity(identity.kind, identity.value))
            if identity.kind == "phone":
                subjects.update({stable_identity("signal", identity.value), stable_identity("imessage", identity.value)})
            if identity.kind == "email":
                subjects.add(stable_identity("imessage", identity.value))
        for subject in subjects:
            if person not in candidates.setdefault(subject, []):
                candidates[subject].append(person)
    return candidates
