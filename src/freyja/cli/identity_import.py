from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from freyja.config import settings
from freyja.identity import Alias, Identity, Person, Relationship, SQLiteIdentityProvider
from freyja.identity.providers import validate_records


def load_document(path: Path) -> tuple[list[Person], list[Relationship]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("people"), list):
        raise ValueError("document must contain a people array")
    people = [_person(item) for item in data["people"]]
    relationships = [_relationship(item) for item in data.get("relationships", [])]
    return people, relationships


def import_document(source: Path, database: Path, *, dry_run: bool = False) -> dict[str, Any]:
    people, relationships = load_document(source)
    # Validation and duplicate detection happen before any write.
    validate_records(people, relationships)
    if not dry_run:
        SQLiteIdentityProvider(database).replace_all(people, relationships)
    return {"people": len(people), "relationships": len(relationships), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import private contacts into Freyja's local identity store.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--database", type=Path, default=Path(settings.identity_database_path))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = import_document(args.source, args.database, dry_run=args.dry_run)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"identity import failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


def _person(data: Any) -> Person:
    if not isinstance(data, dict):
        raise ValueError("each person must be an object")
    raw_aliases = data.get("aliases", [])
    raw_identities = data.get("identities", [])
    if not isinstance(raw_aliases, list) or not isinstance(raw_identities, list):
        raise ValueError("aliases and identities must be arrays")
    aliases: list[Alias] = []
    for item in raw_aliases:
        if isinstance(item, dict):
            if "value" not in item:
                raise ValueError("alias object requires value")
            aliases.append(Alias(str(item["value"]), item.get("label")))
        elif isinstance(item, str):
            aliases.append(Alias(item))
        else:
            raise ValueError("alias must be a string or object")
    identities: list[Identity] = []
    for item in raw_identities:
        if not isinstance(item, dict) or "kind" not in item or "value" not in item:
            raise ValueError("identity requires kind and value")
        identities.append(Identity(str(item["kind"]), str(item["value"]), item.get("label"), bool(item.get("verified", False))))
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("person metadata must be an object")
    return Person(str(data.get("person_id", "")), str(data.get("display_name", "")), data.get("preferred_name"), tuple(aliases), tuple(identities), metadata)


def _relationship(data: Any) -> Relationship:
    if not isinstance(data, dict):
        raise ValueError("each relationship must be an object")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("relationship metadata must be an object")
    return Relationship(str(data.get("source_person_id", "")), str(data.get("relationship", "")), str(data.get("target_person_id", "")), metadata)


if __name__ == "__main__":
    raise SystemExit(main())
