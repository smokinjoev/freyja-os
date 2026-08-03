from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable, Mapping

from freyja.identity.models import Alias, Identity, IdentityKind, Person, Relationship
from freyja.identity.providers import IdentityProvider, SQLiteIdentityProvider
from freyja.memory.principal import stable_identity


_ALIAS_SEPARATOR = re.compile(r"[^a-z0-9]+")


class IdentityService:
    """Indexed resolver for people, aliases, relationships, and channel identities."""

    def __init__(
        self,
        *,
        people: Iterable[Person] | None = None,
        relationships: Iterable[Relationship] | None = None,
        provider: IdentityProvider | None = None,
    ) -> None:
        self._people: dict[str, Person] = {}
        self._identity_index: dict[tuple[str, str], str] = {}
        self._alias_index: dict[str, str] = {}
        self._relationships: list[Relationship] = []
        if provider is not None:
            if people is not None or relationships is not None:
                raise ValueError("provider cannot be combined with people or relationships")
            loaded_people, loaded_relationships = provider.load()
            people, relationships = loaded_people, loaded_relationships
        for person in people or ():
            self.add_person(person)
        for relationship in relationships or ():
            self.add_relationship(relationship)

    @property
    def people(self) -> dict[str, Person]:
        return dict(self._people)

    @property
    def relationships(self) -> tuple[Relationship, ...]:
        return tuple(self._relationships)

    def add_person(self, person: Person) -> Person:
        if not person.person_id:
            raise ValueError("person_id is required")
        if person.person_id in self._people:
            raise ValueError(f"duplicate person_id: {person.person_id}")
        self._people[person.person_id] = person
        for alias in self._person_aliases(person):
            self._alias_index[_normalize_alias(alias.value)] = person.person_id
        for identity in person.identities:
            self._identity_index[self._identity_key(identity.kind, identity.value)] = person.person_id
        return person

    def add_relationship(self, relationship: Relationship) -> None:
        if relationship.source_person_id not in self._people:
            raise ValueError(f"unknown source person: {relationship.source_person_id}")
        if relationship.target_person_id not in self._people:
            raise ValueError(f"unknown target person: {relationship.target_person_id}")
        self._relationships.append(relationship)

    def get_person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    def require_person(self, person_id: str) -> Person:
        person = self.get_person(person_id)
        if person is None:
            raise KeyError(person_id)
        return person

    def resolve(self, identifier: str, *, kind: IdentityKind | str | None = None) -> Person | None:
        if not identifier:
            return None
        if kind:
            return self.resolve_identity(str(kind), identifier)
        if identifier in self._people:
            return self._people[identifier]
        alias_match = self.resolve_alias(identifier)
        if alias_match:
            return alias_match
        for guessed_kind in ("email", "phone", "signal", "imessage", "calendar"):
            match = self.resolve_identity(guessed_kind, identifier)
            if match:
                return match
        return None

    def resolve_alias(self, alias: str) -> Person | None:
        return self._people.get(self._alias_index.get(_normalize_alias(alias), ""))

    def resolve_identity(self, kind: str, value: str) -> Person | None:
        return self._people.get(self._identity_index.get(self._identity_key(kind, value), ""))

    def resolve_signal_sender(self, sender: str) -> Person | None:
        return self.resolve_identity("signal", sender) or self.resolve_identity("phone", sender)

    def resolve_imessage_sender(self, sender: str) -> Person | None:
        return (
            self.resolve_identity("imessage", sender)
            or self.resolve_identity("phone", sender)
            or self.resolve_identity("email", sender)
        )

    def resolve_calendar_owner(self, owner: str) -> Person | None:
        return self.resolve_identity("calendar", owner) or self.resolve(owner)

    def relationships_for(self, person_id: str, relationship: str | None = None) -> tuple[Relationship, ...]:
        normalized = _normalize_relationship(relationship) if relationship else None
        return tuple(
            item
            for item in self._relationships
            if item.source_person_id == person_id
            and (normalized is None or _normalize_relationship(item.relationship) == normalized)
        )

    def related_people(self, person_id: str, relationship: str | None = None) -> tuple[Person, ...]:
        return tuple(
            person
            for item in self.relationships_for(person_id, relationship)
            if (person := self.get_person(item.target_person_id)) is not None
        )

    def person_context(self, person: Person) -> dict[str, str]:
        return {
            "person_id": person.person_id,
            "display_name": person.display_name,
            "preferred_name": person.preferred_name or person.display_name,
            "memory_subject": person_memory_subject(person),
        }

    def create_transient_person(self, person_id: str, *, display_name: str | None = None) -> Person:
        aliases = (Alias(person_id),)
        person = Person(person_id=person_id, display_name=display_name or person_id, preferred_name=display_name, aliases=aliases)
        return person

    def with_channel_identity(self, person: Person, *, kind: IdentityKind, value: str) -> Person:
        if any(identity.kind == kind and identity.value == value for identity in person.identities):
            return person
        updated = replace(person, identities=person.identities + (Identity(kind=kind, value=value),))
        self._people[person.person_id] = updated
        self._identity_index[self._identity_key(kind, value)] = updated.person_id
        return updated

    def _identity_key(self, kind: str, value: str) -> tuple[str, str]:
        if kind in {"email", "imessage"} and "@" in value:
            normalized = value.strip().lower()
        elif kind in {"phone", "signal", "imessage"}:
            normalized = _normalize_phone(value)
        elif kind == "alias":
            normalized = _normalize_alias(value)
        else:
            normalized = value.strip().lower()
        return kind, normalized

    def _person_aliases(self, person: Person) -> tuple[Alias, ...]:
        values = [Alias(person.person_id), Alias(person.display_name)]
        if person.preferred_name:
            values.append(Alias(person.preferred_name))
        values.extend(person.aliases)
        return tuple(values)


