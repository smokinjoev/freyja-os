from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


IdentityKind = Literal[
    "alias",
    "phone",
    "email",
    "signal",
    "imessage",
    "calendar",
    "voice",
    "avatar",
    "account",
]


@dataclass(frozen=True)
class Alias:
    value: str
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True)
class Identity:
    kind: IdentityKind
    value: str
    label: str | None = None
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "label": self.label,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class Relationship:
    source_person_id: str
    relationship: str
    target_person_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_person_id": self.source_person_id,
            "relationship": self.relationship,
            "target_person_id": self.target_person_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Person:
    person_id: str
    display_name: str
    preferred_name: str | None = None
    aliases: tuple[Alias, ...] = ()
    identities: tuple[Identity, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.preferred_name or self.display_name

    def to_dict(self, *, include_identifiers: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "person_id": self.person_id,
            "display_name": self.display_name,
            "preferred_name": self.preferred_name,
            "aliases": [alias.to_dict() for alias in self.aliases],
            "metadata": dict(self.metadata),
        }
        if include_identifiers:
            data["identities"] = [identity.to_dict() for identity in self.identities]
        else:
            data["identity_kinds"] = sorted({identity.kind for identity in self.identities})
        return data
