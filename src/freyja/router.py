import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

from freyja.config import settings

logger = logging.getLogger(__name__)


class RouteRequest(BaseModel):
    prompt: str
    provider: str = "auto"
    model: str | None = None
    task_type: str | None = None
    privacy: str | None = None
    tools_required: bool = False
    context_size: int = 0


class RoutingDecision(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: str
    model: str
    reason: str
    privacy_classification: str
    fallback_attempts: list[dict[str, Any]] = Field(default_factory=list)
    estimated_cost_usd: float = 0.0
    limitation_notice: str | None = None
    public_error_message: str | None = None


class RoutingResult(BaseModel):
    decision: RoutingDecision
    response: str
    latency_ms: int | None = None


SANITIZED_TERMS = {"api key", "authorization", "bearer", "sk-"}


PUBLIC_ERROR_MESSAGES = {
    "ollama": "Local model provider is unavailable.",
    "openrouter": "Cloud model provider is unavailable.",
    "none_available": "No approved provider is currently available.",
    "blocked": "The request was blocked by routing policy.",
}


SENSITIVE_KEYWORDS = {
    "ssn",
    "social security",
    "password",
    "credit card",
    "bank account",
    "routing number",
    "medical record",
    "diagnosis",
    "prescription",
    "therapy",
    "mental health",
    "location",
    "address",
    "home address",
    "phone number",
    "private",
    "confidential",
    "secret",
}

ROUTINE_TASK_TYPES = {
    "chat",
    "summarize",
    "summary",
    "extract",
    "extraction",
    "classify",
    "classification",
    "routine",
}

CLOUD_TASK_TYPES = {
    "code",
    "coding",
    "plan",
    "planning",
    "reason",
    "complex",
    "difficult",
    "large_context",
    "advanced",
    "math",
    "translation",
}


def _classify_privacy(prompt: str, explicit: str | None) -> str:
    if explicit:
        lowered = explicit.lower()
        if lowered in {"private", "sensitive", "public", "routine"}:
            return lowered
    lowered_prompt = prompt.lower()
    if any(keyword in lowered_prompt for keyword in SENSITIVE_KEYWORDS):
        return "sensitive"
    return "routine"


def _routine_score(request: RouteRequest) -> int:
    score = 0
    task = (request.task_type or "").lower()
    if any(rt in task for rt in ROUTINE_TASK_TYPES):
        score += 2
    if not request.tools_required:
        score += 1
    if request.context_size <= 4096:
        score += 1
    if len(request.prompt) <= settings.local_max_prompt_chars:
        score += 1
    return score


def _cloud_score(request: RouteRequest) -> int:
    score = 0
    task = (request.task_type or "").lower()
    if any(ct in task for ct in CLOUD_TASK_TYPES):
        score += 2
    if request.tools_required:
        score += 1
    if request.context_size > 4096:
        score += 1
    if len(request.prompt) > settings.local_max_prompt_chars:
        score += 1
    return score


class Router:
    def __init__(self) -> None:
        self.ollama_client: Any | None = None
        self.openrouter_client: Any | None = None

    def register_clients(self, ollama_client: Any, openrouter_client: Any) -> None:
        self.ollama_client = ollama_client
        self.openrouter_client = openrouter_client

    async def _ollama_healthy(self) -> bool:
        if self.ollama_client is None:
            return False
        return await self.ollama_client.healthy()

    async def _openrouter_healthy(self) -> bool:
        if self.openrouter_client is None:
            return False
        return await self.openrouter_client.healthy()

    def _approved_model(self, requested: str | None) -> tuple[str, str]:
        approved = settings.approved_openrouter_models
        default_model = settings.openrouter_model
        if requested:
            if approved and requested not in approved:
                return default_model, f"requested model not in allowlist; using default {default_model}"
            return requested, f"using requested model {requested}"
        if approved:
            return approved[0], f"using first approved allowlist model {approved[0]}"
        if default_model:
            return default_model, f"using default model {default_model}"
        return "", "no approved OpenRouter model available"

    def _estimate_cost(self, prompt: str) -> float:
        # Very rough heuristic: ~0.25 tokens per character for input and output.
        tokens = len(prompt) * 0.25 * 2
        # Approximate $2 / 1M tokens across allowlisted models.
        return round(tokens * 2.0 / 1_000_000, 6)

    def _record_attempt(self, provider: str, outcome: str) -> dict[str, str]:
        return {"provider": provider, "outcome": outcome}

    async def _route_sensitive(
        self,
        request: RouteRequest,
        *,
        spent_this_month: float,
        estimated_cost: float,
        fallback_attempts: list[dict[str, Any]],
    ) -> RoutingDecision | None:
        """Try to keep sensitive data local; fall back to cloud only when local is unhealthy and cloud is allowed."""
        ollama_healthy = await self._ollama_healthy()
        if ollama_healthy:
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="sensitive/private request with healthy local model",
                privacy_classification="sensitive",
                fallback_attempts=fallback_attempts,
                estimated_cost_usd=0.0,
            )
        fallback_attempts.append(self._record_attempt("ollama", "unhealthy"))

        if not settings.cloud_enabled:
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="sensitive request defaults to local; cloud disabled",
                privacy_classification="sensitive",
                fallback_attempts=fallback_attempts,
                estimated_cost_usd=0.0,
                limitation_notice="Cloud routing is currently disabled; falling back to local.",
            )
        if spent_this_month >= settings.openrouter_monthly_hard_limit:
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="sensitive request defaults to local; hard budget reached",
                privacy_classification="sensitive",
                fallback_attempts=fallback_attempts,
                estimated_cost_usd=estimated_cost,
                limitation_notice="Monthly cloud budget exhausted; falling back to local.",
            )
        if estimated_cost > settings.openrouter_per_request_limit:
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="sensitive request defaults to local; per-request cost limit exceeded",
                privacy_classification="sensitive",
                fallback_attempts=fallback_attempts,
                estimated_cost_usd=estimated_cost,
                limitation_notice="Request exceeds per-request cost limit; falling back to local.",
            )

        openrouter_healthy = await self._openrouter_healthy()
        if not openrouter_healthy:
            fallback_attempts.append(self._record_attempt("openrouter", "unhealthy"))
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="sensitive request defaults to local; openrouter unhealthy",
                privacy_classification="sensitive",
                fallback_attempts=fallback_attempts,
                estimated_cost_usd=estimated_cost,
                limitation_notice="Cloud provider unhealthy; falling back to local.",
            )

        model, reason = self._approved_model(request.model)
        if not model:
            fallback_attempts.append(self._record_attempt("openrouter", "no approved model"))
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="sensitive request defaults to local; no approved cloud model",
                privacy_classification="sensitive",
                fallback_attempts=fallback_attempts,
                estimated_cost_usd=estimated_cost,
                limitation_notice="No approved OpenRouter model; falling back to local.",
            )
        return RoutingDecision(
            provider="openrouter",
            model=model,
            reason=f"sensitive request falls back to cloud; {reason}",
            privacy_classification="sensitive",
            fallback_attempts=fallback_attempts,
            estimated_cost_usd=estimated_cost,
        )

    async def decide(
        self,
        request: RouteRequest,
        *,
        spent_this_month: float = 0.0,
    ) -> RoutingDecision:
        privacy = _classify_privacy(request.prompt, request.privacy)
        fallback_attempts: list[dict[str, Any]] = []
        notice: str | None = None
        reason_tail = ""

        if request.provider not in {"local", "cloud", "auto"}:
            return RoutingDecision(
                provider="error",
                model="",
                reason=f"invalid provider '{request.provider}'",
                privacy_classification=privacy,
                estimated_cost_usd=0.0,
            )

        if request.provider == "local":
            return RoutingDecision(
                provider="ollama",
                model=request.model or settings.ollama_model,
                reason="manual local override",
                privacy_classification=privacy,
                estimated_cost_usd=0.0,
            )

        estimated_cost = self._estimate_cost(request.prompt)

        if request.provider == "cloud":
            if not settings.cloud_enabled:
                return RoutingDecision(
                    provider="ollama",
                    model=request.model or settings.ollama_model,
                    reason="manual cloud override rejected: cloud disabled",
                    privacy_classification=privacy,
                    estimated_cost_usd=0.0,
                    limitation_notice="Cloud routing is currently disabled; falling back to local.",
                )
            if spent_this_month >= settings.openrouter_monthly_hard_limit:
                return RoutingDecision(
                    provider="ollama",
                    model=request.model or settings.ollama_model,
                    reason="manual cloud override rejected: hard budget reached",
                    privacy_classification=privacy,
                    estimated_cost_usd=estimated_cost,
                    limitation_notice="Monthly cloud budget exhausted; falling back to local.",
                )
            if estimated_cost > settings.openrouter_per_request_limit:
                return RoutingDecision(
                    provider="ollama",
                    model=request.model or settings.ollama_model,
                    reason="manual cloud override rejected: per-request cost limit exceeded",
                    privacy_classification=privacy,
                    estimated_cost_usd=estimated_cost,
                    limitation_notice="Request exceeds per-request cost limit; falling back to local.",
                )
            model, reason = self._approved_model(request.model)
            return RoutingDecision(
                provider="openrouter",
                model=model,
                reason=f"manual cloud override; {reason}",
                privacy_classification=privacy,
                estimated_cost_usd=estimated_cost,
            )

        # provider == "auto"
        if privacy == "sensitive":
            sensitive_decision = await self._route_sensitive(
                request,
                spent_this_month=spent_this_month,
                estimated_cost=estimated_cost,
                fallback_attempts=fallback_attempts,
            )
            if sensitive_decision is not None:
                return sensitive_decision

        if _cloud_score(request) > _routine_score(request):
            cloud_allowed = settings.cloud_enabled and spent_this_month < settings.openrouter_monthly_soft_limit
            if cloud_allowed and estimated_cost <= settings.openrouter_per_request_limit:
                openrouter_healthy = await self._openrouter_healthy()
                if openrouter_healthy:
                    model, reason = self._approved_model(request.model)
                    if model:
                        return RoutingDecision(
                            provider="openrouter",
                            model=model,
                            reason=f"cloud preferred for task/context; {reason}",
                            privacy_classification=privacy,
                            fallback_attempts=fallback_attempts,
                            estimated_cost_usd=estimated_cost,
                        )
                    fallback_attempts.append(self._record_attempt("openrouter", "no approved model"))
                else:
                    fallback_attempts.append(self._record_attempt("openrouter", "unhealthy"))
            else:
                if not settings.cloud_enabled:
                    notice = "Cloud routing is currently disabled; falling back to local."
                    reason_tail = "cloud disabled"
                    fallback_attempts.append(self._record_attempt("openrouter", "cloud disabled"))
                elif spent_this_month >= settings.openrouter_monthly_soft_limit:
                    notice = "Monthly cloud soft budget reached; falling back to local."
                    reason_tail = "soft budget reached"
                    fallback_attempts.append(self._record_attempt("openrouter", "soft budget reached"))
                elif estimated_cost > settings.openrouter_per_request_limit:
                    notice = "Request exceeds per-request cost limit; falling back to local."
                    reason_tail = "per-request cost limit exceeded"
                    fallback_attempts.append(self._record_attempt("openrouter", "per-request limit"))

        local_reason = "routine/sensitive request defaults to local"
        if reason_tail:
            local_reason += f"; {reason_tail}"
        return RoutingDecision(
            provider="ollama",
            model=request.model or settings.ollama_model,
            reason=local_reason,
            privacy_classification=privacy,
            fallback_attempts=fallback_attempts,
            estimated_cost_usd=0.0,
            limitation_notice=notice,
        )

    def _public_error(self, provider: str, fallback_attempts: list[dict[str, Any]]) -> str:
        if any(a.get("provider") == "openrouter" for a in fallback_attempts) and any(
            a.get("provider") == "ollama" for a in fallback_attempts
        ):
            return PUBLIC_ERROR_MESSAGES["none_available"]
        if provider in {"openrouter", "cloud"}:
            return PUBLIC_ERROR_MESSAGES["openrouter"]
        return PUBLIC_ERROR_MESSAGES["ollama"]

    async def execute(
        self,
        request: RouteRequest,
        *,
        spent_this_month: float = 0.0,
    ) -> RoutingResult:
        decision = await self.decide(request, spent_this_month=spent_this_month)
        self._log_decision(decision, request)

        if decision.provider == "error":
            decision.public_error_message = PUBLIC_ERROR_MESSAGES["blocked"]
            return RoutingResult(
                decision=decision,
                response="",
            )

        if decision.provider == "ollama":
            if self.ollama_client is None:
                decision.reason += "; ollama client unavailable"
                decision.public_error_message = PUBLIC_ERROR_MESSAGES["ollama"]
                return RoutingResult(decision=decision, response="")
            response = await self.ollama_client.chat(
                prompt=request.prompt,
                model=decision.model or None,
            )
            if "error" in response:
                raw_error = response["error"]
                decision.fallback_attempts.append({"provider": "ollama", "outcome": raw_error})
                if settings.cloud_enabled and request.provider != "local":
                    fallback_result = await self._try_openrouter_fallback(request, decision)
                    fallback_result.decision.fallback_attempts = self._sanitize_fallback_attempts(fallback_result.decision.fallback_attempts)
                    return fallback_result
                decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
                decision.public_error_message = self._public_error("ollama", decision.fallback_attempts)
                return RoutingResult(decision=decision, response="")

            content = response.get("message", {}).get("content", "")
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            return RoutingResult(decision=decision, response=content)

        if decision.provider == "openrouter":
            if self.openrouter_client is None:
                decision.reason += "; openrouter client unavailable"
                decision.public_error_message = PUBLIC_ERROR_MESSAGES["openrouter"]
                return RoutingResult(decision=decision, response="")
            response = await self.openrouter_client.chat(
                prompt=request.prompt,
                model=decision.model or None,
            )
            if "error" in response:
                raw_error = response["error"]
                decision.fallback_attempts.append({"provider": "openrouter", "outcome": raw_error})
                if request.provider != "cloud":
                    fallback_result = await self._try_ollama_fallback(request, decision)
                    fallback_result.decision.fallback_attempts = self._sanitize_fallback_attempts(fallback_result.decision.fallback_attempts)
                    return fallback_result
                decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
                decision.public_error_message = self._public_error("openrouter", decision.fallback_attempts)
                return RoutingResult(decision=decision, response="")

            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            return RoutingResult(
                decision=decision,
                response=response.get("response", ""),
            )

        return RoutingResult(decision=decision, response="")

    async def _try_openrouter_fallback(
        self,
        request: RouteRequest,
        decision: RoutingDecision,
    ) -> RoutingResult:
        cloud_allowed = settings.cloud_enabled and decision.estimated_cost_usd <= settings.openrouter_per_request_limit
        if not cloud_allowed:
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            decision.public_error_message = self._public_error("openrouter", decision.fallback_attempts)
            return RoutingResult(decision=decision, response="")
        if self.openrouter_client is None:
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            decision.public_error_message = PUBLIC_ERROR_MESSAGES["openrouter"]
            return RoutingResult(decision=decision, response="")
        model, reason = self._approved_model(request.model)
        if not model:
            decision.fallback_attempts.append(self._record_attempt("openrouter", "no approved model"))
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            decision.public_error_message = PUBLIC_ERROR_MESSAGES["none_available"]
            return RoutingResult(decision=decision, response="")
        decision.fallback_attempts.append({"provider": "openrouter", "outcome": "attempting fallback"})
        response = await self.openrouter_client.chat(prompt=request.prompt, model=model)
        if "error" in response:
            raw_error = response["error"]
            decision.fallback_attempts.append({"provider": "openrouter", "outcome": raw_error})
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            decision.public_error_message = self._public_error("openrouter", decision.fallback_attempts)
            return RoutingResult(decision=decision, response="")
        new_decision = RoutingDecision(
            request_id=decision.request_id,
            provider="openrouter",
            model=model,
            reason=f"fallback after local failure; {reason}",
            privacy_classification=decision.privacy_classification,
            fallback_attempts=self._sanitize_fallback_attempts(decision.fallback_attempts),
            estimated_cost_usd=decision.estimated_cost_usd,
        )
        self._log_decision(new_decision, request)
        return RoutingResult(decision=new_decision, response=response.get("response", ""))

    async def _try_ollama_fallback(
        self,
        request: RouteRequest,
        decision: RoutingDecision,
    ) -> RoutingResult:
        if self.ollama_client is None:
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            decision.public_error_message = PUBLIC_ERROR_MESSAGES["ollama"]
            return RoutingResult(decision=decision, response="")
        decision.fallback_attempts.append({"provider": "ollama", "outcome": "attempting fallback"})
        response = await self.ollama_client.chat(
            prompt=request.prompt,
            model=request.model or settings.ollama_model or None,
        )
        if "error" in response:
            raw_error = response["error"]
            decision.fallback_attempts.append({"provider": "ollama", "outcome": raw_error})
            decision.fallback_attempts = self._sanitize_fallback_attempts(decision.fallback_attempts)
            decision.public_error_message = self._public_error("ollama", decision.fallback_attempts)
            return RoutingResult(decision=decision, response="")
        new_decision = RoutingDecision(
            request_id=decision.request_id,
            provider="ollama",
            model=request.model or settings.ollama_model,
            reason="fallback after cloud failure",
            privacy_classification=decision.privacy_classification,
            fallback_attempts=self._sanitize_fallback_attempts(decision.fallback_attempts),
            estimated_cost_usd=0.0,
            limitation_notice="Cloud provider failed; returned local response.",
        )
        self._log_decision(new_decision, request)
        return RoutingResult(decision=new_decision, response=response.get("message", {}).get("content", ""))

    def _log_decision(self, decision: RoutingDecision, request: RouteRequest) -> None:
        log_record = {
            "event": "routing_decision",
            "request_id": decision.request_id,
            "provider": decision.provider,
            "model": decision.model,
            "reason": decision.reason,
            "privacy_classification": decision.privacy_classification,
            "estimated_cost_usd": decision.estimated_cost_usd,
            "fallback_attempts": [
                {
                    "provider": attempt.get("provider"),
                    "outcome": self._sanitize_outcome(str(attempt.get("outcome", ""))),
                }
                for attempt in decision.fallback_attempts
            ],
            "prompt_length": len(request.prompt),
            "task_type": request.task_type,
            "tools_required": request.tools_required,
            "context_size": request.context_size,
        }
        logger.info(log_record)

    def _sanitize_outcome(self, outcome: str) -> str:
        lowered = outcome.lower()
        if any(term in lowered for term in SANITIZED_TERMS):
            return "<redacted>"
        return outcome

    def _sanitize_fallback_attempts(self, attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "provider": attempt.get("provider"),
                "outcome": self._sanitize_outcome(str(attempt.get("outcome", ""))),
            }
            for attempt in attempts
        ]


router = Router()
