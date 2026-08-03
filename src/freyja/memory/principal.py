import hashlib
import re
from typing import Mapping

from fastapi import Header, HTTPException

from freyja.memory.models import MemoryPrincipal

_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")
_CLIENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_CONVERSATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,159}$")


def stable_identity(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def validate_principal_value(
    value: str | None,
    *,
    field_name: str,
    pattern: re.Pattern[str],
    required: bool,
) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    if len(value) > 160:
        raise ValueError(f"{field_name} is too long")
    if not pattern.fullmatch(value):
        raise ValueError(f"{field_name} contains invalid characters")
    return value


def build_memory_principal(
    *,
    client_type: str,
    client_subject: str,
    account_owner: str | None = None,
    conversation_id: str | None = None,
) -> MemoryPrincipal:
    validated_type = validate_principal_value(
        client_type,
        field_name="client_type",
        pattern=_CLIENT_TYPE_PATTERN,
        required=True,
    )
    validated_subject = validate_principal_value(
        client_subject,
        field_name="client_subject",
        pattern=_IDENTITY_PATTERN,
        required=True,
    )
    validated_owner = validate_principal_value(
        account_owner,
        field_name="account_owner",
        pattern=_IDENTITY_PATTERN,
        required=False,
    )
    validated_conversation = validate_principal_value(
        conversation_id,
        field_name="conversation_id",
        pattern=_CONVERSATION_PATTERN,
        required=False,
    )
    return MemoryPrincipal(
        client_type=validated_type or "",
        client_subject=validated_subject or "",
        account_owner=validated_owner,
        conversation_id=validated_conversation,
    )


def principal_from_headers(headers: Mapping[str, str]) -> MemoryPrincipal | None:
    client_type = headers.get("x-freyja-client-type")
    client_subject = headers.get("x-freyja-client-subject")
    if not client_type and not client_subject:
        return None
    if not client_type or not client_subject:
        raise ValueError("complete memory principal headers are required")
    return build_memory_principal(
        client_type=client_type,
        client_subject=client_subject,
        account_owner=headers.get("x-freyja-account-owner") or None,
        conversation_id=headers.get("x-freyja-conversation-id") or None,
    )


async def require_memory_principal(
    x_freyja_client_type: str | None = Header(default=None),
    x_freyja_client_subject: str | None = Header(default=None),
    x_freyja_account_owner: str | None = Header(default=None),
    x_freyja_conversation_id: str | None = Header(default=None),
) -> MemoryPrincipal:
    try:
        principal = build_memory_principal(
            client_type=x_freyja_client_type or "",
            client_subject=x_freyja_client_subject or "",
            account_owner=x_freyja_account_owner,
            conversation_id=x_freyja_conversation_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Memory principal is required.",
        ) from None
    return principal
