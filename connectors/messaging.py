from __future__ import annotations

from dataclasses import dataclass

from freyja.memory.principal import stable_identity


@dataclass(frozen=True)
class AuthorizedSender:
    platform: str
    address: str
    member_id: str | None = None

    @property
    def subject(self) -> str:
        if self.member_id:
            return stable_identity("family-member", self.member_id)
        return stable_identity(self.platform, self.address)

    @property
    def conversation_id(self) -> str:
        return stable_identity(f"{self.platform}-conv", self.address)

    def safe_headers(self) -> dict[str, str]:
        headers = {
            "X-Freyja-Client-Type": self.platform,
            "X-Freyja-Client-Subject": self.subject,
            "X-Freyja-Conversation-Id": self.conversation_id,
        }
        if self.member_id:
            headers["X-Freyja-Family-Member"] = self.member_id
        return headers


def parse_allowed_senders(raw: str, platform: str) -> dict[str, AuthorizedSender]:
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
        identities[address] = AuthorizedSender(platform=platform, address=address, member_id=member_id)
    return identities


def _safe_member_id(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if not cleaned:
        raise ValueError("member id must contain at least one alphanumeric character")
    return cleaned[:64]
