from __future__ import annotations

from dataclasses import dataclass

from freyja.identity import IdentityService, Person, person_from_legacy_member, person_memory_subject
from freyja.memory.principal import stable_identity


@dataclass(frozen=True)
class AuthorizedSender:
    platform: str
    address: str
    member_id: str | None = None
    person: Person | None = None

    @property
    def subject(self) -> str:
        if self.person:
            return person_memory_subject(self.person)
        if self.member_id:
            return stable_identity("family-member", self.member_id)
        return stable_identity(self.platform, self.address)

    @property
    def conversation_id(self) -> str:
        return stable_identity(f"{self.platform}-conv", self.address)

    def conversation_id_for_thread(self, thread_id: str) -> str:
        return stable_identity(f"{self.platform}-thread", f"{self.address}:{thread_id}")

    def safe_headers(self) -> dict[str, str]:
        person = self.person or (person_from_legacy_member(self.member_id) if self.member_id else None)
        headers = {
            "X-Freyja-Client-Type": self.platform,
            "X-Freyja-Client-Subject": self.subject,
            "X-Freyja-Conversation-Id": self.conversation_id,
        }
        if self.member_id:
            headers["X-Freyja-Family-Member"] = self.member_id
        if person:
            headers["X-Freyja-Person-Id"] = person.person_id
            headers["X-Freyja-Person-Display-Name"] = person.display_name
            headers["X-Freyja-Person-Preferred-Name"] = person.preferred_name or person.display_name
        return headers


def parse_allowed_senders(
    raw: str,
    platform: str,
    identity_service: IdentityService | None = None,
) -> dict[str, AuthorizedSender]:
    identities: dict[str, AuthorizedSender] = {}
    for entry in raw.split(","):
        value = entry.strip()
        if not value:
            continue
        member_id: str | None = None
        address = value
        if "=" in value:
            left, right = value.split("=", 1)
            if left.strip() and right.strip():
                member_id = _safe_member_id(left.strip())
                address = right.strip()
        person = _resolve_person(
            address=address,
            platform=platform,
            member_id=member_id,
            identity_service=identity_service,
        )
        identities[address] = AuthorizedSender(
            platform=platform,
            address=address,
            member_id=person.person_id if person else member_id,
            person=person,
        )
    return identities


def _safe_member_id(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if not cleaned:
        raise ValueError("member id must contain at least one alphanumeric character")
    return cleaned[:64]


def _resolve_person(
    *,
    address: str,
    platform: str,
    member_id: str | None,
    identity_service: IdentityService | None,
) -> Person | None:
    if identity_service is not None:
        person = None
        if member_id:
            person = identity_service.resolve(member_id)
        if person is None and platform == "signal":
            person = identity_service.resolve_signal_sender(address)
        if person is None and platform == "imessage":
            person = identity_service.resolve_imessage_sender(address)
        if person is None:
            person = identity_service.resolve(address, kind=platform)
        if person is not None:
            return person
    if member_id:
        return person_from_legacy_member(member_id)
    return None
