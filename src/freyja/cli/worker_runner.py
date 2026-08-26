from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import httpx

from freyja.workers import ExternalWorkerClass, WorkerObservation, WorkerTrustLevel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claim and run one Freyja 3 worker job.")
    parser.add_argument("--base-url", default=os.environ.get("FREYJA3_WORKER_BASE_URL", "http://127.0.0.1:8300"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--machine-id", default=os.environ.get("FREYJA3_MACHINE_ID", socket.gethostname().lower()))
    parser.add_argument("--worker-class", default=os.environ.get("FREYJA3_WORKER_CLASS", "monitoring"))
    parser.add_argument("--allowed-root", action="append", default=_allowed_roots_from_env())
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
            completion = _run_job(job, machine_id=args.machine_id, allowed_roots=args.allowed_root)
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


def _run_job(job: dict[str, Any], *, machine_id: str, allowed_roots: list[str] | None = None) -> dict[str, Any]:
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
    if worker_class == ExternalWorkerClass.DOCUMENT_INGESTION.value:
        return _run_document_ingestion(job, machine_id=machine_id, allowed_roots=allowed_roots or [])
    return {
        "status": "failed",
        "result": {"machine_id": machine_id, "worker_class": worker_class},
        "error": f"worker class {worker_class!r} is not implemented by this runner",
    }


def _run_document_ingestion(job: dict[str, Any], *, machine_id: str, allowed_roots: list[str]) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    source = str(payload.get("source") or payload.get("path") or "payload:text")
    try:
        text = _ingestion_text(payload, allowed_roots=allowed_roots)
    except ValueError as exc:
        return {
            "status": "failed",
            "result": {"machine_id": machine_id, "worker_class": ExternalWorkerClass.DOCUMENT_INGESTION.value, "source": source},
            "error": str(exc),
        }
    normalized = " ".join(text.split())
    words = normalized.split()
    summary = normalized[:280] if normalized else "No extractable text."
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.DOCUMENT_INGESTION,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source=source,
        summary=summary,
        facts=[
            {"claim": f"document contains approximately {len(words)} words", "confidence": "high"},
            {"claim": f"document contains approximately {len(text)} characters", "confidence": "high"},
        ],
        citations=[{"label": "text-prefix", "excerpt": normalized[:160]}] if normalized else [],
        uncertainty=None if normalized else "No text content was supplied or extracted.",
    )
    return {
        "status": "completed",
        "result": {
            "machine_id": machine_id,
            "worker_class": ExternalWorkerClass.DOCUMENT_INGESTION.value,
            "observation": observation.model_dump(mode="json"),
        },
    }


def _ingestion_text(payload: dict[str, Any], *, allowed_roots: list[str]) -> str:
    if isinstance(payload.get("text"), str):
        return payload["text"][:20000]
    path_value = payload.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("document_ingestion requires payload.text or payload.path")
    path = Path(path_value).expanduser().resolve()
    roots = [Path(root).expanduser().resolve() for root in allowed_roots if root]
    if not roots or not any(path == root or root in path.parents for root in roots):
        raise ValueError("payload.path is outside configured ingestion roots")
    if not path.is_file():
        raise ValueError("payload.path is not a readable file")
    return path.read_text(errors="replace")[:20000]


def _allowed_roots_from_env() -> list[str]:
    value = os.environ.get("FREYJA3_WORKER_ALLOWED_ROOTS", "")
    return [item for item in value.split(":") if item]


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
