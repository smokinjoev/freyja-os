from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from freyja.identity.models import Alias, Identity, Person
from freyja.identity.providers import validate_records


HELPER_PATH = Path(__file__).with_name("apple_contacts_export.swift")


def load_apple_contacts(*, helper_path: Path = HELPER_PATH, timeout_seconds: int = 120) -> list[Person]:
    if not helper_path.is_file():
        raise RuntimeError("Apple Contacts helper is missing")
    try:
        result = subprocess.run(
            ["/usr/bin/swift", str(helper_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Apple Contacts helper could not be run") from exc
    if result.returncode != 0:
        raise RuntimeError("Apple Contacts access failed; review macOS Contacts permission for the invoking app")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Apple Contacts helper returned invalid data") from exc
    return people_from_apple_payload(payload)


def people_from_apple_payload(payload: Any) -> list[Person]:
    if not isinstance(payload, dict) or not isinstance(payload.get("contacts"), list):
        raise ValueError("Apple Contacts payload must contain a contacts array")
    people: list[Person] = []
    for record in payload["contacts"]:
        if not isinstance(record, dict):
            raise ValueError("Apple contact must be an object")
        identifier = str(record.get("identifier", "")).strip()
        display_name = str(record.get("display_name", "")).strip()
        if not identifier or not display_name:
            raise ValueError("Apple contact requires identifier and display_name")
        uid_digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        nickname = str(record.get("nickname", "")).strip()
        aliases = (Alias(nickname),) if nickname and nickname.casefold() != display_name.casefold() else ()
        identities: list[Identity] = []
        for kind, field in (("phone", "phones"), ("email", "emails")):
            values = record.get(field, [])
            if not isinstance(values, list):
                raise ValueError(f"Apple contact {field} must be an array")
            for item in values:
                if not isinstance(item, dict) or not str(item.get("value", "")).strip():
                    raise ValueError(f"Apple contact {field} entry requires value")
                identities.append(
                    Identity(kind=kind, value=str(item["value"]).strip(), label=str(item.get("label", "")).strip() or None)
                )
        people.append(
            Person(
                person_id=f"apple-{uid_digest[:20]}",
                display_name=display_name,
                preferred_name=nickname or None,
                aliases=aliases,
                identities=tuple(identities),
                metadata={"contact_source": "apple_contacts", "provider_uid_sha256": uid_digest},
            )
        )
    validate_records(people, [])
    return people
