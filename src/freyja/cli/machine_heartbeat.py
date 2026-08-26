from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys

import httpx

from freyja.freyja3_machines import Freyja3MachineHeartbeat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a Freyja 3 machine heartbeat.")
    parser.add_argument("--url", default=os.environ.get("FREYJA3_MACHINE_HEARTBEAT_URL", "http://127.0.0.1:8300/freyja3/machines/heartbeat"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--machine-id", default=os.environ.get("FREYJA3_MACHINE_ID", socket.gethostname().lower()))
    parser.add_argument("--role", default=os.environ.get("FREYJA3_MACHINE_ROLE", "worker-ingestion-monitoring"))
    parser.add_argument("--status", default="ok")
    parser.add_argument("--service", default="freyja3-agent-gateway")
    parser.add_argument("--commit-sha", default=os.environ.get("FREYJA3_COMMIT_SHA") or _git_commit())
    args = parser.parse_args(argv)

    heartbeat = Freyja3MachineHeartbeat(
        machine_id=args.machine_id,
        role=args.role,
        status=args.status,
        service=args.service,
        commit_sha=args.commit_sha,
        metadata={"hostname": socket.gethostname()},
    )
    headers = {"x-freyja-security-domain": "system"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(args.url, headers=headers, json=heartbeat.model_dump(mode="json"))
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"heartbeat failed: {exc}", file=sys.stderr)
        return 1
    print(response.text)
    return 0


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
