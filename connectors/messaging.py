from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx

from freyja.agents.household import HouseholdAgent, household_agents
from freyja.contracts import CanonicalAttachment, CanonicalRequest, CanonicalSender
from freyja.identity import IdentityService, Person, person_from_legacy_member, person_memory_subject
from freyja.media import AttachmentInput, DocumentText, ImageInput, images_from_attachments, pdf_texts_from_attachments
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


@dataclass(frozen=True)
class NormalizedAttachment:
    filename: str | None = None
    mime_type: str | None = None
    path: str | None = None
    data_base64: str | None = None
    size_bytes: int | None = None
    local_ref: str | None = None

    @property
    def has_payload(self) -> bool:
        return bool(self.data_base64 or self.path)

    @property
    def is_image(self) -> bool:
        mime = (self.mime_type or "").lower()
        name = (self.filename or self.path or self.local_ref or "").lower()
        return mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"))

    @property
    def is_pdf(self) -> bool:
        mime = (self.mime_type or "").lower()
        name = (self.filename or self.path or self.local_ref or "").lower()
        return mime == "application/pdf" or name.endswith(".pdf")

    @property
    def is_docx(self) -> bool:
        mime = (self.mime_type or "").lower()
        name = (self.filename or self.path or self.local_ref or "").lower()
        return (
            mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or name.endswith(".docx")
        )

    @property
    def is_document(self) -> bool:
        return self.is_pdf or self.is_docx

    @property
    def display_name(self) -> str:
        return self.filename or self.local_ref or self.path or "unnamed"

    def metadata_line(self, index: int) -> str:
        parts = [f"{self.mime_type or 'attachment'}: {self.display_name}"]
        if self.size_bytes is not None:
            parts.append(f"{self.size_bytes} bytes")
        if self.is_image and not self.has_payload:
            parts.append("image payload unavailable")
        if self.is_pdf and not self.has_payload:
            parts.append("document payload unavailable")
        if self.is_docx and not self.has_payload:
            parts.append("document payload unavailable")
        return f"{index}. " + ", ".join(parts)

    def to_attachment_input(self) -> AttachmentInput:
        return AttachmentInput(
            filename=self.filename,
            mime_type=self.mime_type,
            path=self.path,
            data_base64=self.data_base64,
            size_bytes=self.size_bytes,
        )

    def to_canonical_attachment(self) -> CanonicalAttachment:
        return CanonicalAttachment(
            media_type=self.mime_type,
            filename=self.filename,
            size=self.size_bytes,
            source=self.path or self.local_ref,
            reference=self.local_ref,
            data_base64=self.data_base64,
            metadata={
                key: value
                for key, value in {
                    "has_payload": self.has_payload,
                    "path": self.path,
                    "local_ref": self.local_ref,
                }.items()
                if value is not None
            },
        )


@dataclass(frozen=True)
class NormalizedMessage:
    transport: str
    sender: str
    conversation_id: str
    message_id: str
    text: str = ""
    timestamp: datetime | None = None
    thread_id: str | None = None
    group_id: str | None = None
    reply_to_message_id: str | None = None
    attachments: list[NormalizedAttachment] = field(default_factory=list)
    authorized: bool = False
    is_from_self: bool = False

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    @property
    def images(self) -> list[ImageInput]:
        return images_from_attachments([attachment.to_attachment_input() for attachment in self.attachments])

    @property
    def document_texts(self) -> list[DocumentText]:
        return pdf_texts_from_attachments([attachment.to_attachment_input() for attachment in self.attachments])

    @property
    def missing_payload_attachments(self) -> list[NormalizedAttachment]:
        return [
            attachment
            for attachment in self.attachments
            if (attachment.is_image or attachment.is_document) and not attachment.has_payload
        ]

    def prompt_text(self, *, empty_caption: str, metadata_label: str) -> str:
        if not self.attachments:
            return self.text

        attachment_summary = "\n".join(
            attachment.metadata_line(index)
            for index, attachment in enumerate(self.attachments, start=1)
        )
        honesty_note = ""
        if self.missing_payload_attachments:
            honesty_note = (
                "\nPayload honesty constraint: one or more image/document payloads are unavailable. "
                "Do not describe their contents unless bytes were actually provided to the vision/document path."
            )
        document_note = self.document_text_prompt()
        if self.has_text:
            return f"{self.text}\n\n{metadata_label}:\n{attachment_summary}{honesty_note}{document_note}"
        return f"{empty_caption}\n\n{metadata_label}:\n{attachment_summary}{honesty_note}{document_note}"

    def document_text_prompt(self) -> str:
        documents = self.document_texts
        if not documents:
            return ""
        lines = ["\n\nExtracted PDF/document text:"]
        for document in documents:
            if document.ok:
                lines.append(
                    f"{document.filename} ({document.page_count} page(s), native text extraction):\n{document.text}"
                )
            else:
                lines.append(f"{document.filename}: {document.error or 'document text unavailable'}")
        return "\n".join(lines)

    def to_canonical_request(
        self,
        *,
        authorized_sender: AuthorizedSender | None = None,
        resolved_user_id: str | None = None,
        resolved_agent_id: str | None = None,
        permissions: list[str] | None = None,
        channel_metadata: dict[str, object] | None = None,
    ) -> CanonicalRequest:
        user_id = resolved_user_id
        if user_id is None and authorized_sender is not None:
            user_id = authorized_sender.person.person_id if authorized_sender.person else authorized_sender.member_id
        metadata = {
            "thread_id": self.thread_id,
            "group_id": self.group_id,
            "authorized": self.authorized,
            "is_from_self": self.is_from_self,
            **(channel_metadata or {}),
        }
        return CanonicalRequest(
            message_id=self.message_id,
            timestamp=self.timestamp or datetime.now().astimezone(),
            channel=self.transport,
            conversation_id=self.conversation_id,
            sender=CanonicalSender(channel_id=self.sender, address=self.sender),
            resolved_user_id=user_id,
            resolved_agent_id=resolved_agent_id,
            text=self.text,
            attachments=[attachment.to_canonical_attachment() for attachment in self.attachments],
            reply_context={"reply_to_message_id": self.reply_to_message_id} if self.reply_to_message_id else {},
            channel_metadata={key: value for key, value in metadata.items() if value is not None},
            permissions=permissions or [],
        )


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


