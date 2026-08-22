import time
from typing import Any

import httpx

from freyja.config import settings
from freyja.system_prompt import FREYJA_SYSTEM_PROMPT, FREYJA_TOOL_CALL_INSTRUCTION


class LocalOpenAIClient:
    """OpenAI-compatible client for local llama.cpp/vLLM-style endpoints."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        default_output_tokens: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_output_tokens = default_output_tokens or settings.vulcan_default_output_tokens

    async def healthy(self) -> bool:
        health_url = self.base_url.removesuffix("/v1")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{health_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        prompt: str,
        model: str | None = None,
        stream: bool = False,
        tools_required: bool = False,
        tools: list[Any] | None = None,
        output_tokens: int | None = None,
        retry_on_empty_length: bool = True,
    ) -> dict[str, Any]:
        target_model = model or self.model
        if not target_model:
            return {"error": "No local OpenAI-compatible model configured"}

        first_budget = self._output_budget(output_tokens)
        response = await self._chat_once(
            target_model=target_model,
            prompt=prompt,
            stream=stream,
            tools_required=tools_required,
            tools=tools,
            output_tokens=first_budget,
            retry=False,
        )
        if "error" in response:
            return response

        if (
            retry_on_empty_length
            and not str(response.get("response") or "").strip()
            and response.get("finish_reason") == "length"
        ):
            retry_budget = max(settings.ollama_retry_output_tokens, first_budget * 2, settings.ollama_min_output_tokens)
            retry_response = await self._chat_once(
                target_model=target_model,
                prompt=prompt,
                stream=stream,
                tools_required=tools_required,
                tools=tools,
                output_tokens=retry_budget,
                retry=True,
            )
            if "error" in retry_response:
                return retry_response
            retry_response["retried"] = True
            response = retry_response

        if not str(response.get("response") or "").strip():
            response["status"] = "empty_content"
            response["error"] = "Local OpenAI-compatible endpoint returned empty content"
            return response

        response["status"] = "ok"
        return response

    async def vision_chat(
        self,
        *,
        prompt: str,
        image_url: str,
        model: str | None = None,
        output_tokens: int | None = None,
    ) -> dict[str, Any]:
        target_model = model or self.model
        if not target_model:
            return {"error": "No local OpenAI-compatible vision model configured"}

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": FREYJA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "stream": False,
            "max_tokens": self._output_budget(output_tokens),
            "temperature": 0.0,
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"Local OpenAI-compatible HTTP {exc.response.status_code}", "model": target_model}
        except Exception as exc:
            return {"error": str(exc), "model": target_model}

        latency_ms = int((time.monotonic() - start) * 1000)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        response_text = message.get("content") or ""
        if not str(response_text).strip():
            return {
                "status": "empty_content",
                "error": "Local OpenAI-compatible vision endpoint returned empty content",
                "model": data.get("model", target_model),
                "latency_ms": latency_ms,
            }

        return {
            "status": "ok",
            "model": data.get("model", target_model),
            "response": response_text,
            "usage": data.get("usage") or {},
            "latency_ms": latency_ms,
            "finish_reason": choice.get("finish_reason"),
            "timings": data.get("timings") or {},
        }

    async def _chat_once(
        self,
        *,
        target_model: str,
        prompt: str,
        stream: bool,
        tools_required: bool,
        tools: list[Any] | None,
        output_tokens: int,
        retry: bool,
    ) -> dict[str, Any]:
        system_content = FREYJA_SYSTEM_PROMPT
        if tools_required:
            system_content = f"{FREYJA_SYSTEM_PROMPT}\n\n{FREYJA_TOOL_CALL_INSTRUCTION}"

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "stream": stream,
            "max_tokens": output_tokens,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = [self._openai_tool_schema(tool) for tool in tools if tool.enabled]

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=240.0) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"Local OpenAI-compatible HTTP {exc.response.status_code}", "model": target_model}
        except Exception as exc:
            return {"error": str(exc), "model": target_model}

        latency_ms = int((time.monotonic() - start) * 1000)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        timings = data.get("timings") or {}
        response_text = message.get("content") or ""

        return {
            "model": data.get("model", target_model),
            "response": response_text,
            "usage": usage,
            "latency_ms": latency_ms,
            "finish_reason": choice.get("finish_reason"),
            "timings": timings,
            "retried": retry,
        }

    def _output_budget(self, output_tokens: int | None) -> int:
        requested = self.default_output_tokens if output_tokens is None else output_tokens
        return max(requested, settings.ollama_min_output_tokens)

    def _openai_tool_schema(self, tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        }
