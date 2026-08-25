"""Models for Telegram inbound updates and outbound messages."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class TelegramUser(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str = ""
    username: str | None = None
    language_code: str | None = None


class TelegramChat(BaseModel):
    id: int
    type: str


class TelegramPhotoSize(BaseModel):
    file_id: str
    file_unique_id: str | None = None
    width: int
    height: int
    file_size: int | None = None


class TelegramDocument(BaseModel):
    file_id: str
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class TelegramMessage(BaseModel):
    message_id: int
    from_user: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat
    date: int
    text: str = ""
    caption: str = ""
    photo: list[TelegramPhotoSize] = Field(default_factory=list)
    document: TelegramDocument | None = None

    model_config = {"populate_by_name": True}


class TelegramInboundUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None
    channel_post: TelegramMessage | None = None
    edited_channel_post: TelegramMessage | None = None

    @model_validator(mode="after")
    def _normalize_message(self) -> "TelegramInboundUpdate":
        if self.message is None:
            if self.edited_message is not None:
                self.message = self.edited_message
            elif self.channel_post is not None:
                self.message = self.channel_post
            elif self.edited_channel_post is not None:
                self.message = self.edited_channel_post
        return self

    @property
    def effective_message(self) -> TelegramMessage | None:
        return self.message

    @property
    def sender_user_id(self) -> int | None:
        if self.message and self.message.from_user:
            return self.message.from_user.id
        return None

    @property
    def chat_id(self) -> int | None:
        if self.message:
            return self.message.chat.id
        return None

    @property
    def chat_type(self) -> str | None:
        if self.message:
            return self.message.chat.type
        return None

    @property
    def text(self) -> str:
        if self.message:
            return self.message.text or self.message.caption or ""
        return ""

    @property
    def has_image(self) -> bool:
        if not self.message:
            return False
        if self.message.photo:
            return True
        document = self.message.document
        return bool(document and (document.mime_type or "").lower().startswith("image/"))

    @property
    def is_direct_message(self) -> bool:
        return self.chat_type == "private"

    @property
    def is_group(self) -> bool:
        return self.chat_type in {"group", "supergroup"}

    @property
    def is_channel(self) -> bool:
        return self.chat_type == "channel"


class TelegramOutboundMessage(BaseModel):
    chat_id: int
    text: str
    reply_to_message_id: int | None = None
    success: bool = True

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(**kwargs)
        data.pop("success", None)
        return data
