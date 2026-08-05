from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


HELPER_PATH = Path(__file__).with_name("apple_eventkit.swift")


def run_eventkit(
    operation: str,
    arguments: dict[str, Any] | None = None,
    *,
    helper_path: Path = HELPER_PATH,
    request_access: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    if not helper_path.is_file():
        raise RuntimeError("Apple Calendar helper is missing")
    command = ["/usr/bin/swift", str(helper_path), operation]
    if request_access:
        command.append("--request-access")
    try:
        result = subprocess.run(
            command,
            input=json.dumps(arguments or {}),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Apple Calendar helper could not be run") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "EventKit operation failed"
        raise RuntimeError(detail)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Apple Calendar helper returned invalid data") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Apple Calendar helper returned an invalid object")
    return payload
