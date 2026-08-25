from __future__ import annotations

from freyja.media import AttachmentInput, pdf_texts_from_attachments


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
