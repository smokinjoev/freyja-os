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
    aliases = tuple(Alias(str(item["value"]), item.get("label")) if isinstance(item, dict) else Alias(str(item)) for item in data.get("aliases", []))
    identities = tuple(
        Identity(str(item["kind"]), str(item["value"]), item.get("label"), bool(item.get("verified", False)))
        for item in data.get("identities", [])
        if isinstance(item, dict)
    )
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("person metadata must be an object")
    return Person(str(data.get("person_id", "")), str(data.get("display_name", "")), data.get("preferred_name"), aliases, identities, metadata)


def _relationship(data: Any) -> Relationship:
    if not isinstance(data, dict):
        raise ValueError("each relationship must be an object")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("relationship metadata must be an object")
    return Relationship(str(data.get("source_person_id", "")), str(data.get("relationship", "")), str(data.get("target_person_id", "")), metadata)


if __name__ == "__main__":
    raise SystemExit(main())
