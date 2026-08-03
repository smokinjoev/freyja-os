from __future__ import annotations

import hashlib
import re

from freyja.identity.models import Alias, Identity, Person
from freyja.identity.providers import validate_records


def parse_vcards(content: str) -> list[Person]:
    lines = _unfold(content)
    cards: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        upper = line.upper()
        if upper == "BEGIN:VCARD":
            if current is not None:
                raise ValueError("nested vCard is not allowed")
            current = []
        elif upper == "END:VCARD":
            if current is None:
                raise ValueError("vCard end without begin")
            cards.append(current)
            current = None
        elif current is not None:
            current.append(line)
    if current is not None:
        raise ValueError("unterminated vCard")
    if not cards:
        raise ValueError("no vCards found")
    people = [_parse_card(card) for card in cards]
    validate_records(people, [])
    return people


def _parse_card(lines: list[str]) -> Person:
    fields: dict[str, list[tuple[dict[str, str], str]]] = {}
    for line in lines:
        if ":" not in line:
            continue
        descriptor, raw_value = line.split(":", 1)
        parts = descriptor.split(";")
        name = parts[0].split(".")[-1].upper()
        parameters: dict[str, str] = {}
        for parameter in parts[1:]:
            if "=" in parameter:
                key, value = parameter.split("=", 1)
                parameters[key.upper()] = value.strip('"')
        fields.setdefault(name, []).append((parameters, _unescape(raw_value)))
    uid = _first(fields, "UID")
    display_name = _first(fields, "FN")
    if not uid or not display_name:
        raise ValueError("each vCard requires UID and FN")
    aliases: list[Alias] = []
    for _parameters, value in fields.get("NICKNAME", []):
        aliases.extend(Alias(item.strip()) for item in value.split(",") if item.strip())
    identities: list[Identity] = []
    for name, kind in (("TEL", "phone"), ("EMAIL", "email")):
        for parameters, value in fields.get(name, []):
            cleaned = value.removeprefix("tel:").removeprefix("mailto:").strip()
            if cleaned:
                identities.append(Identity(kind=kind, value=cleaned, label=_label(parameters)))
    uid_digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return Person(
        person_id=f"contact-{uid_digest[:20]}",
        display_name=display_name.strip(),
        preferred_name=aliases[0].value if aliases else None,
        aliases=tuple(aliases),
        identities=tuple(identities),
        metadata={"contact_source": "vcard", "provider_uid_sha256": uid_digest},
    )


def _unfold(content: str) -> list[str]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    unfolded: list[str] = []
    for line in normalized.split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _first(fields: dict[str, list[tuple[dict[str, str], str]]], name: str) -> str | None:
    values = fields.get(name, [])
    return values[0][1].strip() if values else None


def _label(parameters: dict[str, str]) -> str | None:
    raw = parameters.get("TYPE")
    return raw.split(",")[0].lower() if raw else None


def _unescape(value: str) -> str:
    return re.sub(r"\\([nN,;\\])", lambda match: "\n" if match.group(1).lower() == "n" else match.group(1), value)
