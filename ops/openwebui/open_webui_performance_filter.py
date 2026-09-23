"""
title: Freyja Local Performance Footer
author: Freyja OS
version: 1.0.0
required_open_webui_version: 0.11.3
"""

from __future__ import annotations

import re
import time
from typing import Any

from pydantic import BaseModel, Field


FOOTER_MARKER = "Perf:"


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=1000)
        show_estimated_tokens: bool = Field(default=True)

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._streams: dict[str, dict[str, Any]] = {}

    def stream(self, event: dict[str, Any]) -> dict[str, Any]:
        stream_id = str(event.get("id") or "default")
        state = self._streams.setdefault(
            stream_id,
            {
                "started_at": time.monotonic(),
                "content": "",
                "usage": {},
                "footer_sent": False,
            },
        )

        usage = event.get("usage")
        if isinstance(usage, dict):
            state["usage"].update(usage)
        timings = event.get("timings")
        if isinstance(timings, dict):
            state["usage"].update(timings)

        choices = event.get("choices")
        if not isinstance(choices, list):
            return event

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                delta = {}
                choice["delta"] = delta

            content = delta.get("content")
            if isinstance(content, str):
                state["content"] += content

            if choice.get("finish_reason") and not state["footer_sent"]:
                duration = self._duration_seconds(state["usage"])
                if duration is None:
                    duration = max(0.01, time.monotonic() - state["started_at"])
                token_count, token_source = self._completion_tokens(state["usage"], state["content"])
                if token_source == "estimated" and not self.valves.show_estimated_tokens:
                    continue
                tokens_per_second = self._tokens_per_second(state["usage"], token_count, duration)
                footer = self._format_footer(token_count, token_source, duration, tokens_per_second)
                separator = "\n\n" if state["content"].strip() else ""
                delta["content"] = f"{content or ''}{separator}{footer}"
                state["footer_sent"] = True
                self._streams.pop(stream_id, None)
                break

        return event

    def outlet(self, body: dict[str, Any], __model__: Any = None) -> dict[str, Any]:
        messages = body.get("messages")
        if not isinstance(messages, list):
            return body

        assistant = self._last_assistant_message(messages)
        if not assistant:
            return body

        content = self._message_content(assistant)
        if FOOTER_MARKER in content:
            return body

        usage = self._usage(assistant)
        token_basis = content or self._output_text(assistant.get("output"))
        token_count, token_source = self._completion_tokens(usage, token_basis)
        duration = self._duration_seconds(usage)
        tokens_per_second = self._tokens_per_second(usage, token_count, duration)

        if token_source == "estimated" and not self.valves.show_estimated_tokens:
            return body

        footer = self._format_footer(token_count, token_source, duration, tokens_per_second)
        assistant["content"] = f"{content.rstrip()}\n\n{footer}".lstrip()
        return body

    def _last_assistant_message(self, messages: list[Any]) -> dict[str, Any] | None:
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                return message
        return None

    def _message_content(self, message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        return ""

    def _output_text(self, output: Any) -> str:
        if not isinstance(output, list):
            return ""
        text: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text.append(part["text"])
        return "".join(text)

    def _usage(self, message: dict[str, Any]) -> dict[str, Any]:
        usage = message.get("usage")
        return usage if isinstance(usage, dict) else {}

    def _completion_tokens(self, usage: dict[str, Any], content: str) -> tuple[int, str]:
        for key in (
            "completion_tokens",
            "output_tokens",
            "response_tokens",
            "generated_tokens",
            "eval_count",
            "completion_token_count",
        ):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                return value, "reported"
            if isinstance(value, float) and value >= 0:
                return int(value), "reported"

        estimated = max(1, round(len(re.findall(r"\S+", content)) * 1.33))
        return estimated, "estimated"

    def _duration_seconds(self, usage: dict[str, Any]) -> float | None:
        for key in ("generation_duration", "duration", "elapsed", "total_duration", "eval_duration"):
            value = usage.get(key)
            seconds = self._coerce_duration(value)
            if seconds is not None and seconds > 0:
                return seconds
        return None

    def _tokens_per_second(
        self, usage: dict[str, Any], token_count: int, duration: float | None
    ) -> float | None:
        for key in ("tokens_per_second", "tokens_per_sec", "eval_rate", "predicted_per_second"):
            value = usage.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        if duration and duration > 0:
            return token_count / duration
        return None

    def _coerce_duration(self, value: Any) -> float | None:
        if not isinstance(value, (int, float)) or value <= 0:
            return None
        if value > 1_000_000:
            return float(value) / 1_000_000_000.0
        return float(value)

    def _format_footer(
        self,
        token_count: int,
        token_source: str,
        duration: float | None,
        tokens_per_second: float | None,
    ) -> str:
        token_label = "output tokens" if token_source == "reported" else "estimated output tokens"
        duration_label = f"{duration:.2f}s" if duration is not None else "unknown"
        speed_label = f"{tokens_per_second:.2f} tokens/sec" if tokens_per_second is not None else "unknown tokens/sec"
        return f"{FOOTER_MARKER} `{speed_label} | {token_count} {token_label} | generation {duration_label}`"