def person_memory_subject(person: Person) -> str:
    return stable_identity("family-member", person.person_id)


def person_context_from_headers(headers: Mapping[str, str]) -> dict[str, str] | None:
    person_id = headers.get("x-freyja-person-id")
    if not person_id:
        return None
    normalized_id = _normalize_alias(person_id)
    if not normalized_id:
        return None
    display_name = _safe_header_text(headers.get("x-freyja-person-display-name")) or normalized_id
    preferred_name = _safe_header_text(headers.get("x-freyja-person-preferred-name")) or display_name
    return {
        "person_id": normalized_id,
        "display_name": display_name,
        "preferred_name": preferred_name,
        "memory_subject": stable_identity("family-member", normalized_id),
    }


def person_from_legacy_member(member_id: str) -> Person:
    return Person(person_id=member_id, display_name=member_id, preferred_name=member_id, aliases=(Alias(member_id),))


def default_identity_service() -> IdentityService:
    from freyja.config import settings

    if settings.identity_provider == "sqlite":
        provider = SQLiteIdentityProvider(settings.identity_database_path)
        people, relationships = provider.load()
        if people or not settings.identity_seed_fallback:
            return IdentityService(people=people, relationships=relationships)
    elif settings.identity_provider != "seeded":
        raise ValueError(f"unsupported identity provider: {settings.identity_provider}")
    return seeded_identity_service()


def seeded_identity_service() -> IdentityService:
    joe = Person(
        person_id="joe",
        display_name="Joe",
        preferred_name="Joe",
        aliases=(Alias("Joseph"), Alias("Dad"), Alias("Father")),
        identities=(Identity(kind="calendar", value="joe"),),
    )
    beth = Person(
        person_id="beth",
        display_name="Beth",
        preferred_name="Beth",
        aliases=(Alias("Mom"), Alias("Mother")),
        identities=(Identity(kind="calendar", value="beth"),),
    )
    service = IdentityService(people=(joe, beth))
    service.add_relationship(Relationship("joe", "spouse", "beth"))
    service.add_relationship(Relationship("beth", "spouse", "joe"))
    return service


def _normalize_alias(value: str) -> str:
    return "-".join(part for part in _ALIAS_SEPARATOR.split(value.strip().lower()) if part)


def _normalize_phone(value: str) -> str:
    stripped = value.strip()
    prefix = "+" if stripped.startswith("+") else ""
    digits = "".join(char for char in stripped if char.isdigit())
    return f"{prefix}{digits}" if digits else stripped.lower()


def _normalize_relationship(value: str) -> str:
    return _normalize_alias(value).replace("-", "_")


def _safe_header_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned[:120] if cleaned else None
