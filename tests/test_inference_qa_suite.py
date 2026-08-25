from __future__ import annotations

import pytest

from certification.runner import LocalReasoningCertificationProvider, load_suite


def test_freyja_qa_100_suite_has_100_deterministic_cases() -> None:
    suite = load_suite("inference/freyja_qa_100")

    assert suite.name == "freyja-qa-100"
    assert len(suite.cases) == 100
    assert suite.passing_score == 0.95
    assert {case.category for case in suite.cases} == {"inference"}
    assert all(case.expected_keywords for case in suite.cases)
    assert all(case.max_score == 1.0 for case in suite.cases)


def test_freyja_qa_100_category_balance() -> None:
    suite = load_suite("inference/freyja_qa_100")

    prefixes = {}
    for case in suite.cases:
        prefix = case.name.rsplit("-", 1)[0]
        prefixes[prefix] = prefixes.get(prefix, 0) + 1

    assert prefixes == {
        "arithmetic": 20,
        "instruction": 20,
        "knowledge": 20,
        "language": 20,
        "logic": 20,
    }


def test_iterative_coding_suite_uses_coding_route() -> None:
    suite = load_suite("inference/freyja_iterative_coding")

    assert suite.name == "freyja-iterative-coding"
    assert suite.category == "coding"
    assert suite.passing_score == 0.90
    assert len(suite.cases) >= 10
    assert all(case.route_request.get("provider") == "auto" for case in suite.cases)
    assert all(case.route_request.get("task_type") == "coding" for case in suite.cases)
    assert all(case.expects.get("provider") == "local_reasoning" for case in suite.cases)
    assert all(case.expects.get("provider_profile_id") == "heavy_local" for case in suite.cases)
    assert all(case.expected_keywords for case in suite.cases)
    assert all("cannot" in {word.lower() for word in case.forbidden_keywords} for case in suite.cases)


def test_iterative_coding_suite_uses_behavior_for_style_flexible_python_repairs() -> None:
    suite = load_suite("inference/freyja_iterative_coding")
    cases = {case.name: case for case in suite.cases}

    dedupe = cases["python-fix-deduplicate-stable"]
    clamp = cases["python-fix-boundary-validation"]

    assert dedupe.expected_keywords == ("def unique_stable",)
    assert "python_behavior" in dedupe.expects
    assert clamp.expected_keywords == ("def clamp",)
    assert "python_behavior" in clamp.expects


@pytest.mark.asyncio
async def test_local_reasoning_certification_provider_calls_heavy_model_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake_chat(self, prompt, model=None, output_tokens=None, **kwargs):
        calls.append({"base_url": self.base_url, "prompt": prompt, "model": model, "output_tokens": output_tokens})
        return {
            "model": model,
            "message": {"content": "45"},
            "prompt_eval_count": 10,
            "eval_count": 2,
            "latency_ms": 250,
            "observability": {"generation_tokens_per_second": 8.0, "latency_ms": 250},
        }

    monkeypatch.setattr("freyja.ollama_client.OllamaClient.chat", fake_chat)

    provider = LocalReasoningCertificationProvider(
        model="gpt-oss-freyja:20b-analysis-prefill",
        base_url="http://vulcan.test:11434",
    )
    execution = await provider.complete(load_suite("inference/freyja_qa_100").cases[0])

    assert execution.response == "45"
    assert calls == [
        {
            "base_url": "http://vulcan.test:11434",
            "prompt": "Answer with only the number: 17 + 28.",
            "model": "gpt-oss-freyja:20b-analysis-prefill",
            "output_tokens": 512,
        }
    ]
    assert execution.context.provider_selected == "local_reasoning"
    assert execution.context.provider_profile_id == "heavy_local"
    assert execution.context.rev2_evidence["direct_model_inference"] is True
    assert execution.context.rev2_evidence["generation_tokens_per_second"] == 8.0
