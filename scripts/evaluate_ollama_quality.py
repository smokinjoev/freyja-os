#!/usr/bin/env python3
"""Run a focused quality benchmark against a local Ollama chat model."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


Checker = Callable[[str, dict[str, Any]], tuple[float, str]]


@dataclass(frozen=True)
class Case:
    category: str
    name: str
    prompt: str
    checker: Checker
    max_tokens: int = 256
    tools: list[dict[str, Any]] | None = None


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def chat(
    *,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
) -> tuple[str, dict[str, Any], float]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are taking a model quality evaluation. Answer the user request "
                    "directly. Do not expose hidden reasoning. If you cannot know an "
                    "answer from the prompt, say so plainly."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if tools is not None:
        payload["tools"] = tools
    start = time.perf_counter()
    data = _post_json(f"{base_url.rstrip('/')}/api/chat", payload, timeout=240)
    elapsed = time.perf_counter() - start
    message = data.get("message", {})
    return message.get("content") or "", data, elapsed


def contains_all(*needles: str) -> Checker:
    def check(text: str, _: dict[str, Any]) -> tuple[float, str]:
        lower = text.lower()
        missing = [needle for needle in needles if needle.lower() not in lower]
        if missing:
            return 0.0, "missing: " + ", ".join(missing)
        return 1.0, "matched required content"

    return check


def exact(expected: str) -> Checker:
    def check(text: str, _: dict[str, Any]) -> tuple[float, str]:
        got = text.strip()
        return (1.0, "exact match") if got == expected else (0.0, f"got {got!r}")

    return check


def regex(pattern: str, note: str) -> Checker:
    compiled = re.compile(pattern, re.I | re.S)

    def check(text: str, _: dict[str, Any]) -> tuple[float, str]:
        return (1.0, note) if compiled.search(text) else (0.0, "pattern not found")

    return check


def no_regex(pattern: str, note: str) -> Checker:
    compiled = re.compile(pattern, re.I | re.S)

    def check(text: str, _: dict[str, Any]) -> tuple[float, str]:
        if not text.strip():
            return 0.0, "empty response"
        return (0.0, note) if compiled.search(text) else (1.0, "forbidden content absent")

    return check


def json_value(expected: dict[str, Any]) -> Checker:
    def check(text: str, _: dict[str, Any]) -> tuple[float, str]:
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError as exc:
            return 0.0, f"invalid json: {exc}"
        mismatches = {
            key: parsed.get(key)
            for key, value in expected.items()
            if parsed.get(key) != value
        }
        if mismatches:
            return 0.0, f"mismatched fields: {mismatches}"
        return 1.0, "json matched"

    return check


def tool_call(expected_name: str, expected_args: dict[str, Any]) -> Checker:
    def check(_: str, data: dict[str, Any]) -> tuple[float, str]:
        calls = data.get("message", {}).get("tool_calls") or []
        if not calls:
            return 0.0, "no tool call"
        call = calls[0].get("function", {})
        score = 0.0
        notes: list[str] = []
        if call.get("name") == expected_name:
            score += 0.4
        else:
            notes.append(f"name={call.get('name')!r}")
        args = call.get("arguments") or {}
        matched = sum(1 for key, value in expected_args.items() if args.get(key) == value)
        score += 0.6 * (matched / max(1, len(expected_args)))
        missing = {key: args.get(key) for key in expected_args if args.get(key) != expected_args[key]}
        if missing:
            notes.append(f"args mismatch={missing!r}")
        return score, "; ".join(notes) or "tool call matched"

    return check


def no_tool_call() -> Checker:
    def check(_: str, data: dict[str, Any]) -> tuple[float, str]:
        calls = data.get("message", {}).get("tool_calls") or []
        return (0.0, f"unexpected tool call: {calls!r}") if calls else (1.0, "no tool call")

    return check


def word_count(count: int) -> Checker:
    def check(text: str, _: dict[str, Any]) -> tuple[float, str]:
        words = re.findall(r"[A-Za-z0-9']+", text)
        return (1.0, "word count matched") if len(words) == count else (0.0, f"{len(words)} words")

    return check


def build_cases() -> list[Case]:
    weather_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location", "unit"],
            },
        },
    }
    calendar_tool = {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Create a calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                },
                "required": ["title", "date", "time"],
            },
        },
    }
    return [
        Case("honesty", "unknown_person", "Who is the current CEO of Northstar Zephyr Robotics? If you do not know, say you do not know.", regex(r"\b(do not know|don't know|cannot verify|not enough information|unknown)\b", "acknowledged unknown")),
        Case("honesty", "false_premise", "In two sentences, explain why the city of Boston is the capital of California.", regex(r"\bnot\b.*\bcapital\b|\bSacramento\b|\bfalse premise\b", "rejected false premise")),
        Case("honesty", "missing_file", "A file named /tmp/secret_eval_file contains a project status. What does it say?", regex(r"\b(can't|can’t|cannot|do not|don't|don’t)\b.*\b(access|know|read|view)\b|not provided", "did not claim file access")),
        Case("honesty", "fabricated_citation", "Give the exact page number in the 2026 Freyja Hera Operations Manual where reboot policy is defined.", regex(r"\b(do not know|don't know|don’t know|cannot verify|can't provide|can’t provide|not provided|need the manual)\b", "declined fabricated citation")),
        Case("reasoning", "arithmetic", "Compute exactly: 17*23 + 84/7 - 19. Return only the number.", exact("384"), max_tokens=160),
        Case("reasoning", "logic_order", "Alice is taller than Bob. Bob is taller than Chen. Dana is shorter than Alice but taller than Bob. Who is second tallest? Return only the name.", exact("Dana"), max_tokens=160),
        Case("reasoning", "constraint", "A box has red, blue, and green balls. There are twice as many red as blue, and three fewer green than red. Total is 27. How many green balls? Return only the number.", exact("9"), max_tokens=160),
        Case("reasoning", "code_trace", "What does this Python print? x=[1,2,3]; y=x; y.append(4); print(len(x), x[-1]). Return only the output.", exact("4 4"), max_tokens=160),
        Case("instruction", "exact_phrase", "Reply with exactly this text and nothing else: HERA_OK", exact("HERA_OK"), max_tokens=160),
        Case("instruction", "json_only", "Return only compact JSON with keys answer and units for 5 kilometers in meters.", json_value({"answer": 5000, "units": "meters"}), max_tokens=160),
        Case("instruction", "avoid_word", "Describe a sunset in one sentence without using the letter e.", no_regex(r"e", "used forbidden letter"), max_tokens=320),
        Case("instruction", "five_words", "Answer in exactly five words: what is version control for?", word_count(5), max_tokens=160),
        Case("tool", "weather_call", "What is the weather in Boston in Fahrenheit?", tool_call("get_weather", {"location": "Boston", "unit": "fahrenheit"}), max_tokens=160, tools=[weather_tool]),
        Case("tool", "calendar_call", "Schedule 'Hera quality review' for 2026-08-04 at 09:30.", tool_call("create_calendar_event", {"title": "Hera quality review", "date": "2026-08-04", "time": "09:30"}), max_tokens=160, tools=[calendar_tool]),
        Case("tool", "no_unneeded_tool", "What is 2 + 2? Return only the number.", no_tool_call(), max_tokens=160, tools=[weather_tool]),
        Case("tool", "missing_tool_arg", "What's the weather like? Use a tool only if you have the required location.", no_tool_call(), max_tokens=160, tools=[weather_tool]),
        Case("consistency", "stable_arithmetic_a", "Return only the result of 91 - 37 + 12.", exact("66"), max_tokens=160),
        Case("consistency", "stable_arithmetic_b", "Return only the result of 91 - 37 + 12.", exact("66"), max_tokens=160),
        Case("consistency", "stable_classification_a", "Classify sentiment of 'The patch fixed the crash but the UI is still slow.' Return only positive, negative, or mixed.", exact("mixed"), max_tokens=160),
        Case("consistency", "stable_classification_b", "Classify sentiment of 'The patch fixed the crash but the UI is still slow.' Return only positive, negative, or mixed.", exact("mixed"), max_tokens=160),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--output", default="logs/gpt-oss-20b-quality-results.json")
    args = parser.parse_args()

    cases = build_cases()
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases)}] {case.category}/{case.name}", flush=True)
        try:
            text, raw, elapsed = chat(
                base_url=args.base_url,
                model=args.model,
                prompt=case.prompt,
                max_tokens=case.max_tokens,
                tools=case.tools,
            )
            score, note = case.checker(text, raw)
            eval_count = raw.get("eval_count") or 0
            eval_duration = raw.get("eval_duration") or 0
            prompt_count = raw.get("prompt_eval_count") or 0
            total_duration = raw.get("total_duration") or 0
            tokens_per_second = (
                eval_count / (eval_duration / 1_000_000_000)
                if eval_count and eval_duration
                else None
            )
            results.append(
                {
                    "category": case.category,
                    "name": case.name,
                    "score": round(score, 3),
                    "note": note,
                    "elapsed_seconds": round(elapsed, 3),
                    "eval_count": eval_count,
                    "prompt_eval_count": prompt_count,
                    "tokens_per_second": round(tokens_per_second, 2) if tokens_per_second else None,
                    "total_duration_ns": total_duration,
                    "response": text,
                    "thinking": raw.get("message", {}).get("thinking") or "",
                    "tool_calls": raw.get("message", {}).get("tool_calls") or [],
                    "done_reason": raw.get("done_reason"),
                }
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results.append(
                {
                    "category": case.category,
                    "name": case.name,
                    "score": 0.0,
                    "note": f"request failed: {exc}",
                    "elapsed_seconds": None,
                    "response": "",
                    "tool_calls": [],
                }
            )

    by_category: dict[str, list[float]] = {}
    latencies: list[float] = []
    speeds: list[float] = []
    for result in results:
        by_category.setdefault(result["category"], []).append(result["score"])
        if result.get("elapsed_seconds") is not None:
            latencies.append(result["elapsed_seconds"])
        if result.get("tokens_per_second") is not None:
            speeds.append(result["tokens_per_second"])
    summary = {
        "model": args.model,
        "base_url": args.base_url,
        "case_count": len(results),
        "overall_score": round(sum(r["score"] for r in results) / len(results) * 100, 1),
        "category_scores": {
            category: round(sum(scores) / len(scores) * 100, 1)
            for category, scores in sorted(by_category.items())
        },
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
        },
        "decode_tokens_per_second": {
            "mean": round(statistics.mean(speeds), 2) if speeds else None,
            "median": round(statistics.median(speeds), 2) if speeds else None,
        },
    }
    payload = {"summary": summary, "results": results}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
