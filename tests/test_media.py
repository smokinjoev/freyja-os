from __future__ import annotations

import base64
from io import BytesIO
from zipfile import ZipFile

from freyja.media import AttachmentInput, ImageInput, pdf_texts_from_attachments


SIMPLE_PDF_BASE64 = (
    "JVBERi0xLjQKMSAwIG9iaiA8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4gZW5kb2JqCjIg"
    "MCBvYmogPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4gZW5kb2JqCjMgMCBv"
    "YmogPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAzMDAgMTQ0XSAvUmVz"
    "b3VyY2VzIDw8IC9Gb250IDw8IC9GMSA0IDAgUiA+PiA+PiAvQ29udGVudHMgNSAwIFIgPj4gZW5kb2Jq"
    "CjQgMCBvYmogPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNh"
    "ID4+IGVuZG9iago1IDAgb2JqIDw8IC9MZW5ndGggNTEgPj4gc3RyZWFtCkJUIC9GMSAxMiBUZiA3MiAx"
    "MDAgVGQgKEZhbWlseSBkaW5uZXIgRnJpZGF5KSBUaiBFVAplbmRzdHJlYW0gZW5kb2JqCnhyZWYKMCA2"
    "CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDU4IDAwMDAwIG4g"
    "CjAwMDAwMDAxMTUgMDAwMDAgbiAKMDAwMDAwMDI0MSAwMDAwMCBuIAowMDAwMDAwMzExIDAwMDAwIG4g"
    "CnRyYWlsZXIgPDwgL1Jvb3QgMSAwIFIgL1NpemUgNiA+PgpzdGFydHhyZWYKNDEyCiUlRU9GCg=="
)


def simple_docx_base64(text: str = "Family plan Sunday") -> str:
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{escaped}</w:t></w:r></w:p></w:body>
</w:document>""",
        )
    return base64.b64encode(payload.getvalue()).decode("ascii")


def test_pdf_texts_extracts_native_pdf_text() -> None:
    documents = pdf_texts_from_attachments(
        [
            AttachmentInput(
                filename="plan.pdf",
                mime_type="application/pdf",
                data_base64=SIMPLE_PDF_BASE64,
            )
        ]
    )

    assert len(documents) == 1
    assert documents[0].ok is True
    assert documents[0].page_count == 1
    assert "Family dinner Friday" in documents[0].text


def test_pdf_texts_reports_missing_payload() -> None:
    documents = pdf_texts_from_attachments(
        [AttachmentInput(filename="plan.pdf", mime_type="application/pdf")]
    )

    assert documents[0].ok is False
    assert documents[0].error == "document payload unavailable"


def test_docx_texts_extracts_native_word_text() -> None:
    documents = pdf_texts_from_attachments(
        [
            AttachmentInput(
                filename="plan.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                data_base64=simple_docx_base64(),
            )
        ]
    )

    assert len(documents) == 1
    assert documents[0].ok is True
    assert "Family plan Sunday" in documents[0].text


def test_heic_image_input_converts_to_jpeg_for_providers(monkeypatch) -> None:
    monkeypatch.setattr("freyja.media._convert_heic_bytes_to_jpeg", lambda payload: b"jpeg-bytes")
    image = ImageInput(
        filename="photo.heic",
        mime_type="image/heic",
        data_base64=base64.b64encode(b"heic-bytes").decode("ascii"),
    )

    assert image.provider_mime_type() == "image/jpeg"
    assert image.as_data_url() == "data:image/jpeg;base64,anBlZy1ieXRlcw=="
    assert image.as_ollama_image() == "anBlZy1ieXRlcw=="
