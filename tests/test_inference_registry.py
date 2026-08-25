from freyja.config import Settings
from freyja.inference import InferenceLocality, ProviderRegistry, provider_registry_from_settings


def test_provider_registry_translates_legacy_ollama_settings() -> None:
    config = Settings(
        ollama_base_url="http://atlas:11434/",
        ollama_model="qwen2.5:1.5b",
        ollama_chat_model="qwen2.5:7b",
        ollama_reasoning_base_url="http://odin:11434/",
        ollama_reasoning_model="gpt-oss:20b",
        ollama_coding_model="qwen2.5-coder:14b-q3",
        cloud_enabled=True,
    )

    registry = provider_registry_from_settings(config)

    legacy = registry.get("legacy_ollama")
    assert legacy is not None
    assert legacy.kind == "ollama"
    assert legacy.base_url == "http://atlas:11434"
    assert legacy.model == "qwen2.5:7b"
    assert legacy.locality == InferenceLocality.IRIS
    assert legacy.tier == 1

    heavy = registry.get("heavy_local")
    assert heavy is not None
    assert heavy.base_url == "http://odin:11434"
    assert heavy.model == "gpt-oss:20b"
    assert heavy.locality == InferenceLocality.LOCAL_HEAVY
    assert heavy.tier == 3

    coding = registry.get("qwen_coding")
    assert coding is not None
    assert coding.base_url == "http://odin:11434"
    assert coding.model == "qwen2.5-coder:14b-q3"
    assert coding.locality == InferenceLocality.LOCAL_HEAVY
    assert coding.tier == 3
    assert "coding" in coding.capabilities


def test_iris_router_profile_is_disabled_until_enabled() -> None:
    disabled = provider_registry_from_settings(Settings(iris_router_enabled=False))
    enabled = provider_registry_from_settings(Settings(iris_router_enabled=True))

    assert disabled.get("iris_router") is not None
    assert disabled.get("iris_router").enabled is False
    assert enabled.get("iris_router").enabled is True
    assert "route_recommendation" in enabled.get("iris_router").capabilities
    assert enabled.get("iris_router").tier == 1


def test_cloud_profile_follows_cloud_enabled_setting() -> None:
    registry = provider_registry_from_settings(Settings(cloud_enabled=False))

    cloud = registry.get("openrouter_frontier")

    assert cloud is not None
    assert cloud.enabled is False
    assert cloud.tier == 4
    assert cloud not in registry.enabled()


def test_readiness_requires_endpoint_and_model_not_just_host() -> None:
    registry = ProviderRegistry()
    profile = provider_registry_from_settings(Settings()).get("legacy_ollama")
    assert profile is not None
    registry.register(profile)

    profile.readiness.host_reachable = True
    assert profile.readiness.ready is False

    profile.readiness.endpoint_healthy = True
    assert profile.readiness.ready is False

    registry.mark_success("legacy_ollama", latency_ms=42)
    assert profile.readiness.ready is True
    assert profile.readiness.observed_latency_ms == 42
    assert profile.readiness.last_successful_inference_at is not None


def test_enabled_profiles_are_priority_ordered() -> None:
    registry = provider_registry_from_settings(Settings(iris_router_enabled=True))

    provider_ids = [profile.provider_id for profile in registry.enabled()]

    assert provider_ids.index("iris_router") < provider_ids.index("legacy_ollama")
    assert provider_ids.index("heavy_local") < provider_ids.index("openrouter_frontier")


def test_configured_profiles_can_add_named_provider() -> None:
    config = Settings(
        inference_provider_profiles_json="""[
          {
            "provider_id": "iris_chat",
            "kind": "ollama",
            "base_url": "http://iris:11434",
            "model": "qwen2.5:7b",
            "capabilities": ["chat", "summarization"],
            "locality": "iris",
            "tier": 2,
            "priority": 15,
            "enabled": true
          }
        ]"""
    )

    registry = provider_registry_from_settings(config)
    profile = registry.get("iris_chat")

    assert profile is not None
    assert profile.kind == "ollama"
    assert profile.locality == InferenceLocality.IRIS
    assert profile.tier == 2
    assert profile.priority == 15
    assert "summarization" in profile.capabilities


def test_configured_profiles_can_override_legacy_profile() -> None:
    config = Settings(
        inference_provider_profiles_json="""[
          {
            "provider_id": "heavy_local",
            "kind": "ollama",
            "base_url": "http://odin:11434",
            "model": "deepseek-r1:32b",
            "capabilities": ["chat", "reasoning", "coding"],
            "locality": "local_heavy",
            "tier": 3,
            "priority": 25,
            "enabled": true
          }
        ]"""
    )

    registry = provider_registry_from_settings(config)
    profile = registry.get("heavy_local")

    assert profile is not None
    assert profile.base_url == "http://odin:11434"
    assert profile.model == "deepseek-r1:32b"
    assert profile.priority == 25


def test_invalid_configured_profiles_fail_safe_to_defaults() -> None:
    malformed = provider_registry_from_settings(Settings(inference_provider_profiles_json="{not-json"))
    wrong_shape = provider_registry_from_settings(Settings(inference_provider_profiles_json='{"provider_id":"bad"}'))
    invalid_entry = provider_registry_from_settings(
        Settings(
            inference_provider_profiles_json="""[
              {
                "provider_id": "bad",
                "kind": "ollama",
                "base_url": "http://bad:11434",
                "model": "tiny",
                "capabilities": ["chat"],
                "locality": "unknown",
                "tier": 9
              }
            ]"""
        )
    )

    for registry in (malformed, wrong_shape, invalid_entry):
        assert registry.get("legacy_ollama") is not None
        assert registry.get("heavy_local") is not None
        assert registry.get("bad") is None
