from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FILTER_PATH = REPO_ROOT / "ops" / "openwebui" / "open_webui_performance_filter.py"


def _load_filter():
    spec = importlib.util.spec_from_file_location("open_webui_performance_filter", FILTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Filter()


def test_performance_filter_prefers_reported_completion_tokens() -> None:
    filter_ = _load_filter()
    body = {
        "model": "qwen3.8:27b",
        "messages": [
            {
                "id": "msg-1",
                "role": "assistant",
                "content": "hello from Vulcan",
                "usage": {"completion_tokens": 12, "total_duration": 3_000_000_000},
            }
        ],
    }

    result = filter_.outlet(body)

    content = result["messages"][0]["content"]
    assert "4.00 tokens/sec" in content
    assert "12 output tokens" in content
    assert "generation 3.00s" in content
    assert "estimated output tokens" not in content


def test_performance_filter_labels_estimated_tokens_and_is_idempotent() -> None:
    filter_ = _load_filter()
    body = {
        "model": "qwen3.8:27b",
        "messages": [
            {
                "id": "msg-1",
                "role": "assistant",
                "content": "one two three four",
                "usage": {"duration": 2},
            }
        ],
    }

    first = filter_.outlet(body)
    second = filter_.outlet(first)

    content = second["messages"][0]["content"]
    assert "estimated output tokens" in content
    assert content.count("Perf:") == 1


def test_performance_filter_applies_to_agent_gateway_models() -> None:
    filter_ = _load_filter()
    body = {
        "model": "agent/freyja",
        "messages": [{"id": "msg-1", "role": "assistant", "content": "hello", "usage": {}}],
    }

    result = filter_.outlet(body)

    assert "Perf:" in result["messages"][0]["content"]


def test_performance_filter_adds_metrics_when_visible_content_is_empty() -> None:
    filter_ = _load_filter()
    body = {
        "model": "qwen3.8:27b",
        "messages": [
            {
                "id": "msg-1",
                "role": "assistant",
                "content": "",
                "output": [
                    {
                        "type": "reasoning",
                        "content": [{"type": "output_text", "text": "internal reasoning text"}],
                    }
                ],
                "usage": {"eval_count": 20, "eval_duration": 4_000_000_000},
            }
        ],
    }

    result = filter_.outlet(body)

    content = result["messages"][0]["content"]
    assert "internal reasoning text" not in content
    assert "5.00 tokens/sec" in content
    assert "20 output tokens" in content


def test_performance_filter_appends_footer_to_final_stream_chunk() -> None:
    filter_ = _load_filter()

    first = filter_.stream(
        {
            "id": "chatcmpl-test",
            "choices": [{"index": 0, "delta": {"content": "perf"}, "finish_reason": None}],
        }
    )
    final = filter_.stream(
        {
            "id": "chatcmpl-test",
            "usage": {"completion_tokens": 2, "eval_duration": 1_000_000_000},
            "choices": [{"index": 0, "delta": {"content": "-ok"}, "finish_reason": "stop"}],
        }
    )

    assert first["choices"][0]["delta"]["content"] == "perf"
    content = final["choices"][0]["delta"]["content"]
    assert "-ok\n\nPerf:" in content
    assert "2 output tokens" in content
    assert "2.00 tokens/sec" in content
