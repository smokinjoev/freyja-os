"""Telegram gateway: authorization, command routing, and Director integration."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from freyja.config import settings as freyja_settings
from freyja.tools.registry import get_registry

from .config import TelegramSettings
from .models import TelegramInboundUpdate, TelegramMessage, TelegramOutboundMessage

logger = logging.getLogger(__name__)

_MAX_RECENT_IDS = 1000
_SAFE_ERROR_TEXT = "Freyja could not process your message. Please try again later."
_UNAUTHORIZED_TEXT = "You are not authorized to use this gateway."
_MAX_STATUS_LENGTH = 4000
_TRUNCATION_SUFFIX = "\n... (truncated)"


class TelegramGatewayError(Exception):
    """Raised when the gateway encounters a fatal configuration error."""


class RejectionReason:
    DISABLED = "gateway_disabled"
    NO_TOKEN = "no_token"
    UNKNOWN_USER = "unknown_user"
    ANONYMOUS_SENDER = "anonymous_sender"
    GROUP_MESSAGE = "group_message"
    SUPERGROUP_MESSAGE = "supergroup_message"
    CHANNEL_MESSAGE = "channel_message"
    DIRECT_MESSAGES_ONLY = "direct_messages_only"
    EMPTY_MESSAGE = "empty_message"
    OVERSIZED_MESSAGE = "oversized_message"
    DUPLICATE_UPDATE = "duplicate_update"
    SMITH_DISABLED = "smith_read_only_disabled"


class TelegramGateway:
    """Receive normalized Telegram updates, enforce policy, and forward to Director."""

    def __init__(
        self,
        settings: TelegramSettings | None = None,
        state_dir: str | None = None,
    ) -> None:
        self._settings = settings or TelegramSettings()
        self._enabled = self._settings.telegram_enabled and self._settings.token_configured
        self._allowed_user_ids = self._settings.allowed_user_id_set
        self._direct_messages_only = self._settings.telegram_direct_messages_only
        self._max_message_chars = self._settings.telegram_max_message_chars
        self._director_url = self._settings.freyja_director_url.rstrip("/")
        self._timeout = self._settings.telegram_request_timeout_seconds
        self._poll_interval = self._settings.telegram_poll_interval_seconds
        self._state_dir = Path(state_dir or self._settings.telegram_state_dir)
        self._offset_file = self._state_dir / "telegram-offset.json"
        self._heartbeat_file = self._state_dir / "telegram-heartbeat.json"
        self._recent_update_ids: deque[int] = deque(maxlen=_MAX_RECENT_IDS)
        self._http_client: httpx.AsyncClient | None = None
        self._last_offset = self._load_offset()
        self._ensure_state_dir()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def allowed_user_ids(self) -> set[int]:
        return set(self._allowed_user_ids)

    @property
    def direct_messages_only(self) -> bool:
        return self._direct_messages_only

    @property
    def bot_token_configured(self) -> bool:
        return self._settings.token_configured

    def _ensure_state_dir(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._state_dir, 0o700)

    def _load_offset(self) -> int:
        if not self._offset_file.exists():
            return 0
        try:
            data = json.loads(self._offset_file.read_text(encoding="utf-8"))
            offset = int(data.get("offset", 0))
            self._recent_update_ids.append(offset)
            return offset
        except Exception:
            return 0

    def _save_offset(self, offset: int) -> None:
        if offset <= 0:
            return
        self._last_offset = offset
        self._ensure_state_dir()
        tmp_path = self._offset_file.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps({"offset": offset, "updated_at": time.time()}),
            encoding="utf-8",
        )
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self._offset_file)
        os.chmod(self._offset_file, 0o600)

    def _record_heartbeat(self) -> None:
        try:
            self._ensure_state_dir()
            tmp_path = self._heartbeat_file.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps({
                    "timestamp": time.time(),
                    "enabled": self._enabled,
                    "direct_messages_only": self._direct_messages_only,
                    "allowed_user_count": len(self._allowed_user_ids),
                    "token_configured": self.bot_token_configured,
                }),
                encoding="utf-8",
            )
            os.chmod(tmp_path, 0o600)
            tmp_path.replace(self._heartbeat_file)
            os.chmod(self._heartbeat_file, 0o600)
        except Exception:
            logger.exception("Failed to record Telegram gateway heartbeat")

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def handle(self, update: TelegramInboundUpdate) -> TelegramOutboundMessage | None:
        """Process a single Telegram update and optionally return a reply."""
        self._record_heartbeat()

        if not self._enabled:
            self._log_rejection(update, RejectionReason.DISABLED)
            return None

        message = update.effective_message
        if message is None:
            return None

        if update.update_id in self._recent_update_ids:
            self._log_rejection(update, RejectionReason.DUPLICATE_UPDATE)
            return None
        self._recent_update_ids.append(update.update_id)
        self._save_offset(update.update_id)

        chat_id = update.chat_id
        if chat_id is None:
            return None

        if not self._settings.token_configured:
            self._log_rejection(update, RejectionReason.NO_TOKEN)
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)

        user_id = update.sender_user_id
        if user_id is None:
            self._log_rejection(update, RejectionReason.ANONYMOUS_SENDER)
            return self._reply(message, _UNAUTHORIZED_TEXT, success=False)

        if update.is_channel:
            self._log_rejection(update, RejectionReason.CHANNEL_MESSAGE)
            return self._reply(message, _UNAUTHORIZED_TEXT, success=False)

        if update.is_group:
            self._log_rejection(update, RejectionReason.GROUP_MESSAGE)
            return self._reply(message, _UNAUTHORIZED_TEXT, success=False)

        if update.chat_type == "supergroup":
            self._log_rejection(update, RejectionReason.SUPERGROUP_MESSAGE)
            return self._reply(message, _UNAUTHORIZED_TEXT, success=False)

        if self._direct_messages_only and not update.is_direct_message:
            self._log_rejection(update, RejectionReason.DIRECT_MESSAGES_ONLY)
            return self._reply(message, _UNAUTHORIZED_TEXT, success=False)

        if user_id not in self._allowed_user_ids:
            self._log_rejection(update, RejectionReason.UNKNOWN_USER)
            return self._reply(message, _UNAUTHORIZED_TEXT, success=False)

        text = update.text.strip()
        if not text:
            self._log_rejection(update, RejectionReason.EMPTY_MESSAGE)
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)

        if len(text) > self._max_message_chars:
            self._log_rejection(update, RejectionReason.OVERSIZED_MESSAGE)
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)

        return await self._route_command(text, message, user_id)

    def _log_rejection(self, update: TelegramInboundUpdate, reason: str) -> None:
        log: dict[str, Any] = {
            "event": "telegram_gateway_rejected",
            "reason": reason,
            "update_id": update.update_id,
        }
        if update.effective_message:
            chat = update.effective_message.chat
            if update.sender_user_id is not None:
                log["user_id"] = update.sender_user_id
            if chat:
                log["chat_id"] = chat.id
                log["chat_type"] = chat.type
        # Never log message bodies or the bot token.
        logger.info(log)

    def _reply(
        self,
        message: TelegramMessage,
        text: str,
        *,
        success: bool = True,
    ) -> TelegramOutboundMessage:
        return TelegramOutboundMessage(
            chat_id=message.chat.id,
            text=self._truncate(text),
            reply_to_message_id=message.message_id,
            success=success,
        )

    def _truncate(self, text: str) -> str:
        if len(text) <= _MAX_STATUS_LENGTH:
            return text
        return text[: _MAX_STATUS_LENGTH - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX

    async def _route_command(
        self,
        text: str,
        message: TelegramMessage,
        user_id: int,
    ) -> TelegramOutboundMessage:
        lowered = text.lower()

        if lowered == "/help" or lowered.startswith("/help "):
            return self._reply(message, self._help_text())

        if lowered == "/whoami" or lowered.startswith("/whoami "):
            return self._reply(
                message,
                f"Your Telegram numeric user ID is {user_id}. Chat type: {message.chat.type}",
            )

        if lowered == "/status" or lowered.startswith("/status "):
            status = await self._status_text()
            return self._reply(message, status)

        if lowered == "/health" or lowered.startswith("/health "):
            health = await self._health_text()
            return self._reply(message, health)

        if lowered == "/models" or lowered.startswith("/models "):
            models = await self._models_text()
            return self._reply(message, models)

        if lowered.startswith("/smith"):
            if not freyja_settings.agent_smith_enabled:
                return self._reply(
                    message,
                    "Agent Smith is currently disabled.",
                    success=False,
                )
            if not (
                self._settings.telegram_smith_read_only_enabled
                or freyja_settings.agent_smith_read_only_enabled
            ):
                return self._reply(
                    message,
                    "Agent Smith read-only mode is not enabled for Telegram.",
                    success=False,
                )
            return await self._handle_smith(text, message)

        if lowered.startswith("/"):
            return self._reply(
                message,
                "Unknown command. Send /help for available commands.",
                success=False,
            )

        return await self._forward_to_freyja(text, message)

    async def _forward_to_freyja(
        self,
        text: str,
        message: TelegramMessage,
    ) -> TelegramOutboundMessage:
        payload = {
            "prompt": text,
            "provider": "auto",
        }
        try:
            client = await self._client()
            response = await client.post(f"{self._director_url}/route", json=payload)
            response.raise_for_status()
            data = response.json()
            reply = data.get("response", "")
            if not reply:
                return self._reply(message, _SAFE_ERROR_TEXT, success=False)
            meta = data.get("provider", "")
            model = data.get("model", "")
            if meta and model:
                reply += f"\n\n(agent: Freyja, provider: {meta}, model: {model})"
            return self._reply(message, reply)
        except httpx.TimeoutException:
            logger.warning({"event": "telegram_director_timeout"})
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)
        except httpx.HTTPStatusError as exc:
            logger.warning({
                "event": "telegram_director_error",
                "status_code": exc.response.status_code,
            })
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)
        except Exception:
            logger.exception({"event": "telegram_unexpected_error"})
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)

    async def _handle_smith(
        self,
        text: str,
        message: TelegramMessage,
    ) -> TelegramOutboundMessage:
        objective = text[len("/smith"):].strip()
        if not objective:
            objective = "status"

        command = objective.split()[0].lower() if objective else ""
        if command in {"status", "repo", "diff", "tests"}:
            objective_map = {
                "status": "repository status",
                "repo": "repository status",
                "diff": "repository diff summary",
                "tests": "run test suite",
            }
            objective = objective_map.get(command, objective)

        return await self._call_smith_read_only(objective, message)

    async def _call_smith_read_only(
        self,
        objective: str,
        message: TelegramMessage,
    ) -> TelegramOutboundMessage:
        payload = {
            "objective": objective,
            "actor": "agent_smith_telegram",
        }
        try:
            client = await self._client()
            response = await client.post(f"{self._director_url}/agents/smith/read-only", json=payload)
            response.raise_for_status()
            data = response.json()
            summary = data.get("message", "")
            if not summary:
                summary = "Agent Smith completed with no summary."
            return self._reply(
                message,
                f"Agent Smith (read-only):\n{summary}",
            )
        except httpx.TimeoutException:
            logger.warning({"event": "telegram_smith_timeout"})
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)
        except httpx.HTTPStatusError as exc:
            logger.warning({
                "event": "telegram_smith_error",
                "status_code": exc.response.status_code,
            })
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)
        except Exception:
            logger.exception({"event": "telegram_smith_unexpected_error"})
            return self._reply(message, _SAFE_ERROR_TEXT, success=False)

    async def _status_text(self) -> str:
        lines: list[str] = ["Freyja status"]
        try:
            client = await self._client()
            health_response = await client.get(f"{self._director_url}/health")
            lines.append(f"Director: {'reachable' if health_response.status_code == 200 else 'unreachable'}")
        except Exception:
            lines.append("Director: unreachable")

        lines.append(f"Telegram gateway: {'enabled' if self._enabled else 'disabled'}")

        try:
            client = await self._client()
            ollama_response = await client.get(f"{self._director_url}/ollama/health")
            ollama_data = ollama_response.json()
            lines.append(f"Ollama: {'healthy' if ollama_data.get('ollama_reachable') else 'unhealthy'}")
        except Exception:
            lines.append("Ollama: unknown")

        try:
            client = await self._client()
            openrouter_response = await client.get(f"{self._director_url}/openrouter/health")
            openrouter_data = openrouter_response.json()
            lines.append(
                f"OpenRouter: {'configured' if openrouter_data.get('key_configured') else 'not configured'}"
            )
        except Exception:
            lines.append("OpenRouter: unknown")

        lines.append(f"Agent Smith enabled: {freyja_settings.agent_smith_enabled}")
        lines.append(f"Smith read-only enabled: {freyja_settings.agent_smith_read_only_enabled}")
        lines.append(f"Smith write enabled: {freyja_settings.agent_smith_write_pilot_enabled}")

        return "\n".join(lines)

    async def _health_text(self) -> str:
        try:
            client = await self._client()
            response = await client.get(f"{self._director_url}/health")
            if response.status_code == 200:
                data = response.json()
                return f"Director health: {data.get('status', 'unknown')}"
            return "Director health: unreachable"
        except Exception:
            return "Director health: unreachable"

    async def _models_text(self) -> str:
        models: list[str] = []
        try:
            client = await self._client()
            response = await client.get(f"{self._director_url}/ollama/models")
            data = response.json()
            models = [m for m in data.get("models", []) if m]
        except Exception:
            pass

        configured = [freyja_settings.ollama_model]
        if freyja_settings.openrouter_model:
            configured.append(freyja_settings.openrouter_model)
        configured.extend(freyja_settings.approved_openrouter_models)
        configured = [m for m in dict.fromkeys(configured) if m]

        lines = ["Configured models:"]
        for model in configured:
            lines.append(f"- {model}")

        if models:
            lines.append("\nOllama available models:")
            for model in models:
                lines.append(f"- {model}")
        else:
            lines.append("\nOllama available models: unable to fetch")

        return "\n".join(lines)

    def _help_text(self) -> str:
        return (
            "Available commands:\n"
            "/help — show this message\n"
            "/status — Freyja, Director, Ollama, OpenRouter, and agent status\n"
            "/health — bounded Director health check\n"
            "/models — configured and available models\n"
            "/whoami — your Telegram numeric user ID and chat type\n"
            "/smith <request> — read-only Agent Smith diagnostics\n"
            "\n"
            "Any ordinary message is routed to Freyja."
        )

    async def poll_updates(self) -> list[TelegramOutboundMessage]:
        """Poll Telegram for updates, process them, and return replies to send."""
        if not self._enabled:
            return []

        token = self._settings.telegram_bot_token.strip()
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params: dict[str, Any] = {"limit": 100}
        if self._last_offset:
            params["offset"] = self._last_offset + 1

        replies: list[TelegramOutboundMessage] = []
        try:
            client = await self._client()
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                logger.warning({"event": "telegram_api_error", "description": data.get("description")})
                return replies

            for raw_update in data.get("result", []):
                try:
                    update = TelegramInboundUpdate.model_validate(raw_update)
                except Exception:
                    logger.warning({"event": "telegram_update_parse_failed", "update_id": raw_update.get("update_id")})
                    continue
                reply = await self.handle(update)
                if reply is not None:
                    replies.append(reply)
        except httpx.TimeoutException:
            logger.warning({"event": "telegram_poll_timeout"})
        except httpx.HTTPStatusError as exc:
            logger.warning({"event": "telegram_poll_http_error", "status_code": exc.response.status_code})
        except Exception:
            logger.exception({"event": "telegram_poll_unexpected_error"})

        return replies

    async def send_reply(self, reply: TelegramOutboundMessage) -> bool:
        """Send a reply message via the Telegram bot API."""
        if not self._enabled:
            return False
        token = self._settings.telegram_bot_token.strip()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = reply.model_dump(exclude_none=True)
        try:
            client = await self._client()
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return bool(data.get("ok"))
        except Exception:
            logger.exception({"event": "telegram_send_reply_failed", "chat_id": reply.chat_id})
            return False

    async def close(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()


gateway = TelegramGateway()
