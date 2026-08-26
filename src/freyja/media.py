from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

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

    @property
    def is_pdf(self) -> bool:
        mime = (self.mime_type or "").lower()
        name = (self.filename or self.path or "").lower()
        return mime == "application/pdf" or name.endswith(".pdf")

    @property
    def is_docx(self) -> bool:
        mime = (self.mime_type or "").lower()
        name = (self.filename or self.path or "").lower()
        return (
            mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or name.endswith(".docx")
        )

    @property
    def is_document(self) -> bool:
        return self.is_pdf or self.is_docx

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


@dataclass(frozen=True)
class DocumentText:
    filename: str
    mime_type: str
    text: str = ""
    page_count: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text.strip()) and self.error is None


def images_from_attachments(attachments: list[AttachmentInput]) -> list[ImageInput]:
    images: list[ImageInput] = []
    for attachment in attachments:
        image = attachment.to_image_input()
        if image is not None:
            images.append(image)
    return images


def document_texts_from_attachments(
    attachments: list[AttachmentInput],
    *,
    max_chars_per_document: int = 8000,
    max_pages: int = 8,
) -> list[DocumentText]:
    documents: list[DocumentText] = []
    for attachment in attachments:
        if not attachment.is_document:
            continue
        name = attachment.filename or (Path(attachment.path).name if attachment.path else "document")
        mime_type = attachment.mime_type or (
            "application/pdf" if attachment.is_pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        if not (attachment.data_base64 or attachment.path):
            documents.append(DocumentText(filename=name, mime_type=mime_type, error="document payload unavailable"))
            continue
        try:
            payload = _attachment_bytes(attachment)
            if attachment.is_pdf:
                documents.append(
                    _extract_pdf_text(
                        payload,
                        filename=name,
                        mime_type=mime_type,
                        max_chars=max_chars_per_document,
                        max_pages=max_pages,
                    )
                )
            else:
                documents.append(
                    _extract_docx_text(
                        payload,
                        filename=name,
                        mime_type=mime_type,
                        max_chars=max_chars_per_document,
                    )
                )
        except Exception:
            documents.append(DocumentText(filename=name, mime_type=mime_type, error="document text extraction failed"))
    return documents


def pdf_texts_from_attachments(
    attachments: list[AttachmentInput],
    *,
    max_chars_per_document: int = 8000,
    max_pages: int = 8,
) -> list[DocumentText]:
    return document_texts_from_attachments(
        attachments,
        max_chars_per_document=max_chars_per_document,
        max_pages=max_pages,
    )


def _attachment_bytes(attachment: AttachmentInput) -> bytes:
    if attachment.data_base64:
        return base64.b64decode(attachment.data_base64)
    path = Path(str(attachment.path)).expanduser()
    return path.read_bytes()


def _extract_pdf_text(
    payload: bytes,
    *,
    filename: str,
    mime_type: str,
    max_chars: int,
    max_pages: int,
) -> DocumentText:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    parts: list[str] = []
    for index, page in enumerate(reader.pages[:max_pages], start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            parts.append(f"[page {index}]\n{page_text}")
        if sum(len(part) for part in parts) >= max_chars:
            break
    text = "\n\n".join(parts).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return DocumentText(
        filename=filename,
        mime_type=mime_type,
        text=text,
        page_count=len(reader.pages),
        error=None if text else "pdf contains no extractable text",
    )


def _extract_docx_text(
    payload: bytes,
    *,
    filename: str,
    mime_type: str,
    max_chars: int,
) -> DocumentText:
    with ZipFile(BytesIO(payload)) as archive:
        xml_payload = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_payload)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            paragraphs.append(text)
        if sum(len(part) for part in paragraphs) >= max_chars:
            break
    text = "\n".join(paragraphs).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return DocumentText(
        filename=filename,
        mime_type=mime_type,
        text=text,
        page_count=0,
        error=None if text else "docx contains no extractable text",
    )


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
