from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from freyja.config import settings
from freyja.identity import SQLiteIdentityProvider, IdentityService
from freyja.memory.identity_migration import migrate_memory_principals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy memory principals to canonical people.")
    parser.add_argument("--memory-database", type=Path, default=Path(settings.memory_database_path))
    parser.add_argument("--identity-database", type=Path, default=Path(settings.identity_database_path))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args(argv)
    if args.apply and args.verify:
        parser.error("--apply and --verify are mutually exclusive")
    if not args.identity_database.is_file() or args.identity_database.is_symlink():
        parser.error("identity database must be an existing regular file")
    try:
        identities = IdentityService(provider=SQLiteIdentityProvider(args.identity_database))
        report = migrate_memory_principals(
            args.memory_database, identities, apply=args.apply, backup_path=args.backup,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"memory identity migration failed: {exc}\n")
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if not args.verify or report.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
