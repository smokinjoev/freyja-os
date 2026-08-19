import json
import time
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from freyja.config import settings


class IrisRouteRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal[0, 1, 2, 3, 4]
    task: str = Field(min_length=1, max_length=80)
    needs_tools: bool
    sensitivity: Literal["public", "routine", "private", "sensitive"]
    confidence: float = Field(ge=0.0, le=1.0)
    preferred_target: Literal[
        "deterministic",
        "iris",
        "local_heavy",
        "isolated_worker",
        "cloud",
    ]
    reason: str = Field(min_length=1, max_length=240)


class IrisShadowResult(BaseModel):
    ok: bool
    recommendation: IrisRouteRecommendation | None = None
    latency_ms: int | None = None
    model: str | None = None
    error: str | None = None


IRIS_ROUTER_SYSTEM_PROMPT = """You are the Freyja-OS routing classifier running on Iris.
Classify only. Do not answer the request and do not authorize tools.
Return only one compact JSON object with exactly these required keys:
tier, task, needs_tools, sensitivity, confidence, preferred_target, reason.
tier: 0 deterministic, 1 tiny reflex, 2 routine Iris, 3 heavy local, 4 cloud.
sensitivity: public, routine, private, sensitive.
preferred_target: deterministic, iris, local_heavy, isolated_worker, cloud.
confidence must be a decimal from 0.0 to 1.0, for example 0.75.
reason must be 3 to 8 words.
When uncertain, route upward to the more capable tier; avoid under-routing.
No markdown, prose, or extra keys. Director is final authority.
"""


def _ollama_keep_alive_value() -> str | int:
    value = settings.iris_router_keep_alive.strip()
    try:
        return int(value)
    except ValueError:
        return value


class IrisRouterClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.iris_ollama_base_url).rstrip("/")
        self.model = model or settings.iris_router_model
        self.timeout_seconds = timeout_seconds or settings.iris_router_timeout_seconds

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                names = {str(item.get("name") or "") for item in models}
                return self.model in names or any(name.startswith(f"{self.model}:") for name in names)
        except Exception:
            return False

    async def warm(self) -> bool:
        """Load the Iris router model and request indefinite residency."""
        payload = {
            "model": self.model,
            "prompt": "",
            "stream": False,
            "keep_alive": _ollama_keep_alive_value(),
        }
        try:
            async with httpx.AsyncClient(timeout=max(self.timeout_seconds, 30.0)) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
            return True
        except Exception:
            return False

    async def running_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/api/ps")
                response.raise_for_status()
                models = response.json().get("models", [])
                return [str(item.get("name") or "") for item in models if isinstance(item, dict)]
        except Exception:
            return []

    async def model_resident(self) -> bool:
        names = set(await self.running_models())
        return self.model in names or any(name.startswith(f"{self.model}:") for name in names)

    async def recommend(
        self,
        prompt: str,
        *,
        task_type: str | None = None,
        privacy: str | None = None,
        tools_required: bool = False,
        context_size: int = 0,
    ) -> IrisShadowResult:
        if not prompt.strip():
            return IrisShadowResult(ok=False, error="empty prompt")

        clipped_prompt = prompt[: settings.iris_router_max_prompt_chars]
        user_payload = {
            "prompt": clipped_prompt,
            "task_type": task_type,
            "privacy_hint": privacy,
            "tools_required": tools_required,
            "context_size": context_size,
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": IRIS_ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"))},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": _ollama_keep_alive_value(),
            "options": {
                "temperature": 0,
                "num_predict": 100,
            },
        }

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            return IrisShadowResult(
                ok=False,
                model=self.model,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=error.strip(),
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        content = str((data.get("message") or {}).get("content") or "").strip()
        try:
            recommendation = IrisRouteRecommendation.model_validate_json(content)
        except (ValidationError, ValueError) as exc:
            return IrisShadowResult(
                ok=False,
                model=str(data.get("model") or self.model),
                latency_ms=latency_ms,
                error=f"invalid routing JSON: {exc}",
            )

        return IrisShadowResult(
            ok=True,
            recommendation=recommendation,
            latency_ms=latency_ms,
            model=str(data.get("model") or self.model),
        )
