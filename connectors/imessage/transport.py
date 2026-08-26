from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from connectors.imessage.config import IMessageSettings
from connectors.imessage.models import IMessage, IMessageAttachment, IMessageReply


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
        command = [
            self._settings.resolved_imsg_path,
            "send",
            "--db",
            self._settings.imessage_database_path,
        ]
        if reply.recipient and not reply.is_group:
            command.extend(["--to", reply.recipient])
        else:
            command.extend(["--chat-id", str(reply.chat_id)])
        command.extend(
            [
                "--text",
                reply.text,
                "--service",
                "imessage",
                "--json",
            ]
        )
        return command

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
        attachments = IMessageTransport._parse_attachments(event)
        if not isinstance(text, str):
            text = ""
        if not text.strip() and not attachments:
            raise UnsupportedIMessageEvent("message has no text or attachment")
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
            attachments=attachments,
        )

    @staticmethod
    def _parse_attachments(event: dict[str, Any]) -> list[IMessageAttachment]:
        raw_attachments = event.get("attachments")
        if raw_attachments is None:
            raw_attachments = event.get("attachment")
        if raw_attachments is None:
            raw_attachments = event.get("files")
        if raw_attachments is None:
            raw_attachments = event.get("file")

        if isinstance(raw_attachments, dict):
            items: list[Any] = [raw_attachments]
        elif isinstance(raw_attachments, list):
            items = raw_attachments
        else:
            items = []

        attachments: list[IMessageAttachment] = []
        for item in items:
            if isinstance(item, str) and item.strip():
                attachments.append(IMessageAttachment(filename=Path(item).name, path=item))
                continue
            if not isinstance(item, dict):
                continue
            path = _first_string(item, "path", "filename", "file_path", "transfer_name")
            filename = _first_string(item, "name", "filename", "transfer_name")
            mime_type = _first_string(item, "mime_type", "mime", "uti")
            if not filename and path:
                filename = Path(path).name
            elif filename:
                filename = Path(filename).name
            if filename or path or mime_type:
                attachments.append(
                    IMessageAttachment(
                        filename=filename,
                        mime_type=mime_type,
                        path=path,
                    )
                )
        return attachments

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
        if self._settings.imessage_poll_database_enabled:
            try:
                return await asyncio.to_thread(self._recent_messages_from_database)
            except (OSError, sqlite3.Error, UnsupportedIMessageEvent) as exc:
                raise IMessageTransportError("Unable to read iMessage database") from exc

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

    def _recent_messages_from_database(self) -> list[IMessage]:
        database_path = Path(self._settings.imessage_database_path).expanduser()
        if not database_path.exists():
            raise OSError(f"Messages database does not exist: {database_path}")

        limit = max(
            1,
            self._settings.imessage_poll_chat_limit
            * self._settings.imessage_poll_history_limit,
        )
        database_uri = f"file:{quote(str(database_path))}?mode=ro"
        connection = sqlite3.connect(
            database_uri,
            timeout=max(0.1, self._settings.imessage_command_timeout_seconds),
            uri=True,
        )
        try:
            has_attachment_tables = _database_has_tables(
                connection,
                "attachment",
                "message_attachment_join",
            )
            attachment_select = (
                "GROUP_CONCAT(a.filename, char(31)), GROUP_CONCAT(a.mime_type, char(31))"
                if has_attachment_tables
                else "NULL, NULL"
            )
            attachment_joins = (
                """
                LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID
                LEFT JOIN attachment a ON a.ROWID = maj.attachment_id
                """
                if has_attachment_tables
                else ""
            )
            message_filter = (
                "AND (COALESCE(m.text, '') != '' OR a.ROWID IS NOT NULL)"
                if has_attachment_tables
                else "AND COALESCE(m.text, '') != ''"
            )
            rows = connection.execute(
                f"""
                SELECT
                    m.guid,
                    COALESCE(m.text, ''),
                    COALESCE(NULLIF(h.id, ''), NULLIF(c.chat_identifier, ''), 'unknown'),
                    c.ROWID,
                    c.chat_identifier,
                    m.date,
                    COALESCE(c.style, 0),
                    COALESCE(m.is_from_me, 0),
                    {attachment_select}
                FROM message m
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                JOIN chat c ON c.ROWID = cmj.chat_id
                LEFT JOIN handle h ON h.ROWID = m.handle_id
                {attachment_joins}
                WHERE m.guid IS NOT NULL
                  AND COALESCE(m.is_system_message, 0) = 0
                  {message_filter}
                GROUP BY m.ROWID
                ORDER BY m.date DESC, m.ROWID DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        messages = [
            IMessage(
                sender=str(row[2]),
                text=str(row[1]),
                message_id=str(row[0]),
                chat_id=int(row[3]),
                chat_identifier=str(row[4] or row[2]),
                timestamp=self._parse_apple_timestamp(row[5]),
                is_group=int(row[6] or 0) != 45,
                is_from_me=bool(row[7]),
                attachments=_attachments_from_database_row(row[8], row[9]),
            )
            for row in rows
        ]
        messages.sort(key=lambda message: message.timestamp)
        return messages

    @staticmethod
    def _parse_apple_timestamp(value: Any) -> datetime:
        if not isinstance(value, int | float):
            return datetime.now(tz=UTC)

        seconds = value / 1_000_000_000 if abs(value) >= 1_000_000_000 else value
        return datetime(2001, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds)

    async def _run_json_lines(self, command: list[str]) -> list[Any]:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._settings.imessage_command_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            if process is not None:
                process.kill()
                await process.wait()
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
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                self.send_command(reply),
                text=True,
                capture_output=True,
                timeout=self._settings.imessage_send_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise IMessageTransportError(
                f"imsg send timed out after {self._settings.imessage_send_timeout_seconds:.2f}s"
            ) from exc
        except OSError as exc:
            raise IMessageTransportError("Unable to start imsg send") from exc

        if completed.returncode:
            detail = completed.stderr.strip()
            output = completed.stdout.strip()
            diagnostics = []
            if detail:
                diagnostics.append(f"stderr={detail}")
            if output:
                diagnostics.append(f"stdout={output}")
            raise IMessageTransportError(
                f"imsg send failed with status {completed.returncode}"
                + (f": {'; '.join(diagnostics)}" if diagnostics else "")
            )


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _attachments_from_database_row(filenames: Any, mime_types: Any) -> list[IMessageAttachment]:
    if not isinstance(filenames, str) or not filenames:
        return []
    names = filenames.split("\x1f")
    mimes = mime_types.split("\x1f") if isinstance(mime_types, str) else []
    attachments: list[IMessageAttachment] = []
    for index, name in enumerate(names):
        if not name:
            continue
        attachments.append(
            IMessageAttachment(
                filename=Path(name).name,
                mime_type=mimes[index] if index < len(mimes) and mimes[index] else None,
                path=name,
            )
        )
    return attachments


def _database_has_tables(connection: sqlite3.Connection, *table_names: str) -> bool:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({})".format(
            ",".join("?" for _ in table_names)
        ),
        table_names,
    ).fetchall()
    return {row[0] for row in rows} == set(table_names)
