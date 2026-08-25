from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IMessageAttachment(BaseModel):
    filename: str | None = None
    mime_type: str | None = None
    path: str | None = None


class IMessage(BaseModel):
    sender: str
    text: str
    message_id: str
    chat_id: int
    chat_identifier: str
    timestamp: datetime
    is_group: bool = False
    is_from_me: bool = False
    attachments: list[IMessageAttachment] = Field(default_factory=list)


class IMessageReply(BaseModel):
    chat_id: int
    text: str
