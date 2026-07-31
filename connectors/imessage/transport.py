from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from connectors.imessage.config import IMessageSettings
from connectors.imessage.models import IMessage, IMessageReply


class IMessageTransportError(RuntimeError):
    """A recoverable failure while invoking the native macOS bridge."""


class UnsupportedIMessageEvent(ValueError):
    """An `imsg` event that is not a supported message."""


class IMessageTransport:
    """Small adapter around the native macOS `imsg` command-line bridge."""

    def __init__(self, settings: IMessageSettings | None = None) -> None:
        self._settings = settings or IMessageSettings()

    def watch_command(self, *, since_rowid: int | None = None) -> list[str]:
        command = [
            self._settings.resolved_imsg_path,
            "watch",
            "--db",
            self._settings.imessage_database_path,
            "--json",
        ]
        if since_rowid is not None:
            command.extend(["--since-rowid", str(since_rowid)])
        return command

    def send_command(self, reply: IMessageReply) -> list[str]:
        return [
            self._settings.resolved_imsg_path,
            "send",
            "--db",
            self._settings.imessage_database_path,
            "--chat-id",
            str(reply.chat_id),
            "--text",
            reply.text,
            "--service",
            "imessage",
            "--json",
        ]

    def chats_command(self, *, limit: int) -> list[str]:
        return [
            self._settings.resolved_imsg_path,
            "chats",
            "--limit",
            str(limit),
            "--json",
        ]

    def history_command(self, *, chat_id: int, limit: int) -> list[str]:
        return [
            self._settings.resolved_imsg_path,
            "history",
            "--chat-id",
            str(chat_id),
            "--limit",
            str(limit),
            "--json",
        ]

    @staticmethod
    def parse_event(event: Any) -> IMessage:
        if not isinstance(event, dict):
            raise UnsupportedIMessageEvent("event is not an object")

        sender = event.get("sender")
        text = event.get("text")
        message_id = event.get("guid")
        chat_id = event.get("chat_id")
        chat_identifier = event.get("chat_identifier")
        created_at = event.get("created_at")

        if not isinstance(sender, str) or not sender.strip():
            raise UnsupportedIMessageEvent("message has no sender")
        if not isinstance(text, str) or not text.strip():
            raise UnsupportedIMessageEvent("message has no text")
        if not isinstance(message_id, str) or not message_id:
            raise UnsupportedIMessageEvent("message has no guid")
        if not isinstance(chat_id, int):
            raise UnsupportedIMessageEvent("message has no chat id")
        if not isinstance(chat_identifier, str) or not chat_identifier:
            raise UnsupportedIMessageEvent("message has no chat identifier")
        if not isinstance(created_at, str):
            raise UnsupportedIMessageEvent("message has no timestamp")

        try:
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise UnsupportedIMessageEvent("message has an invalid timestamp") from exc

        return IMessage(
            sender=sender,
            text=text,
            message_id=message_id,
            chat_id=chat_id,
            chat_identifier=chat_identifier,
            timestamp=timestamp,
            is_group=event.get("is_group") is True,
            is_from_me=event.get("is_from_me") is True,
        )

    async def watch(self, *, since_rowid: int | None = None) -> AsyncIterator[IMessage]:
        try:
            process = await asyncio.create_subprocess_exec(
                *self.watch_command(since_rowid=since_rowid),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise IMessageTransportError("Unable to start imsg watch") from exc

        if process.stdout is None:
            raise IMessageTransportError("imsg watch has no output stream")

        async for raw_line in process.stdout:
            try:
                payload = json.loads(raw_line)
                yield self.parse_event(payload)
            except (json.JSONDecodeError, UnsupportedIMessageEvent):
                continue

        return_code = await process.wait()
        if return_code:
            detail = ""
            if process.stderr is not None:
                raw_stderr = await process.stderr.read()
                detail = raw_stderr.decode("utf-8", errors="replace").strip()
            raise IMessageTransportError(
                f"imsg watch exited with status {return_code}"
                + (f": {detail}" if detail else "")
            )

    async def recent_messages(self) -> list[IMessage]:
        chats = await self._run_json_lines(
            self.chats_command(limit=self._settings.imessage_poll_chat_limit)
        )

        messages: list[IMessage] = []
        for chat in chats:
            chat_id = chat.get("id") if isinstance(chat, dict) else None
            if not isinstance(chat_id, int):
                continue
            for event in await self._run_json_lines(
                self.history_command(
                    chat_id=chat_id,
                    limit=self._settings.imessage_poll_history_limit,
                )
            ):
                try:
                    messages.append(self.parse_event(event))
                except UnsupportedIMessageEvent:
                    continue

        messages.sort(key=lambda message: message.timestamp)
        return messages

    async def _run_json_lines(self, command: list[str]) -> list[Any]:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._settings.imessage_request_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise IMessageTransportError("imsg command timed out") from exc
        except OSError as exc:
            raise IMessageTransportError("Unable to start imsg command") from exc

        if process.returncode:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise IMessageTransportError(
                f"imsg command failed with status {process.returncode}"
                + (f": {detail}" if detail else "")
            )

        events: list[Any] = []
        for raw_line in stdout.splitlines():
            try:
                events.append(json.loads(raw_line))
            except json.JSONDecodeError:
                continue
        return events

    async def send(self, reply: IMessageReply) -> None:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *self.send_command(reply),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._settings.imessage_send_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            if process is not None:
                process.kill()
                await process.wait()
            raise IMessageTransportError("imsg send timed out") from exc
        except OSError as exc:
            raise IMessageTransportError("Unable to start imsg send") from exc

        if process.returncode:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise IMessageTransportError(
                f"imsg send failed with status {process.returncode}"
                + (f": {detail}" if detail else "")
            )
