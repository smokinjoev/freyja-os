from __future__ import annotations

import email
import imaplib
import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage, Message
from email.utils import (
    formataddr,
    formatdate,
    getaddresses,
    make_msgid,
    parseaddr,
    parsedate_to_datetime,
)
from typing import Callable, Protocol

from connectors.gmail.config import GmailSettings
from connectors.gmail.models import GmailAttachment, GmailMessage, GmailReply

logger = logging.getLogger(__name__)


class GmailMessageHandler(Protocol):
    async def handle(self, message: GmailMessage) -> GmailReply | None: ...


class GmailTransportError(RuntimeError):
    """A recoverable Gmail transport failure."""


_THRID_RE = re.compile(rb"X-GM-THRID\s+(\d+)")


@dataclass
class _InboundEnvelope:
    uid: bytes
    message: GmailMessage
    original_message_id: str
    references: str


class GmailImapSmtpTransport:
    """Poll unread Gmail messages over IMAP and send threaded replies over SMTP."""

    def __init__(
        self,
        gateway: GmailMessageHandler,
        settings: GmailSettings | None = None,
        imap_factory: Callable[[str, int], imaplib.IMAP4_SSL] | None = None,
        smtp_factory: Callable[[str, int], smtplib.SMTP] | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings or GmailSettings()
        self._imap_factory = imap_factory or imaplib.IMAP4_SSL
        self._smtp_factory = smtp_factory or smtplib.SMTP

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        client = self._imap_factory(
            self._settings.gmail_imap_host,
            self._settings.gmail_imap_port,
        )
        client.login(
            self._settings.gmail_imap_username,
            self._settings.gmail_imap_password,
        )
        status, _ = client.select(self._settings.gmail_imap_mailbox)
        if status != "OK":
            raise GmailTransportError("Gmail IMAP mailbox selection failed")
        return client

    async def poll_once(self) -> list[GmailReply]:
        """Fetch unread messages, pass them through the gateway, and send replies."""
        if not self._settings.transport_configured:
            raise GmailTransportError("Gmail IMAP/SMTP transport is not configured")

        imap_client: imaplib.IMAP4_SSL | None = None
        replies: list[GmailReply] = []
        try:
            imap_client = self._connect_imap()
            status, data = imap_client.uid("search", None, "UNSEEN")
            if status != "OK":
                raise GmailTransportError("Gmail IMAP search failed")

            uids = data[0].split() if data and data[0] else []
            for uid in uids:
                envelope = self._fetch_message(imap_client, uid)
                if envelope is None:
                    continue

                reply = await self._gateway.handle(envelope.message)
                if reply is not None:
                    self.send(reply, envelope)
                    replies.append(reply)

                imap_client.uid("store", uid, "+FLAGS", r"(\Seen)")

            return replies
        except GmailTransportError:
            raise
        except Exception as exc:
            logger.warning(
                {
                    "event": "gmail_transport_poll_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise GmailTransportError("Gmail polling failed") from exc
        finally:
            if imap_client is not None:
                try:
                    imap_client.close()
                except Exception:
                    pass
                try:
                    imap_client.logout()
                except Exception:
                    pass

    def _fetch_message(
        self,
        imap_client: imaplib.IMAP4_SSL,
        uid: bytes,
    ) -> _InboundEnvelope | None:
        status, data = imap_client.uid("fetch", uid, "(X-GM-THRID RFC822)")
        if status != "OK":
            logger.warning(
                {
                    "event": "gmail_transport_fetch_failed",
                    "uid": uid.decode(errors="ignore"),
                }
            )
            return None

        fetch_header = b""
        raw_message = b""
        for item in data or []:
            if isinstance(item, tuple):
                fetch_header += item[0] or b""
                raw_message += item[1] or b""

        if not raw_message:
            return None

        parsed = email.message_from_bytes(raw_message)
        thread_id = self._thread_id(fetch_header, parsed)
        original_message_id = self._message_id(parsed, uid)
        return _InboundEnvelope(
            uid=uid,
            message=self._to_gateway_message(
                parsed,
                message_id=original_message_id,
                thread_id=thread_id,
            ),
            original_message_id=original_message_id,
            references=str(parsed.get("References", "")).strip(),
        )

    def _to_gateway_message(
        self,
        parsed: Message,
        *,
        message_id: str,
        thread_id: str,
    ) -> GmailMessage:
        text, html, attachments = self._extract_body_and_attachments(parsed)
        sender = parseaddr(str(parsed.get("From", "")))[1].strip().lower()
        recipients = [
            addr.lower()
            for _name, addr in getaddresses(
                [
                    str(parsed.get("To", "")),
                    str(parsed.get("Cc", "")),
                ]
            )
            if addr
        ]

        return GmailMessage(
            message_id=message_id,
            thread_id=thread_id,
            sender=sender,
            recipients=recipients,
            subject=str(parsed.get("Subject", "")),
            text=text,
            html=html,
            received_at=self._received_at(parsed),
            attachments=attachments,
        )

    @staticmethod
    def _extract_body_and_attachments(
        parsed: Message,
    ) -> tuple[str, str | None, list[GmailAttachment]]:
        text_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[GmailAttachment] = []

        parts = parsed.walk() if parsed.is_multipart() else [parsed]
        for part in parts:
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            filename = part.get_filename()
            disposition = str(part.get("Content-Disposition", "")).lower()

            if filename or "attachment" in disposition:
                payload = part.get_payload(decode=True) or b""
                attachments.append(
                    GmailAttachment(
                        filename=filename or "unnamed",
                        mime_type=content_type,
                        size_bytes=len(payload),
                    )
                )
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                raw_payload = part.get_payload()
                payload = raw_payload.encode() if isinstance(raw_payload, str) else b""
            charset = part.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace").strip()
            if not body:
                continue
            if content_type == "text/plain":
                text_parts.append(body)
            elif content_type == "text/html":
                html_parts.append(body)

        text = "\n\n".join(text_parts).strip()
        html = "\n\n".join(html_parts).strip() or None
        return text, html, attachments

    @staticmethod
    def _thread_id(fetch_header: bytes, parsed: Message) -> str:
        match = _THRID_RE.search(fetch_header)
        if match:
            return f"gmail-thrid:{match.group(1).decode()}"
        references = str(parsed.get("References", "")).strip()
        if references:
            return f"gmail-ref:{references.split()[-1]}"
        return f"gmail-message:{GmailImapSmtpTransport._message_id(parsed, b'unknown')}"

    @staticmethod
    def _message_id(parsed: Message, uid: bytes) -> str:
        header = str(parsed.get("Message-ID", "")).strip()
        if header:
            return header
        return f"gmail-uid:{uid.decode(errors='ignore')}"

    @staticmethod
    def _received_at(parsed: Message) -> datetime:
        raw = str(parsed.get("Date", "")).strip()
        if raw:
            try:
                received = parsedate_to_datetime(raw)
                if received.tzinfo is None:
                    return received.replace(tzinfo=timezone.utc)
                return received.astimezone(timezone.utc)
            except (TypeError, ValueError):
                pass
        return datetime.now(timezone.utc)

    def send(self, reply: GmailReply, source: _InboundEnvelope) -> None:
        message = EmailMessage()
        from_addr = self._settings.gmail_smtp_username
        from_name = self._settings.gmail_smtp_from_name.strip()
        if from_name:
            message["From"] = formataddr((from_name, from_addr))
        else:
            message["From"] = from_addr
        message["To"] = reply.to
        message["Subject"] = reply.subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid(domain=from_addr.split("@")[-1])
        if source.original_message_id:
            message["In-Reply-To"] = source.original_message_id
            references = source.references.split()
            if source.original_message_id not in references:
                references.append(source.original_message_id)
            message["References"] = " ".join(references)
        message.set_content(reply.text)

        try:
            with self._smtp_factory(
                self._settings.gmail_smtp_host,
                self._settings.gmail_smtp_port,
            ) as smtp_client:
                if self._settings.gmail_smtp_starttls:
                    smtp_client.starttls()
                smtp_client.login(
                    self._settings.gmail_smtp_username,
                    self._settings.gmail_smtp_password,
                )
                smtp_client.send_message(message)
        except Exception as exc:
            logger.warning(
                {
                    "event": "gmail_transport_send_failed",
                    "recipient": reply.to,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise GmailTransportError("Gmail send failed") from exc
