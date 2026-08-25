from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from freyja.config import settings
from freyja.iris_router import IrisRouterClient, IrisShadowResult
from freyja.roadmode_app import app as director_app

logger = logging.getLogger(__name__)
iris_router = IrisRouterClient()


def _provider_target(provider: str | None) -> str | None:
    if provider == "ollama":
        return "iris"
    if provider == "local_reasoning":
        return "local_heavy"
    if provider == "openrouter":
        return "cloud"
    if provider == "deterministic":
        return "deterministic"
    return None


def _parse_route_request(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not str(payload.get("prompt") or "").strip():
        return None
    return payload


async def _recommend(payload: dict[str, Any]) -> IrisShadowResult:
    return await iris_router.recommend(
        str(payload.get("prompt") or ""),
        task_type=payload.get("task_type"),
        privacy=payload.get("privacy"),
        tools_required=bool(payload.get("tools_required", False)),
        context_size=int(payload.get("context_size") or 0),
    )


async def _record_shadow_comparison(
    shadow_task: asyncio.Task[IrisShadowResult],
    response_body: bytes,
) -> None:
    try:
        shadow = await shadow_task
    except Exception:
        logger.exception("Iris shadow task failed")
        return

    actual: dict[str, Any] = {}
    try:
        parsed = json.loads(response_body.decode("utf-8"))
        if isinstance(parsed, dict):
            actual = parsed
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    recommendation = shadow.recommendation
    actual_target = _provider_target(str(actual.get("provider") or "") or None)
    recommended_target = recommendation.preferred_target if recommendation else None
    agreement = bool(actual_target and recommended_target and actual_target == recommended_target)

    logger.info(
        {
            "event": "iris_shadow_route",
            "request_id": actual.get("request_id"),
            "director_provider": actual.get("provider"),
            "director_model": actual.get("model"),
            "director_target": actual_target,
            "iris_ok": shadow.ok,
            "iris_model": shadow.model,
            "iris_latency_ms": shadow.latency_ms,
            "iris_tier": recommendation.tier if recommendation else None,
            "iris_target": recommended_target,
            "iris_task": recommendation.task if recommendation else None,
            "iris_confidence": recommendation.confidence if recommendation else None,
            "agreement": agreement,
            "iris_error": shadow.error,
        }
    )


class IrisShadowMiddleware:
    """Observe /route traffic with Iris without changing Director behavior.

    The request is replayed unchanged to the underlying Director. Iris runs in
    a separate asyncio task, and the comparison is logged after the Director
    response has already been sent. Shadow inference therefore cannot select a
    provider, authorize a tool, mutate the response, or block the request.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/route"
            or not settings.iris_router_enabled
            or not settings.iris_router_shadow_enabled
        ):
            await self.app(scope, receive, send)
            return

        request_messages: list[dict[str, Any]] = []
        body_parts: list[bytes] = []
        while True:
            message = await receive()
            request_messages.append(message)
            if message.get("type") == "http.request":
                body_parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            else:
                break

        payload = _parse_route_request(b"".join(body_parts))
        shadow_task = asyncio.create_task(_recommend(payload)) if payload else None

        replay_index = 0

        async def replay_receive() -> dict[str, Any]:
            nonlocal replay_index
            if replay_index < len(request_messages):
                message = request_messages[replay_index]
                replay_index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        response_parts: list[bytes] = []

        async def shadow_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.body":
                response_parts.append(message.get("body", b""))
            await send(message)
            if (
                shadow_task is not None
                and message.get("type") == "http.response.body"
                and not message.get("more_body", False)
            ):
                asyncio.create_task(_record_shadow_comparison(shadow_task, b"".join(response_parts)))

        await self.app(scope, replay_receive, shadow_send)


app = IrisShadowMiddleware(director_app)
