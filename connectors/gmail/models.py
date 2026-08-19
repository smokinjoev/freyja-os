from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GmailAttachment(BaseModel):
    filename: str
    mime_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    attachment_id: str | None = None


class GmailMessage(BaseModel):
    message_id: str
    thread_id: str
    sender: str
    recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    text: str = ""
    html: str | None = None
    received_at: datetime
    attachments: list[GmailAttachment] = Field(default_factory=list)


class GmailReply(BaseModel):
    thread_id: str
    to: str
    subject: str
    text: str
    success: bool = True
