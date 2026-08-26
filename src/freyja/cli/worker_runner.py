from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from typing import Any

import httpx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claim and run one Freyja 3 worker job.")
    parser.add_argument("--base-url", default=os.environ.get("FREYJA3_WORKER_BASE_URL", "http://127.0.0.1:8300"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--machine-id", default=os.environ.get("FREYJA3_MACHINE_ID", socket.gethostname().lower()))
    parser.add_argument("--worker-class", default=os.environ.get("FREYJA3_WORKER_CLASS", "monitoring"))
    args = parser.parse_args(argv)

    headers = {"x-freyja-security-domain": "system"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    base_url = args.base_url.rstrip("/")

    try:
        with httpx.Client(timeout=15.0) as client:
            claim = client.post(
                f"{base_url}/freyja3/workers/jobs/claim",
                headers=headers,
                params={"machine_id": args.machine_id, "worker_class": args.worker_class},
            )
            claim.raise_for_status()
            job = claim.json().get("job")
            if job is None:
                print('{"ok": true, "job": null}')
                return 0
            completion = _run_job(job, machine_id=args.machine_id)
            complete = client.post(
                f"{base_url}/freyja3/workers/jobs/{job['job_id']}/complete",
                headers=headers,
                params={"machine_id": args.machine_id},
                json=completion,
            )
            complete.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"worker failed: {exc}", file=sys.stderr)
        return 1
    print(complete.text)
    return 0


def _run_job(job: dict[str, Any], *, machine_id: str) -> dict[str, Any]:
    worker_class = str(job.get("worker_class") or "")
    if worker_class == "monitoring":
        return {
            "status": "completed",
            "result": {
                "machine_id": machine_id,
                "worker_class": worker_class,
                "objective": job.get("objective"),
                "hostname": socket.gethostname(),
                "commit_sha": _git_commit(),
            },
        }
    return {
        "status": "failed",
        "result": {"machine_id": machine_id, "worker_class": worker_class},
        "error": f"worker class {worker_class!r} is not implemented by this runner",
    }


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
