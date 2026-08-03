from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from freyja.identity.backup import backup_identity_database, restore_identity_database, verify_identity_backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up, verify, or restore Freyja identity SQLite data.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("source", type=Path)
    backup.add_argument("destination", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("backup", type=Path)
    restore.add_argument("destination", type=Path)
    restore.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = backup_identity_database(args.source, args.destination)
        elif args.command == "verify":
            result = verify_identity_backup(args.backup)
        else:
            result = restore_identity_database(args.backup, args.destination, replace=args.replace)
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        parser.exit(2, f"identity backup operation failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
