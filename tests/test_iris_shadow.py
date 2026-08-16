from certification.iris_shadow import IrisComparison, provider_target, summarize
from freyja.atlas_app import _parse_route_request


def _comparison(**overrides):
    base = dict(
        case="case",
        category="core",
        difficulty="smoke",
        director_provider="ollama",
        director_model="qwen2.5:7b",
        director_target="iris",
        final_provider="ollama",
        final_model="qwen2.5:7b",
        final_target="iris",
        response_ok=True,
        iris_ok=True,
        iris_tier=2,
        iris_target="iris",
        iris_task="chat",
        iris_confidence=0.9,
        iris_latency_ms=120,
        iris_error=None,
        agrees_with_director=True,
        agrees_with_final=True,
    )
    base.update(overrides)
    return IrisComparison(**base)


def test_provider_target_mapping() -> None:
    assert provider_target("ollama") == "iris"
    assert provider_target("local_reasoning") == "local_heavy"
    assert provider_target("openrouter") == "cloud"
    assert provider_target("deterministic") == "deterministic"
    assert provider_target("unknown") is None


def test_shadow_summary_reports_agreement_and_latency() -> None:
    results = [
        _comparison(),
        _comparison(
            case="heavy",
            director_provider="local_reasoning",
            director_target="local_heavy",
            final_provider="local_reasoning",
            final_target="local_heavy",
            iris_tier=3,
            iris_target="local_heavy",
            iris_latency_ms=200,
        ),
        _comparison(
            case="disagree",
            iris_target="cloud",
            agrees_with_director=False,
            agrees_with_final=False,
            iris_latency_ms=160,
        ),
    ]

    summary = summarize(results)

    assert summary["cases"] == 3
    assert summary["iris_valid_rate"] == 1.0
    assert summary["agreement_with_director_rate"] == 2 / 3
    assert summary["agreement_with_final_provider_rate"] == 2 / 3
    assert summary["iris_latency_ms_mean"] == 160.0
    assert summary["iris_latency_ms_p95"] == 200.0


def test_parse_route_request_accepts_valid_request() -> None:
    payload = _parse_route_request(b'{"prompt":"turn off the kitchen lights","tools_required":true}')
    assert payload is not None
    assert payload["prompt"] == "turn off the kitchen lights"
    assert payload["tools_required"] is True


def test_parse_route_request_rejects_invalid_or_empty_body() -> None:
    assert _parse_route_request(b"not-json") is None
    assert _parse_route_request(b'{"prompt":""}') is None
