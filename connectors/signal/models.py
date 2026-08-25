from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SignalAttachment(BaseModel):
    filename: str | None = None
    mime_type: str | None = None
    path: str | None = None
    data_base64: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class InboundMessage(BaseModel):
    sender: str
    text: str = ""
    message_id: str
    timestamp: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc))
    group_id: str | None = None
    attachments: list[SignalAttachment] = Field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())

    @property
    def is_attachment_only(self) -> bool:
        return not self.has_text and bool(self.attachments)


class OutboundResponse(BaseModel):
    recipient: str
    text: str
    reply_to_message_id: str | None = None
    success: bool = True

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(**kwargs)
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return data
