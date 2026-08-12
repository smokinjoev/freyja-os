from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from freyja.config import settings
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.router import _classify_privacy


class InferenceTier(StrEnum):
    LOCAL = "LOCAL"
    FREE = "FREE"
    FAST = "FAST"
    REASONING = "REASONING"
    DEEP = "DEEP"
    FRONTIER = "FRONTIER"
    OLLAMA_CLOUD = "OLLAMA_CLOUD"


class TierPolicy(BaseModel):
    provider: str
    model: str
    input_per_m: float = 0.0
    output_per_m: float = 0.0
    privacy_allows_cloud: bool = False


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    tier: InferenceTier | None = None
    privacy: str | None = None
    output_tokens_estimate: int = 512
    tools_required: StrictBool = False
    spent_this_month: float = 0.0
    frontier_approved: StrictBool = False


class InferenceDecision(BaseModel):
    tier: InferenceTier
    provider: str
    model: str
    reason: str
    privacy_classification: str
    estimated_cost_usd: float
    fallback_attempts: list[dict[str, Any]] = Field(default_factory=list)


class InferenceResult(BaseModel):
    decision: InferenceDecision
    response: str
    latency_ms: int | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


def _estimate_input_tokens(prompt: str) -> int:
    return max(1, int(len(prompt) * 0.25))


def _estimate_cost(prompt: str, output_tokens: int, policy: TierPolicy) -> float:
    input_tokens = _estimate_input_tokens(prompt)
    cost = (input_tokens * policy.input_per_m / 1_000_000) + (
        max(0, output_tokens) * policy.output_per_m / 1_000_000
    )
    return round(cost, 6)


