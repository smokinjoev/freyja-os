from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from freyja.channels import ChannelMessage, ChannelPolicyError


class ChannelTransportError(RuntimeError):
    pass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class TelegramPilotConfig:
    bot_token: str = ""
    timeout_seconds: int = 25
    api_base: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls) -> "TelegramPilotConfig":
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            timeout_seconds=_env_int("TELEGRAM_LONG_POLL_TIMEOUT_SECONDS", 25),
            api_base=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.bot_token.strip())


@dataclass(frozen=True)
class TelegramInbound:
    update_id: int
    message: ChannelMessage


@dataclass(frozen=True)
class SignalCliRestConfig:
    account_number: str = ""
    rest_api_url: str = ""

    @classmethod
    def from_env(cls) -> "SignalCliRestConfig":
        return cls(
            account_number=os.environ.get("SIGNAL_ACCOUNT_NUMBER", ""),
            rest_api_url=os.environ.get("SIGNAL_REST_API_URL", ""),
        )

    @property
    def configured(self) -> bool:
        return bool(self.account_number.strip()) and bool(self.rest_api_url.strip())


def parse_telegram_update(update: dict[str, Any]) -> ChannelMessage | None:
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    sender_id = sender.get("id")
    chat_id = chat.get("id")
    if sender_id is None or chat_id is None:
        raise ChannelPolicyError("Telegram update lacks sender or chat id")
    text = str(message.get("text") or message.get("caption") or "").strip()
    attachments: list[dict[str, Any]] = []
    for photo in message.get("photo") or []:
        if isinstance(photo, dict):
            attachments.append(
                {
                    "kind": "image",
                    "source": "telegram",
                    "file_id": photo.get("file_id"),
                    "file_unique_id": photo.get("file_unique_id"),
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                }
            )
    document = message.get("document")
    if isinstance(document, dict):
        attachments.append(
            {
                "kind": "document",
                "source": "telegram",
                "file_id": document.get("file_id"),
                "file_unique_id": document.get("file_unique_id"),
                "filename": document.get("file_name"),
                "mime_type": document.get("mime_type"),
            }
        )
    return ChannelMessage(
        channel="telegram",
        sender=str(sender_id),
        chat_id=str(chat_id),
        text=text,
        attachments=tuple(attachments),
    )


def parse_signal_event(event: dict[str, Any]) -> ChannelMessage | None:
    envelope = event.get("envelope")
    if not isinstance(envelope, dict):
        return None
    data = envelope.get("dataMessage")
    if not isinstance(data, dict):
        return None
    sender = envelope.get("sourceNumber") or envelope.get("source")
    if not sender:
        raise ChannelPolicyError("Signal event lacks sender")
    attachments = []
    for attachment in data.get("attachments") or []:
        if isinstance(attachment, dict):
            attachments.append(
                {
                    "kind": "attachment",
                    "source": "signal",
                    "content_type": attachment.get("contentType"),
                    "filename": attachment.get("filename"),
                    "id": attachment.get("id"),
                }
            )
    return ChannelMessage(
        channel="signal",
        sender=str(sender),
        chat_id=str(envelope.get("sourceUuid") or sender),
        text=str(data.get("message") or "").strip(),
        attachments=tuple(attachments),
    )


class TelegramLongPollingTransport:
    def __init__(self, config: TelegramPilotConfig | None = None) -> None:
        self.config = config or TelegramPilotConfig.from_env()

    def get_updates(self, *, offset: int | None = None) -> list[ChannelMessage]:
        return [item.message for item in self.get_update_messages(offset=offset)]

    def get_update_messages(self, *, offset: int | None = None) -> list[TelegramInbound]:
        if not self.config.configured:
            raise ChannelTransportError("TELEGRAM_BOT_TOKEN is not configured")
        query = {"timeout": str(self.config.timeout_seconds)}
        if offset is not None:
            query["offset"] = str(offset)
        response = self._request("getUpdates", query=query)
        if response.get("ok") is not True:
            raise ChannelTransportError("Telegram getUpdates failed")
        messages: list[TelegramInbound] = []
        for update in response.get("result") or []:
            if isinstance(update, dict):
                update_id = update.get("update_id")
                message = parse_telegram_update(update)
                if message is not None and update_id is not None:
                    messages.append(TelegramInbound(update_id=int(update_id), message=message))
        return messages

    def send_message(self, *, chat_id: str, text: str) -> None:
        if not self.config.configured:
            raise ChannelTransportError("TELEGRAM_BOT_TOKEN is not configured")
        response = self._request("sendMessage", data={"chat_id": chat_id, "text": text})
        if response.get("ok") is not True:
            raise ChannelTransportError("Telegram sendMessage failed")

    def _request(self, method: str, *, query: dict[str, str] | None = None, data: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.config.api_base.rstrip('/')}/bot{self.config.bot_token}/{method}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        body = urllib.parse.urlencode(data).encode("utf-8") if data else None
        try:
            with urllib.request.urlopen(url, data=body, timeout=self.config.timeout_seconds + 5) as response:
                import json

                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ChannelTransportError("Telegram request failed") from exc
        if not isinstance(parsed, dict):
            raise ChannelTransportError("Telegram response was not an object")
        return parsed


class SignalCliRestTransport:
    def __init__(self, config: SignalCliRestConfig | None = None) -> None:
        self.config = config or SignalCliRestConfig.from_env()

    def receive(self) -> list[ChannelMessage]:
        if not self.config.configured:
            raise ChannelTransportError("SIGNAL_ACCOUNT_NUMBER and SIGNAL_REST_API_URL are required")
        data = self._request("GET", f"/v1/receive/{urllib.parse.quote(self.config.account_number, safe='')}")
        messages: list[ChannelMessage] = []
        events = data if isinstance(data, list) else data.get("messages", []) if isinstance(data, dict) else []
        for event in events:
            if isinstance(event, dict):
                message = parse_signal_event(event)
                if message is not None:
                    messages.append(message)
        return messages

    def send(self, *, recipient: str, text: str) -> None:
        if not self.config.configured:
            raise ChannelTransportError("SIGNAL_ACCOUNT_NUMBER and SIGNAL_REST_API_URL are required")
        payload = {"message": text, "number": self.config.account_number, "recipients": [recipient]}
        data = self._request("POST", "/v2/send", payload=payload)
        if isinstance(data, dict) and data.get("error"):
            raise ChannelTransportError("Signal send failed")

    def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None) -> Any:
        import json

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"{self.config.rest_api_url.rstrip('/')}{path}",
            data=body,
            headers={"content-type": "application/json"} if body else {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            raise ChannelTransportError("Signal REST request failed") from exc
        return json.loads(raw.decode("utf-8")) if raw else {}
