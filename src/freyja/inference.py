from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from freyja.config import Settings, settings

logger = logging.getLogger(__name__)


class InferenceLocality(str, Enum):
    DETERMINISTIC = "deterministic"
    IRIS = "iris"
    LOCAL_HEAVY = "local_heavy"
    CLOUD = "cloud"


class ProviderReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_reachable: bool = False
    endpoint_healthy: bool = False
    model_available: bool = False
    model_resident: bool | None = None
    last_successful_inference_at: datetime | None = None
    observed_latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None

    @property
    def ready(self) -> bool:
        return self.host_reachable and self.endpoint_healthy and self.model_available


class InferenceProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    kind: Literal["deterministic", "ollama", "openrouter"]
    base_url: str = ""
    model: str = ""
    capabilities: set[str] = Field(default_factory=set)
    locality: InferenceLocality
    tier: int = Field(ge=0, le=4)
    priority: int = 100
    enabled: bool = True
    readiness: ProviderReadiness = Field(default_factory=ProviderReadiness)


class ProviderRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, InferenceProviderProfile] = Field(default_factory=dict)

    def register(self, profile: InferenceProviderProfile) -> None:
        self.profiles[profile.provider_id] = profile

    def get(self, provider_id: str) -> InferenceProviderProfile | None:
        return self.profiles.get(provider_id)

    def enabled(self) -> list[InferenceProviderProfile]:
        return sorted(
            [profile for profile in self.profiles.values() if profile.enabled],
            key=lambda profile: (profile.priority, profile.provider_id),
        )

    def by_locality(self, locality: InferenceLocality) -> list[InferenceProviderProfile]:
        return [profile for profile in self.enabled() if profile.locality == locality]

    def mark_success(self, provider_id: str, latency_ms: int | None = None) -> None:
        profile = self.profiles[provider_id]
        profile.readiness.host_reachable = True
        profile.readiness.endpoint_healthy = True
        profile.readiness.model_available = True
        profile.readiness.last_successful_inference_at = datetime.now(UTC)
        if latency_ms is not None:
            profile.readiness.observed_latency_ms = max(0, int(latency_ms))


def _configured_profiles(config: Settings) -> list[InferenceProviderProfile]:
    raw = config.inference_provider_profiles_json.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid FREYJA_INFERENCE_PROVIDER_PROFILES JSON")
        return []
    if not isinstance(payload, list):
        logger.warning("Ignoring FREYJA_INFERENCE_PROVIDER_PROFILES because it is not a list")
        return []

    profiles: list[InferenceProviderProfile] = []
    for item in payload:
        if not isinstance(item, dict):
            logger.warning("Ignoring non-object inference provider profile")
            continue
        try:
            profiles.append(InferenceProviderProfile.model_validate(item))
        except ValidationError as exc:
            logger.warning("Ignoring invalid inference provider profile: %s", exc)
    return profiles


def provider_registry_from_settings(config: Settings = settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    legacy_base_url = config.ollama_base_url.rstrip("/")
    reasoning_base_url = (config.ollama_reasoning_base_url or config.ollama_base_url).rstrip("/")

    registry.register(
        InferenceProviderProfile(
            provider_id="legacy_ollama",
            kind="ollama",
            base_url=legacy_base_url,
            model=config.ollama_chat_model or config.ollama_model,
            capabilities={"chat", "classification", "summarization"},
            locality=InferenceLocality.IRIS,
            tier=1,
            priority=20,
        )
    )
    registry.register(
        InferenceProviderProfile(
            provider_id="iris_router",
            kind="ollama",
            base_url=config.iris_ollama_base_url.rstrip("/"),
            model=config.iris_router_model,
            capabilities={"classification", "route_recommendation", "reflex"},
            locality=InferenceLocality.IRIS,
            tier=1,
            priority=10,
            enabled=bool(config.iris_router_enabled),
        )
    )
    registry.register(
        InferenceProviderProfile(
            provider_id="heavy_local",
            kind="ollama",
            base_url=reasoning_base_url,
            model=config.ollama_reasoning_model,
            capabilities={"chat", "reasoning", "coding", "planning"},
            locality=InferenceLocality.LOCAL_HEAVY,
            tier=3,
            priority=30,
        )
    )
    registry.register(
        InferenceProviderProfile(
            provider_id="qwen_coding",
            kind="ollama",
            base_url=reasoning_base_url,
            model=config.ollama_coding_model,
            capabilities={"chat", "coding", "debugging", "refactoring"},
            locality=InferenceLocality.LOCAL_HEAVY,
            tier=3,
            priority=28,
        )
    )
    registry.register(
        InferenceProviderProfile(
            provider_id="openrouter_frontier",
            kind="openrouter",
            base_url=config.openrouter_base_url.rstrip("/"),
            model=config.openrouter_model,
            capabilities={"chat", "reasoning", "coding", "long_context"},
            locality=InferenceLocality.CLOUD,
            tier=4,
            priority=40,
            enabled=bool(config.cloud_enabled),
        )
    )
    for profile in _configured_profiles(config):
        registry.register(profile)
    return registry


def legacy_provider_profile_id(provider: str) -> str | None:
    if provider == "ollama":
        return "legacy_ollama"
    if provider == "local_reasoning":
        return "heavy_local"
    if provider == "openrouter":
        return "openrouter_frontier"
    if provider == "deterministic":
        return "deterministic"
    return None
