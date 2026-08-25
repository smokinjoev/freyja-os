#!/usr/bin/env python3
"""Configure iMessage family sender mapping and verify agent routing."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = Path("/Users/freyja/freyja-os-imessage-runtime/.env")
PRODUCTION_CHECK = REPO_ROOT / "scripts" / "messaging-production-check.py"


def _parse_mapping(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"mapping must be person=address: {value}")
        person, address = value.split("=", 1)
        person = person.strip().lower()
        address = address.strip()
        if person not in {"joe", "beth", "liam", "jenna"}:
            raise ValueError(f"unsupported family member: {person}")
        if not address:
            raise ValueError(f"empty address for {person}")
        mapping[person] = address
    missing = sorted({"joe", "beth", "liam", "jenna"} - set(mapping))
    if missing:
        raise ValueError("missing family members: " + ", ".join(missing))
    return mapping


def _replace_env_line(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines()
    replacement = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map family iMessage senders to personal agents.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--restart", action="store_true", help="Restart the iMessage LaunchAgent after updating env.")
    parser.add_argument("mapping", nargs="+", help="Four mappings: joe=..., beth=..., liam=..., jenna=...")
    args = parser.parse_args(argv)

    try:
        mapping = _parse_mapping(args.mapping)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ordered = ",".join(f"{person}={mapping[person]}" for person in ("joe", "beth", "liam", "jenna"))
    _replace_env_line(args.env_file, "IMESSAGE_ALLOWED_SENDERS", ordered)

    check = subprocess.run(
        [
            sys.executable,
            str(PRODUCTION_CHECK),
            "--connector",
            "imessage",
            "--env-file",
            str(args.env_file),
            "--require-imessage-family-agents",
        ],
        text=True,
        check=False,
    )
    if check.returncode != 0:
        return check.returncode

    if args.restart:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{__import__('os').getuid()}/com.freyja-os.imessage-connector"],
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
