import logging
import time
from typing import Any

import httpx

from freyja.config import settings
from freyja.system_prompt import FREYJA_SYSTEM_PROMPT, FREYJA_TOOL_CALL_INSTRUCTION


logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = settings.ollama_model if model is None else model

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False

    async def tags(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            return {"error": str(exc)}

    async def chat(
        self,
        prompt: str,
        model: str | None = None,
        stream: bool = False,
        tools_required: bool = False,
        tools: list[Any] | None = None,
        output_tokens: int | None = None,
        retry_on_empty_length: bool = True,
    ) -> dict:
        target_model = model or self.model
        if not target_model:
            return {"error": "No Ollama model configured"}

        system_content = FREYJA_SYSTEM_PROMPT
        if tools_required:
            system_content = f"{FREYJA_SYSTEM_PROMPT}\n\n{FREYJA_TOOL_CALL_INSTRUCTION}"

        first_budget = self._output_budget(output_tokens)
        response = await self._chat_once(
            target_model=target_model,
            system_content=system_content,
            prompt=prompt,
            stream=stream,
            tools=tools,
            output_tokens=first_budget,
            retry=False,
        )
        if "error" in response:
            return response

        message = response.get("message", {})
        if (
            retry_on_empty_length
            and not str(message.get("content") or "").strip()
            and not (message.get("tool_calls") or [])
            and response.get("done_reason") == "length"
        ):
            retry_budget = max(settings.ollama_retry_output_tokens, first_budget * 2, settings.ollama_min_output_tokens)
            retry_response = await self._chat_once(
                target_model=target_model,
                system_content=system_content,
                prompt=prompt,
                stream=stream,
                tools=tools,
                output_tokens=retry_budget,
                retry=True,
            )
            if "error" in retry_response:
                return retry_response
            retry_response["retried"] = True
            response = retry_response

        content = str(response.get("message", {}).get("content") or "")
        tool_calls = response.get("message", {}).get("tool_calls") or []
        if not content.strip() and not tool_calls:
            status = "empty_content"
            response["status"] = status
            response["error"] = "Ollama returned empty content"
            self._log_observability(response, status=status)
            return response

        response["status"] = "ok"
        self._log_observability(response, status="ok")
        return response

    async def _chat_once(
        self,
        *,
        target_model: str,
        system_content: str,
        prompt: str,
        stream: bool,
        tools: list[Any] | None,
        output_tokens: int,
        retry: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "stream": stream,
            "think": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": 0.2,
                "num_predict": output_tokens,
            },
        }
        if tools:
            payload["tools"] = [self._ollama_tool_schema(tool) for tool in tools if tool.enabled]

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=240.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"Ollama HTTP {exc.response.status_code}", "model": target_model}
        except Exception as exc:
            return {"error": str(exc), "model": target_model}

        latency_ms = int((time.monotonic() - start) * 1000)
        sanitized = self._sanitize_response(data, target_model=target_model, latency_ms=latency_ms, retry=retry)
        sanitized["output_tokens_budget"] = output_tokens
        return sanitized

    def _output_budget(self, output_tokens: int | None) -> int:
        requested = settings.ollama_default_output_tokens if output_tokens is None else output_tokens
        return max(requested, settings.ollama_min_output_tokens)

    def _sanitize_response(
        self,
        data: dict[str, Any],
        *,
        target_model: str,
        latency_ms: int,
        retry: bool,
    ) -> dict[str, Any]:
        message = data.get("message") or {}
        sanitized_message = {
            "role": message.get("role", "assistant"),
            "content": message.get("content") or "",
        }
        if message.get("tool_calls"):
            sanitized_message["tool_calls"] = message.get("tool_calls")
        eval_count = int(data.get("eval_count") or 0)
        eval_duration = int(data.get("eval_duration") or 0)
        generation_rate = eval_count / (eval_duration / 1_000_000_000) if eval_count and eval_duration else None
        observability = {
            "provider": "ollama",
            "model": data.get("model", target_model),
            "latency_ms": latency_ms,
            "prompt_tokens": data.get("prompt_eval_count"),
            "generated_tokens": data.get("eval_count"),
            "generation_tokens_per_second": round(generation_rate, 2) if generation_rate else None,
            "retried": retry,
            "done_reason": data.get("done_reason"),
        }
        return {
            "model": data.get("model", target_model),
            "message": sanitized_message,
            "done": data.get("done"),
            "done_reason": data.get("done_reason"),
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "eval_duration": data.get("eval_duration"),
            "latency_ms": latency_ms,
            "observability": observability,
        }

    def _ollama_tool_schema(self, tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        }

    def _log_observability(self, response: dict[str, Any], *, status: str) -> None:
        observability = dict(response.get("observability") or {})
        observability["status"] = status
        logger.info(observability)

    async def list_local_models(self) -> list[str]:
        tags = await self.tags()
        if "error" in tags:
            return []
        return [model.get("name", "") for model in tags.get("models", [])]
