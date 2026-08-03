#!/usr/bin/env python3
"""Small live coding-quality benchmark for Hera's local GPT-OSS model."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable


Checker = Callable[[str, dict[str, Any]], tuple[float, str]]


def _post_json(url: str, payload: dict[str, Any], timeout: int = 240) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _chat(base_url: str, model: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], float]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 768,
        },
    }
    if tools:
        payload["tools"] = tools
    start = time.perf_counter()
    data = _post_json(f"{base_url.rstrip('/')}/api/chat", payload)
    return data, time.perf_counter() - start


def _contains_all(*patterns: str) -> Checker:
    compiled = [re.compile(pattern, re.I | re.S) for pattern in patterns]

    def check(content: str, _: dict[str, Any]) -> tuple[float, str]:
        missing = [pattern.pattern for pattern in compiled if not pattern.search(content)]
        if missing:
            return 0.0, "missing: " + ", ".join(missing)
        return 1.0, "matched expected coding signals"

    return check


def _tool_call_check(content: str, data: dict[str, Any]) -> tuple[float, str]:
    calls = data.get("message", {}).get("tool_calls") or []
    if not calls:
        return 0.0, "no native tool call"
    fn = calls[0].get("function", {})
    args = fn.get("arguments") or {}
    score = 0.0
    notes: list[str] = []
    if fn.get("name") == "repository_status":
        score += 0.5
    else:
        notes.append(f"name={fn.get('name')!r}")
    if args == {}:
        score += 0.5
    else:
        notes.append(f"args={args!r}")
    return score, "; ".join(notes) or "native tool call matched"


def _cases() -> list[dict[str, Any]]:
    system = {
        "role": "system",
        "content": (
            "You are evaluating Freyja code. Answer directly. Do not expose hidden reasoning. "
            "When asked for code, provide a concise patch sketch only; do not claim it was applied."
        ),
    }
    return [
        {
            "name": "code_trace_weekday",
            "category": "code_tracing",
            "messages": [
                system,
                {
                    "role": "user",
                    "content": (
                        "Trace this Freyja helper. If today is Monday 2026-08-03 and target_weekday is 0, "
                        "what date is returned and why?\n\n"
                        "def _weekday_from_today(target_weekday, today):\n"
                        "    delta = (target_weekday - today.weekday()) % 7\n"
                        "    if delta == 0:\n"
                        "        delta = 7\n"
                        "    return today + timedelta(days=delta)\n\n"
                        "Answer in one sentence."
                    ),
                },
            ],
            "checker": _contains_all(r"2026\D+08\D+10", "7"),
        },
        {
            "name": "bug_diagnosis_schema_enum",
            "category": "bug_diagnosis",
            "messages": [
                system,
                {
                    "role": "user",
                    "content": (
                        "Diagnose the bug in this Freyja-style tool validation snippet and propose the minimal fix:\n\n"
                        "def validate(arguments, schema):\n"
                        "    errors = []\n"
                        "    for key, value in arguments.items():\n"
                        "        prop = schema['properties'].get(key)\n"
                        "        if prop is None:\n"
                        "            errors.append(f'Unknown argument: {key}')\n"
                        "            continue\n"
                        "        if prop.get('type') == 'string' and not isinstance(value, str):\n"
                        "            errors.append(f'{key} must be string')\n"
                        "    return errors\n\n"
                        "The schema may contain enum values such as ['celsius', 'fahrenheit']."
                    ),
                },
            ],
            "checker": _contains_all("enum", "reject|invalid|must be one", "fahrenheit"),
        },
        {
            "name": "patch_planning_ollama_retry",
            "category": "patch_planning",
            "messages": [
                system,
                {
                    "role": "user",
                    "content": (
                        "Draft a concise patch plan for Freyja's Ollama provider. Requirements: strip message.thinking, "
                        "retry once when message.content is empty and done_reason is length, use at least 512 generated "
                        "tokens by default, and log observability without secrets or chain-of-thought."
                    ),
                },
            ],
            "checker": _contains_all("thinking", r"retry.*once|once.*retry", "512", "observability|latency|tokens"),
        },
        {
            "name": "tool_call_repository_status",
            "category": "tool_call_generation",
            "messages": [
                system,
                {"role": "user", "content": "Use the available tool to inspect repository status."},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "repository_status",
                        "description": "Return git status for the Freyja repository.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "checker": _tool_call_check,
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--output", default="logs/gpt-oss-20b-coding-benchmark.json")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for case in _cases():
        print(f"running {case['category']}/{case['name']}", flush=True)
        try:
            data, elapsed = _chat(args.base_url, args.model, case["messages"], tools=case.get("tools"))
            content = data.get("message", {}).get("content") or ""
            score, note = case["checker"](content, data)
            eval_count = data.get("eval_count") or 0
            eval_duration = data.get("eval_duration") or 0
            tps = eval_count / (eval_duration / 1_000_000_000) if eval_count and eval_duration else None
            results.append(
                {
                    "category": case["category"],
                    "name": case["name"],
                    "score": round(score, 3),
                    "note": note,
                    "elapsed_seconds": round(elapsed, 3),
                    "generated_tokens": data.get("eval_count"),
                    "prompt_tokens": data.get("prompt_eval_count"),
                    "generation_tokens_per_second": round(tps, 2) if tps else None,
                    "done_reason": data.get("done_reason"),
                    "content": content,
                    "tool_calls": data.get("message", {}).get("tool_calls") or [],
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "category": case["category"],
                    "name": case["name"],
                    "score": 0.0,
                    "note": f"request failed: {exc}",
                    "elapsed_seconds": None,
                    "content": "",
                    "tool_calls": [],
                }
            )

    scores = [result["score"] for result in results]
    latencies = [result["elapsed_seconds"] for result in results if result["elapsed_seconds"] is not None]
    summary = {
        "model": args.model,
        "overall_score": round(sum(scores) / len(scores) * 100, 1),
        "case_count": len(results),
        "latency_seconds_mean": round(statistics.mean(latencies), 3) if latencies else None,
        "latency_seconds_max": round(max(latencies), 3) if latencies else None,
    }
    payload = {"summary": summary, "results": results}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
