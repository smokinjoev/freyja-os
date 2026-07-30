from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IMessage(BaseModel):
    sender: str
    text: str
    message_id: str
    chat_id: int
    chat_identifier: str
    timestamp: datetime
    is_group: bool = False
    is_from_me: bool = False


class IMessageReply(BaseModel):
    chat_id: int
    text: str
