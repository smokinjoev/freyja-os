#!/usr/bin/env python3
"""Verify the public, no-secret Freyja operational baseline."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Check:
    name: str
    url: str
    expected_statuses: tuple[int, ...]
    status: int | None
    ok: bool
    detail: str


TARGETS = (
    ("LibreChat", "http://100.119.235.114:3080/", (200,)),
    ("Open WebUI", "http://100.119.235.114:3001/", (200,)),
    ("LobeHub", "http://100.119.235.114:3210/", (200,)),
    ("Family portal", "http://100.119.235.114:9091/", (200,)),
    ("Director", "http://100.94.80.21:8512/health", (200,)),
    ("Nexus model API", "http://100.94.80.21:3939/v1/models", (401,)),
    ("Vulcan Ollama", "http://100.94.80.21:11434/api/tags", (200,)),
    ("Iris Core", "http://100.115.228.56:8510/health", (200,)),
    ("Agent Smith status", "http://100.115.228.56:8000/agent-runs/api/status", (200,)),
    ("Agent Smith runtime", "http://100.115.228.56:8000/agent-runs/api/runtime/health", (200,)),
)


def check(name: str, url: str, expected_statuses: tuple[int, ...]) -> Check:
    request = Request(url, headers={"User-Agent": "FreyjaLiveReadiness/1.0"})
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read(4096)
    except HTTPError as error:
        status = error.code
        body = error.read(4096)
    except URLError as error:
        return Check(name, url, expected_statuses, None, False, f"connection error: {error.reason}")

    if status not in expected_statuses:
        return Check(name, url, expected_statuses, status, False, "unexpected HTTP status")

    if name in {"Director", "Iris Core"}:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Check(name, url, expected_statuses, status, False, "health response was not JSON")
        if payload.get("status") not in {"healthy", "ok"} and payload.get("ok") is not True:
            return Check(name, url, expected_statuses, status, False, "health response did not report healthy")

    detail = "authorized health response" if status == 200 else "expected protected response"
    return Check(name, url, expected_statuses, status, True, detail)


def main() -> int:
    results = [check(*target) for target in TARGETS]
    report = {"ok": all(result.ok for result in results), "checks": [asdict(result) for result in results]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