class InferenceGateway:
    def __init__(
        self,
        *,
        ollama_client: OllamaClient | None = None,
        openrouter_client: OpenRouterClient | None = None,
    ) -> None:
        self.ollama_client = ollama_client or OllamaClient(model=settings.inference_gateway_local_model)
        self.openrouter_client = openrouter_client or OpenRouterClient()

    def tier_policies(self) -> dict[InferenceTier, TierPolicy]:
        return {
            InferenceTier.LOCAL: TierPolicy(
                provider="ollama",
                model=settings.inference_gateway_local_model,
                privacy_allows_cloud=False,
            ),
            InferenceTier.FREE: TierPolicy(
                provider="openrouter",
                model=settings.inference_gateway_free_model,
                privacy_allows_cloud=True,
            ),
            InferenceTier.FAST: TierPolicy(
                provider="openrouter",
                model=settings.inference_gateway_fast_model,
                input_per_m=settings.inference_gateway_fast_input_per_m,
                output_per_m=settings.inference_gateway_fast_output_per_m,
                privacy_allows_cloud=True,
            ),
            InferenceTier.REASONING: TierPolicy(
                provider="openrouter",
                model=settings.inference_gateway_reasoning_model,
                input_per_m=settings.inference_gateway_reasoning_input_per_m,
                output_per_m=settings.inference_gateway_reasoning_output_per_m,
                privacy_allows_cloud=True,
            ),
            InferenceTier.DEEP: TierPolicy(
                provider="openrouter",
                model=settings.inference_gateway_deep_model,
                input_per_m=settings.inference_gateway_deep_input_per_m,
                output_per_m=settings.inference_gateway_deep_output_per_m,
                privacy_allows_cloud=True,
            ),
            InferenceTier.FRONTIER: TierPolicy(
                provider="openrouter",
                model=settings.inference_gateway_frontier_model,
                input_per_m=settings.inference_gateway_frontier_input_per_m,
                output_per_m=settings.inference_gateway_frontier_output_per_m,
                privacy_allows_cloud=True,
            ),
            InferenceTier.OLLAMA_CLOUD: TierPolicy(
                provider="ollama_cloud",
                model=settings.inference_gateway_ollama_cloud_model,
                privacy_allows_cloud=True,
            ),
        }

    def default_tier(self) -> InferenceTier:
        configured = settings.inference_gateway_default_tier.upper()
        try:
            return InferenceTier(configured)
        except ValueError:
            return InferenceTier.FAST

    def _approved_cloud_model(self, model: str) -> bool:
        approved = settings.approved_inference_gateway_models or settings.approved_openrouter_models
        return not approved or model in approved

    def decide(self, request: InferenceRequest) -> InferenceDecision:
        privacy = _classify_privacy(request.prompt, request.privacy)
        requested_tier = request.tier or self.default_tier()
        policies = self.tier_policies()
        policy = policies[requested_tier]
        fallback_attempts: list[dict[str, Any]] = []

        if requested_tier == InferenceTier.FRONTIER and not request.frontier_approved:
            raise HTTPException(status_code=403, detail="FRONTIER tier requires explicit approval.")

        if requested_tier == InferenceTier.FREE and not policy.model:
            raise HTTPException(status_code=503, detail="FREE tier is not configured.")

        if requested_tier == InferenceTier.OLLAMA_CLOUD and not (
            settings.inference_gateway_ollama_cloud_base_url
            and settings.inference_gateway_ollama_cloud_api_key
            and policy.model
        ):
            raise HTTPException(status_code=503, detail="OLLAMA_CLOUD tier is not configured.")

        if privacy == "sensitive" and policy.provider != "ollama":
            fallback_attempts.append(
                {
                    "tier": requested_tier.value,
                    "provider": policy.provider,
                    "outcome": "sensitive request kept local",
                }
            )
            requested_tier = InferenceTier.LOCAL
            policy = policies[requested_tier]

        estimated_cost = _estimate_cost(request.prompt, request.output_tokens_estimate, policy)
        if policy.provider in {"openrouter", "ollama_cloud"}:
            if not settings.cloud_enabled:
                raise HTTPException(status_code=503, detail="Cloud inference is disabled.")
        if policy.provider == "openrouter":
            if not self._approved_cloud_model(policy.model):
                raise HTTPException(status_code=403, detail="Requested inference model is not allowlisted.")
            if request.spent_this_month >= settings.inference_gateway_monthly_hard_limit:
                raise HTTPException(status_code=402, detail="Inference gateway monthly budget exhausted.")
            if estimated_cost > settings.inference_gateway_per_request_limit:
                raise HTTPException(status_code=402, detail="Inference request exceeds per-request budget.")

        return InferenceDecision(
            tier=requested_tier,
            provider=policy.provider,
            model=policy.model,
            reason=f"{requested_tier.value} tier selected",
            privacy_classification=privacy,
            estimated_cost_usd=estimated_cost,
            fallback_attempts=fallback_attempts,
        )

    async def chat(self, request: InferenceRequest) -> InferenceResult:
        started = time.monotonic()
        decision = self.decide(request)
        if decision.provider == "ollama":
            response = await self.ollama_client.chat(
                prompt=request.prompt,
                model=decision.model,
                output_tokens=request.output_tokens_estimate,
            )
            if "error" in response:
                raise HTTPException(status_code=503, detail="Local inference provider unavailable.")
            response_text = response.get("message", {}).get("content", "")
            usage = response.get("usage", {})
        elif decision.provider == "ollama_cloud":
            ollama_cloud_client = OpenRouterClient(
                base_url=settings.inference_gateway_ollama_cloud_base_url,
                api_key=settings.inference_gateway_ollama_cloud_api_key,
                model=decision.model,
            )
            response = await ollama_cloud_client.chat(
                prompt=request.prompt,
                model=decision.model,
                tools_required=request.tools_required,
            )
            if "error" in response:
                raise HTTPException(status_code=503, detail="Ollama Cloud inference provider unavailable.")
            response_text = response.get("response", "")
            usage = response.get("usage", {})
        else:
            response = await self.openrouter_client.chat(
                prompt=request.prompt,
                model=decision.model,
                tools_required=request.tools_required,
            )
            if "error" in response:
                raise HTTPException(status_code=503, detail="Cloud inference provider unavailable.")
            response_text = response.get("response", "")
            usage = response.get("usage", {})

        return InferenceResult(
            decision=decision,
            response=response_text,
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=usage,
        )


gateway = InferenceGateway()
inference_gateway_router = APIRouter(prefix="/inference-gateway", tags=["inference-gateway"])


@inference_gateway_router.get("/status")
async def inference_gateway_status() -> dict[str, Any]:
    policies = gateway.tier_policies()
    return {
        "service": "freyja-inference-gateway",
        "enabled": settings.inference_gateway_enabled,
        "monthly_hard_limit_usd": settings.inference_gateway_monthly_hard_limit,
        "per_request_limit_usd": settings.inference_gateway_per_request_limit,
        "default_tier": gateway.default_tier().value,
        "tiers": {
            tier.value: {
                "provider": policy.provider,
                "model": policy.model,
                "input_per_m": policy.input_per_m,
                "output_per_m": policy.output_per_m,
            }
            for tier, policy in policies.items()
        },
        "openrouter_key_configured": bool(settings.openrouter_api_key),
        "allowlist_count": len(settings.approved_inference_gateway_models or settings.approved_openrouter_models),
    }


@inference_gateway_router.post("/decide")
async def inference_gateway_decide(request: InferenceRequest) -> InferenceDecision:
    return gateway.decide(request)


@inference_gateway_router.post("/chat")
async def inference_gateway_chat(request: InferenceRequest) -> InferenceResult:
    if not settings.inference_gateway_enabled:
        raise HTTPException(status_code=503, detail="Inference gateway is disabled.")
    return await gateway.chat(request)
