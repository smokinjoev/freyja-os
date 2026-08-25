from __future__ import annotations

import base64
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class ImageInput(BaseModel):
    mime_type: str = "image/jpeg"
    data_base64: str | None = None
    path: str | None = None
    filename: str | None = None

    @model_validator(mode="after")
    def _requires_content(self) -> "ImageInput":
        if not (self.data_base64 or self.path):
            raise ValueError("image requires data_base64 or path")
        return self

    @property
    def display_name(self) -> str:
        if self.filename:
            return self.filename
        if self.path:
            return Path(self.path).name
        return "image"

    def as_ollama_image(self) -> str:
        return self._data_base64()

    def as_data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self._data_base64()}"

    def _data_base64(self) -> str:
        if self.data_base64:
            return self.data_base64
        path = Path(str(self.path)).expanduser()
        return base64.b64encode(path.read_bytes()).decode("ascii")


class AttachmentInput(BaseModel):
    filename: str | None = None
    mime_type: str | None = None
    path: str | None = None
    data_base64: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)

    @property
    def is_image(self) -> bool:
        mime = (self.mime_type or "").lower()
        if mime.startswith("image/"):
            return True
        name = (self.filename or self.path or "").lower()
        return name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"))

    def to_image_input(self) -> ImageInput | None:
        if not self.is_image:
            return None
        if not (self.data_base64 or self.path):
            return None
        return ImageInput(
            mime_type=self.mime_type or _mime_from_name(self.filename or self.path or "") or "image/jpeg",
            data_base64=self.data_base64,
            path=self.path,
            filename=self.filename,
        )


def images_from_attachments(attachments: list[AttachmentInput]) -> list[ImageInput]:
    images: list[ImageInput] = []
    for attachment in attachments:
        image = attachment.to_image_input()
        if image is not None:
            images.append(image)
    return images


def _mime_from_name(name: str) -> str | None:
    lowered = name.lower()
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".gif"):
        return "image/gif"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".heic"):
        return "image/heic"
    return None
