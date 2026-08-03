from __future__ import annotations

import argparse
import json
from pathlib import Path

from freyja.config import settings
from freyja.identity import SQLiteIdentityProvider
from freyja.identity.vcard import parse_vcards


def import_vcards(source: Path, database: Path, *, dry_run: bool = False, replace: bool = False) -> dict:
    if not dry_run and not replace:
        raise ValueError("use --dry-run first; --replace is required to write")
    people = parse_vcards(source.read_text(encoding="utf-8"))
    if not dry_run:
        SQLiteIdentityProvider(database).replace_all(people, [])
    return {"people": len(people), "relationships": 0, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import an offline vCard export into Freyja identity storage.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--database", type=Path, default=Path(settings.identity_database_path))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Required before writing the identity database.")
    args = parser.parse_args(argv)
    try:
        result = import_vcards(args.source, args.database, dry_run=args.dry_run, replace=args.replace)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"vCard import failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
