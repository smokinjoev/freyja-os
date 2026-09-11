#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


READ_ONLY_PROMPT = "Read-only smoke test: run pwd, git status --short, and identify the project type. Do not modify files."
WRITE_PROMPT = (
    "Tiny safe write smoke test: create or update tmp/cloyd-coder-smoke.txt with a timestamp, "
    "then run git status --short. Do not touch any other file."
)


def request(method: str, base_url: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_job(base_url: str, job_id: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = request("GET", base_url, f"/jobs/{job_id}")
        print(json.dumps({"id": job["id"], "status": job["status"], "changed_files": job.get("changed_files", [])}))
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(5)
    raise TimeoutError(f"job {job_id} did not finish within {timeout_seconds} seconds")


def run_job(base_url: str, prompt: str, timeout_seconds: int) -> dict:
    job = request("POST", base_url, "/jobs", {"project": "family-dashboard", "prompt": prompt})
    print(json.dumps({"started": job["id"], "project": job["project"], "cwd": job["cwd"]}))
    return wait_for_job(base_url, job["id"], timeout_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test cloyd-coder with the family-dashboard project.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--write", action="store_true", help="Run the tiny safe write job after read-only succeeds.")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    try:
        read_job = run_job(args.base_url, READ_ONLY_PROMPT, args.timeout)
        if read_job["status"] != "completed":
            print(json.dumps(read_job, indent=2))
            return 1
        if args.write:
            write_job = run_job(args.base_url, WRITE_PROMPT, args.timeout)
            print(json.dumps(write_job, indent=2))
            return 0 if write_job["status"] == "completed" else 1
        print(json.dumps(read_job, indent=2))
        return 0
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