def person_id_for_sender(identity: AuthorizedSender) -> str:
    if identity.person:
        return identity.person.person_id.lower().strip()
    if identity.member_id:
        return identity.member_id.lower().strip()
    return "family"


def canonical_director_payload(
    request: CanonicalRequest,
    *,
    conversation_id: str | None = None,
    text: str | None = None,
) -> dict[str, object]:
    payload = request.model_dump(mode="json")
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    if text is not None:
        payload["text"] = text
    return payload


def director_headers(
    *,
    identity: AuthorizedSender,
    client_type: str,
    client_subject: str,
    conversation_id: str,
    trace_id: str,
    connector_token: str = "",
    account_owner: str | None = None,
    agent_id: str | None = None,
    agent_display_name: str | None = None,
    person_id: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = identity.safe_headers()
    headers["X-Freyja-Client-Type"] = client_type
    headers["X-Freyja-Client-Subject"] = client_subject
    headers["X-Freyja-Conversation-Id"] = conversation_id
    headers["X-Freyja-Trace-Id"] = trace_id
    if account_owner:
        headers["X-Freyja-Account-Owner"] = account_owner
    if agent_id:
        headers["X-Freyja-Agent-Id"] = agent_id
    if agent_display_name:
        headers["X-Freyja-Agent-Display-Name"] = agent_display_name
    if person_id:
        headers["X-Freyja-Person-Id"] = person_id
    if extra:
        headers.update(extra)
    if connector_token:
        headers["Authorization"] = f"Bearer {connector_token}"
    return headers


async def post_canonical_to_director(
    *,
    client: httpx.AsyncClient,
    director_url: str,
    payload: dict[str, object],
    headers: dict[str, str],
) -> dict[str, object]:
    response = await client.post(
        f"{director_url.rstrip('/')}/canonical/route",
        json=payload,
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def director_response_text(data: dict[str, object]) -> str:
    value = data.get("text") or data.get("response") or ""
    return value if isinstance(value, str) else ""


def director_response_provider(data: dict[str, object]) -> object:
    metadata = data.get("channel_metadata")
    if isinstance(metadata, dict) and metadata.get("provider") is not None:
        return metadata.get("provider")
    return data.get("provider")


def director_response_model(data: dict[str, object]) -> object:
    metadata = data.get("channel_metadata")
    if isinstance(metadata, dict) and metadata.get("model") is not None:
        return metadata.get("model")
    if isinstance(metadata, dict) and metadata.get("inference_model") is not None:
        return metadata.get("inference_model")
    return data.get("model")


def director_response_request_id(data: dict[str, object]) -> object:
    return data.get("trace_id") or data.get("request_id")


def director_response_inference_status(data: dict[str, object]) -> object:
    metadata = data.get("channel_metadata")
    if isinstance(metadata, dict):
        return metadata.get("inference_status")
    return None


def director_response_inference_endpoint(data: dict[str, object]) -> object:
    metadata = data.get("channel_metadata")
    if isinstance(metadata, dict):
        return metadata.get("inference_endpoint_id")
    return None


def director_response_tool_count(data: dict[str, object]) -> int:
    tool_results = data.get("tool_results")
    return len(tool_results) if isinstance(tool_results, list) else 0


def director_response_step_count(data: dict[str, object]) -> int:
    metadata = data.get("channel_metadata")
    steps = metadata.get("agent_steps") if isinstance(metadata, dict) else None
    return len(steps) if isinstance(steps, list) else 0


def household_agent_for_sender(identity: AuthorizedSender) -> HouseholdAgent:
    return household_agents.resolve(person_id_for_sender(identity))


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
