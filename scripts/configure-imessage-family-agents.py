#!/usr/bin/env python3
"""Configure iMessage family sender mapping and verify agent routing."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for import_path in (REPO_ROOT, REPO_ROOT / "src"):
    path_value = str(import_path)
    if path_value not in sys.path:
        sys.path.insert(0, path_value)

from freyja.identity import Alias, Identity, Person, Relationship
from freyja.identity.providers import SQLiteIdentityProvider


DEFAULT_ENV = Path("/Users/freyja/freyja-os-imessage-runtime/.env")
DEFAULT_IDENTITY_DB = Path("/Users/freyja/.local/state/freyja/identity.sqlite3")
PRODUCTION_CHECK = REPO_ROOT / "scripts" / "messaging-production-check.py"
FAMILY = ("joe", "beth", "liam", "jenna")


def _parse_mapping(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"mapping must be person=address: {value}")
        person, address = value.split("=", 1)
        person = person.strip().lower()
        address = address.strip()
        if person not in FAMILY:
            raise ValueError(f"unsupported family member: {person}")
        if not address:
            raise ValueError(f"empty address for {person}")
        mapping[person] = address
    missing = sorted(set(FAMILY) - set(mapping))
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


def _identity_db_path(env_path: Path, explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        return explicit_path
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("IDENTITY_DATABASE_PATH="):
            configured = line.split("=", 1)[1].strip()
            if configured:
                return Path(configured).expanduser()
    return DEFAULT_IDENTITY_DB


def _family_people(mapping: dict[str, str]) -> tuple[list[Person], list[Relationship]]:
    people = [
        Person(
            person_id="joe",
            display_name="Joe",
            preferred_name="Joe",
            aliases=(Alias("Joseph"), Alias("Dad"), Alias("Father")),
            identities=(
                Identity("phone", mapping["joe"], label="iMessage phone", verified=True),
                Identity("imessage", mapping["joe"], label="iMessage", verified=True),
                Identity("calendar", "joe", verified=True),
            ),
        ),
        Person(
            person_id="beth",
            display_name="Beth",
            preferred_name="Beth",
            aliases=(Alias("Mom"), Alias("Mother")),
            identities=(
                Identity("phone", mapping["beth"], label="iMessage phone", verified=True),
                Identity("imessage", mapping["beth"], label="iMessage", verified=True),
                Identity("calendar", "beth", verified=True),
            ),
        ),
        Person(
            person_id="liam",
            display_name="Liam",
            preferred_name="Liam",
            aliases=(Alias("Son"),),
            identities=(
                Identity("phone", mapping["liam"], label="iMessage phone", verified=True),
                Identity("imessage", mapping["liam"], label="iMessage", verified=True),
                Identity("calendar", "liam", verified=True),
            ),
        ),
        Person(
            person_id="jenna",
            display_name="Jenna",
            preferred_name="Jenna",
            aliases=(Alias("Daughter"),),
            identities=(
                Identity("phone", mapping["jenna"], label="iMessage phone", verified=True),
                Identity("imessage", mapping["jenna"], label="iMessage", verified=True),
                Identity("calendar", "jenna", verified=True),
            ),
        ),
    ]
    relationships = [
        Relationship("joe", "spouse", "beth"),
        Relationship("beth", "spouse", "joe"),
    ]
    for child in ("liam", "jenna"):
        relationships.extend(
            [
                Relationship("joe", "child", child),
                Relationship("beth", "child", child),
                Relationship(child, "parent", "joe"),
                Relationship(child, "parent", "beth"),
            ]
        )
    return people, relationships


def _persist_family_identity_db(path: Path, mapping: dict[str, str]) -> None:
    provider = SQLiteIdentityProvider(path)
    existing_people, existing_relationships = provider.load()
    family_people, family_relationships = _family_people(mapping)
    people_by_id = {person.person_id: person for person in existing_people if person.person_id not in FAMILY}
    for person in family_people:
        people_by_id[person.person_id] = person
    family_relationship_keys = {
        (item.source_person_id, item.relationship, item.target_person_id)
        for item in family_relationships
    }
    relationships = [
        item
        for item in existing_relationships
        if item.source_person_id not in FAMILY
        and item.target_person_id not in FAMILY
        and (item.source_person_id, item.relationship, item.target_person_id) not in family_relationship_keys
    ]
    relationships.extend(family_relationships)
    provider.replace_all(list(people_by_id.values()), relationships)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map family iMessage senders to personal agents.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--identity-db", type=Path, default=None)
    parser.add_argument("--restart", action="store_true", help="Restart the iMessage LaunchAgent after updating env.")
    parser.add_argument("mapping", nargs="+", help="Four mappings: joe=..., beth=..., liam=..., jenna=...")
    args = parser.parse_args(argv)

    try:
        mapping = _parse_mapping(args.mapping)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    identity_db = _identity_db_path(args.env_file, args.identity_db)
    _persist_family_identity_db(identity_db, mapping)

    ordered = ",".join(mapping[person] for person in FAMILY)
    _replace_env_line(args.env_file, "IMESSAGE_ALLOWED_SENDERS", ordered)
    _replace_env_line(args.env_file, "IDENTITY_PROVIDER", "sqlite")
    _replace_env_line(args.env_file, "IDENTITY_DATABASE_PATH", str(identity_db))
    _replace_env_line(args.env_file, "IDENTITY_SEED_FALLBACK", "true")

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
