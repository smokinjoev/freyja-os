from __future__ import annotations

from email.message import EmailMessage
from email.utils import formatdate

import pytest

from connectors.gmail.config import GmailSettings
from connectors.gmail.models import GmailReply
from connectors.gmail.transport import GmailImapSmtpTransport


def _settings() -> GmailSettings:
    return GmailSettings(
        gmail_enabled=True,
        gmail_identity="freyja@example.com",
        gmail_allowed_senders="worker@example.com",
        gmail_imap_username="freyja@example.com",
        gmail_imap_password="app-password",
        gmail_smtp_username="freyja@example.com",
        gmail_smtp_password="app-password",
    )


def _raw_message(*, html_only: bool = False, attachment: bool = False) -> bytes:
    message = EmailMessage()
    message["From"] = "Worker <worker@example.com>"
    message["To"] = "Freyja <freyja@example.com>"
    message["Subject"] = "Status"
    message["Message-ID"] = "<message-1@example.com>"
    message["References"] = "<root@example.com>"
    message["Date"] = formatdate(localtime=False)
    if html_only:
        message.add_alternative(
            '<p>Hello <a href="https://example.com">there</a></p>',
            subtype="html",
        )
    else:
        message.set_content("Hello Freyja")
    if attachment:
        message.add_attachment(
            b"not trusted",
            maintype="application",
            subtype="pdf",
            filename="invoice.pdf",
        )
    return message.as_bytes()


class FakeImap:
    def __init__(self, _host: str, _port: int) -> None:
        self.stored: list[tuple[bytes, str, str]] = []
        self.closed = False
        self.logged_out = False

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        assert username == "freyja@example.com"
        assert password == "app-password"
        return "OK", []

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        assert mailbox == "INBOX"
        return "OK", []

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        if command == "search":
            return "OK", [b"101"]
        if command == "fetch":
            uid = args[0]
            assert uid == b"101"
            return "OK", [(b"101 (X-GM-THRID 777 RFC822 {123}", _raw_message())]
        if command == "store":
            uid, operation, flags = args
            self.stored.append((uid, operation, flags))
            return "OK", []
        raise AssertionError(f"unexpected IMAP command: {command}")

    def close(self) -> None:
        self.closed = True

    def logout(self) -> None:
        self.logged_out = True


class FakeSmtp:
    sent_messages: list[EmailMessage] = []

    def __init__(self, host: str, port: int) -> None:
        assert host == "smtp.gmail.com"
        assert port == 587
        self.started_tls = False
        self.logged_in = False

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        assert username == "freyja@example.com"
        assert password == "app-password"
        self.logged_in = True

    def send_message(self, message: EmailMessage) -> None:
        self.sent_messages.append(message)


class RecordingGateway:
    def __init__(self) -> None:
        self.messages = []

    async def handle(self, message):
        self.messages.append(message)
        return GmailReply(
            thread_id=message.thread_id,
            to=message.sender,
            subject=f"Re: {message.subject}",
            text="Director reply",
        )


@pytest.mark.asyncio
async def test_poll_once_fetches_unread_message_and_sends_threaded_reply():
    FakeSmtp.sent_messages = []
    gateway = RecordingGateway()
    fake_imap = FakeImap("imap.gmail.com", 993)

    transport = GmailImapSmtpTransport(
        gateway,
        _settings(),
        imap_factory=lambda host, port: fake_imap,
        smtp_factory=FakeSmtp,
    )

    replies = await transport.poll_once()

    assert len(replies) == 1
    assert len(gateway.messages) == 1
    inbound = gateway.messages[0]
    assert inbound.message_id == "<message-1@example.com>"
    assert inbound.thread_id == "gmail-thrid:777"
    assert inbound.sender == "worker@example.com"
    assert inbound.text == "Hello Freyja"
    assert fake_imap.stored == [(b"101", "+FLAGS", r"(\Seen)")]

    assert len(FakeSmtp.sent_messages) == 1
    outbound = FakeSmtp.sent_messages[0]
    assert outbound["To"] == "worker@example.com"
    assert outbound["Subject"] == "Re: Status"
    assert outbound["In-Reply-To"] == "<message-1@example.com>"
    assert outbound["References"] == "<root@example.com> <message-1@example.com>"
    assert "Director reply" in outbound.get_content()


def test_html_and_attachments_are_normalized_with_pdf_payload_for_extraction():
    parsed = GmailImapSmtpTransport._to_gateway_message(
        GmailImapSmtpTransport(
            RecordingGateway(),
            _settings(),
            imap_factory=FakeImap,
            smtp_factory=FakeSmtp,
        ),
        __import__("email").message_from_bytes(
            _raw_message(html_only=True, attachment=True)
        ),
        message_id="<message-1@example.com>",
        thread_id="gmail-thrid:777",
    )

    assert parsed.text == ""
    assert "https://example.com" in (parsed.html or "")
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].filename == "invoice.pdf"
    assert parsed.attachments[0].size_bytes == len(b"not trusted")
    assert parsed.attachments[0].data_base64 is not None
