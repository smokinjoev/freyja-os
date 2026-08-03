from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Protocol

from freyja.identity.models import Alias, Identity, Person, Relationship


SCHEMA_VERSION = 1
_ALIAS_SEPARATOR = re.compile(r"[^a-z0-9]+")


class IdentityProvider(Protocol):
    def load(self) -> tuple[list[Person], list[Relationship]]: ...

    def replace_all(self, people: list[Person], relationships: list[Relationship]) -> None: ...


class InMemoryIdentityProvider:
    def __init__(self, people: list[Person] | None = None, relationships: list[Relationship] | None = None) -> None:
        self.people = list(people or [])
        self.relationships = list(relationships or [])

    def load(self) -> tuple[list[Person], list[Relationship]]:
        return list(self.people), list(self.relationships)

    def replace_all(self, people: list[Person], relationships: list[Relationship]) -> None:
        self.people = list(people)
        self.relationships = list(relationships)


class SQLiteIdentityProvider:
    """Versioned, transactional local identity store."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS people (
                    person_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
                    preferred_name TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS aliases (
                    person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
                    value TEXT NOT NULL, label TEXT, UNIQUE(person_id, value)
                );
                CREATE TABLE IF NOT EXISTS identities (
                    person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, value TEXT NOT NULL, label TEXT,
                    verified INTEGER NOT NULL DEFAULT 0, UNIQUE(kind, value)
                );
                CREATE TABLE IF NOT EXISTS relationships (
                    source_person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
                    relationship TEXT NOT NULL,
                    target_person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(source_person_id, relationship, target_person_id)
                );
                """
            )
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
            elif int(row[0]) != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported identity schema version: {row[0]}")
        self.path.chmod(0o600)

    def load(self) -> tuple[list[Person], list[Relationship]]:
        self.initialize()
        with self._connect() as connection:
            people: list[Person] = []
            for row in connection.execute("SELECT person_id, display_name, preferred_name, metadata_json FROM people ORDER BY person_id"):
                aliases = tuple(
                    Alias(value=item[0], label=item[1])
                    for item in connection.execute("SELECT value, label FROM aliases WHERE person_id=? ORDER BY rowid", (row[0],))
                )
                identities = tuple(
                    Identity(kind=item[0], value=item[1], label=item[2], verified=bool(item[3]))
                    for item in connection.execute(
                        "SELECT kind, value, label, verified FROM identities WHERE person_id=? ORDER BY rowid", (row[0],)
                    )
                )
                people.append(Person(row[0], row[1], row[2], aliases, identities, json.loads(row[3])))
            relationships = [
                Relationship(row[0], row[1], row[2], json.loads(row[3]))
                for row in connection.execute(
                    "SELECT source_person_id, relationship, target_person_id, metadata_json FROM relationships ORDER BY rowid"
                )
            ]
        return people, relationships

    def replace_all(self, people: list[Person], relationships: list[Relationship]) -> None:
        self.initialize()
        validate_records(people, relationships)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM relationships")
            connection.execute("DELETE FROM identities")
            connection.execute("DELETE FROM aliases")
            connection.execute("DELETE FROM people")
            for person in people:
                connection.execute(
                    "INSERT INTO people VALUES (?, ?, ?, ?)",
                    (person.person_id, person.display_name, person.preferred_name, json.dumps(person.metadata, sort_keys=True)),
                )
                connection.executemany(
                    "INSERT INTO aliases(person_id, value, label) VALUES (?, ?, ?)",
                    [(person.person_id, alias.value, alias.label) for alias in person.aliases],
                )
                connection.executemany(
                    "INSERT INTO identities(person_id, kind, value, label, verified) VALUES (?, ?, ?, ?, ?)",
                    [(person.person_id, item.kind, item.value, item.label, int(item.verified)) for item in person.identities],
                )
            connection.executemany(
                "INSERT INTO relationships VALUES (?, ?, ?, ?)",
                [(item.source_person_id, item.relationship, item.target_person_id, json.dumps(item.metadata, sort_keys=True)) for item in relationships],
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def validate_records(people: list[Person], relationships: list[Relationship]) -> None:
    person_ids: set[str] = set()
    identity_keys: set[tuple[str, str]] = set()
    alias_keys: set[str] = set()
    for person in people:
        if not person.person_id or not person.display_name:
            raise ValueError("every person requires person_id and display_name")
        if person.person_id in person_ids:
            raise ValueError(f"duplicate person_id: {person.person_id}")
        person_ids.add(person.person_id)
        for alias in person.aliases:
            key = _normalize_alias(alias.value)
            if not key:
                raise ValueError("alias value is required")
            if key in alias_keys:
                raise ValueError(f"duplicate alias: {alias.value}")
            alias_keys.add(key)
        for identity in person.identities:
            key = _identity_key(identity.kind, identity.value)
            if key in identity_keys:
                raise ValueError(f"duplicate identity: {identity.kind}:{identity.value}")
            identity_keys.add(key)
    for item in relationships:
        if item.source_person_id not in person_ids or item.target_person_id not in person_ids:
            raise ValueError("relationship references unknown person")


def _identity_key(kind: str, value: str) -> tuple[str, str]:
    if kind in {"email", "imessage"} and "@" in value:
        normalized = value.strip().lower()
    elif kind in {"phone", "signal", "imessage"}:
        stripped = value.strip()
        prefix = "+" if stripped.startswith("+") else ""
        digits = "".join(character for character in stripped if character.isdigit())
        normalized = f"{prefix}{digits}" if digits else stripped.lower()
    elif kind == "alias":
        normalized = _normalize_alias(value)
    else:
        normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"identity value is required: {kind}")
    return kind, normalized


def _normalize_alias(value: str) -> str:
    return "-".join(part for part in _ALIAS_SEPARATOR.split(value.strip().lower()) if part)
