#!/usr/bin/env python3
"""Small client for Hera's FLM OpenAI-compatible GPT-OSS NPU endpoint."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def ask(prompt: str, *, base_url: str, model: str, max_tokens: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Answer directly and concisely. Do not expose hidden reasoning."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.load(response)
    choice = body.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = message.get("content") or ""
    if content.strip():
        return content.strip()
    # FLM may put the answer in reasoning_content when the token budget is too small.
    reasoning = message.get("reasoning_content") or ""
    return reasoning.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--base-url", default=os.getenv("FLM_BASE_URL", "http://127.0.0.1:5000"))
    parser.add_argument("--model", default=os.getenv("FLM_MODEL", "gpt-oss:20b"))
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()
    try:
        print(ask(args.prompt, base_url=args.base_url, model=args.model, max_tokens=args.max_tokens))
    except Exception as exc:
        print(f"FLM GPT-OSS unavailable: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
