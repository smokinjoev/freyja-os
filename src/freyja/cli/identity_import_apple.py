from __future__ import annotations

import argparse
import json
from pathlib import Path

from freyja.config import settings
from freyja.identity import SQLiteIdentityProvider
from freyja.identity.apple_contacts import load_apple_contacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Freyja's native Apple Contacts into identity storage.")
    parser.add_argument("--database", type=Path, default=Path(settings.identity_database_path))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Required before writing the identity database.")
    parser.add_argument(
        "--request-access",
        action="store_true",
        help="Explicitly allow macOS to show the initial Contacts permission prompt.",
    )
    args = parser.parse_args(argv)
    if not args.dry_run and not args.replace:
        parser.error("use --dry-run first; --replace is required to write")
    try:
        people = load_apple_contacts(request_access=args.request_access)
        if not args.dry_run:
            SQLiteIdentityProvider(args.database).replace_all(people, [])
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"Apple Contacts import failed: {exc}\n")
    print(json.dumps({"people": len(people), "relationships": 0, "dry_run": args.dry_run}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
