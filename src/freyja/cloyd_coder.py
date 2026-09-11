from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from freyja.config import settings
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.opencode_runtime import _opencode_send, _opencode_stop


PROJECTS = {
    "family-dashboard": "/home/joe/cloyd-services",
    "freyja-atlas": "/home/joe/freyja-os",
    "nextcloud": "/home/joe/nextcloud",
    "paperless": "/home/joe/paperless-ngx",
}

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class JobCreateRequest(BaseModel):
    project: str
    prompt: str = Field(min_length=1)


class Job(BaseModel):
    id: str
    project: str
    cwd: str
    prompt: str
    status: str
    created_at: str
    updated_at: str
    transcript_log: str = ""
    changed_files: list[str] = Field(default_factory=list)
    verification_output: str = ""
    opencode_alias: str
    opencode_session: str | None = None
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_dir() -> Path:
    base = Path(os.environ.get("CLOYD_CODER_STATE_DIR", Path.home() / ".local" / "state" / "freyja" / "cloyd-coder"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def jobs_dir() -> Path:
    path = state_dir() / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def load_job(job_id: str) -> Job:
    path = job_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="job not found")
    return Job.model_validate_json(path.read_text(encoding="utf-8"))


def save_job(job: Job) -> None:
    job.updated_at = utc_now()
    path = job_path(job.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(job.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def git_files(cwd: str) -> set[str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    files: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.add(path)
    return files


def append_log(job: Job, event: str, payload: Any) -> None:
    entry = {"time": utc_now(), "event": event, "payload": payload}
    job.transcript_log = f"{job.transcript_log}{json.dumps(entry, sort_keys=True)}\n"


def run_job(job_id: str, before_files: set[str] | None) -> None:
    job = load_job(job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    append_log(job, "job_started", {"project": job.project, "cwd": job.cwd})
    save_job(job)
    try:
        result = _run_opencode_send(job)
        job = load_job(job_id)
        if job.status == "cancelled":
            append_log(job, "opencode_result_after_cancel", result)
            save_job(job)
            return
        append_log(job, "opencode_result", result)
        job.opencode_session = result.get("session") if isinstance(result, dict) else None
        if isinstance(result, dict) and result.get("ok") is False:
            job.status = "failed"
            job.error = str(result.get("error") or result)
        else:
            job.status = "completed"
    except Exception as exc:
        job = load_job(job_id)
        job.status = "failed"
        job.error = str(exc)
        append_log(job, "job_error", {"error": str(exc)})
    after_files = git_files(job.cwd)
    if before_files is not None and after_files is not None:
        job.changed_files = sorted(after_files - before_files)
    elif after_files is not None:
        job.changed_files = sorted(after_files)
    save_job(job)


def _run_opencode_send(job: Job) -> dict[str, Any]:
    import asyncio

    return asyncio.run(
        _opencode_send(
            ToolExecutionRequest(
                tool_name="opencode_send",
                actor="cloyd-coder",
                arguments={
                    "alias": job.opencode_alias,
                    "directory": job.cwd,
                    "host": "atlas",
                    "prompt": job.prompt,
                },
                metadata={"director_authorized": True},
            )
        )
    )


app = FastAPI(title="cloyd-coder", version="0.1.0")


@app.post("/jobs", response_model=Job)
def create_job(request: JobCreateRequest) -> Job:
    cwd = PROJECTS.get(request.project)
    if cwd is None:
        raise HTTPException(status_code=400, detail={"error": "project is not allowlisted", "allowed_projects": sorted(PROJECTS)})
    job_id = uuid.uuid4().hex
    now = utc_now()
    job = Job(
        id=job_id,
        project=request.project,
        cwd=cwd,
        prompt=request.prompt,
        status="queued",
        created_at=now,
        updated_at=now,
        opencode_alias=f"cloyd-coder-{job_id}",
    )
    append_log(job, "job_queued", {"project": request.project, "cwd": cwd})
    save_job(job)
    before_files = git_files(cwd)
    thread = threading.Thread(target=run_job, args=(job_id, before_files), name=f"cloyd-coder-{job_id}", daemon=True)
    thread.start()
    return load_job(job_id)


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    return load_job(job_id)


@app.get("/jobs/{job_id}/log")
def get_job_log(job_id: str) -> dict[str, str]:
    job = load_job(job_id)
    return {"id": job.id, "log": job.transcript_log}


@app.post("/jobs/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: str) -> Job:
    import asyncio

    job = load_job(job_id)
    if job.status in TERMINAL_STATUSES:
        return job
    job.status = "cancelled"
    append_log(job, "cancel_requested", {"status": "requested"})
    save_job(job)
    result = asyncio.run(
        _opencode_stop(
            ToolExecutionRequest(
                tool_name="opencode_stop",
                actor="cloyd-coder",
                arguments={"alias": job.opencode_alias},
                metadata={"director_authorized": True},
            )
        )
    )
    job = load_job(job_id)
    append_log(job, "cancel_requested", result)
    if not result.get("ok"):
        job.error = str(result.get("error") or result)
    save_job(job)
    return job


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas-local coding-agent bridge for OpenWebUI/Cloyd.")
    parser.add_argument("--host", default=os.environ.get("CLOYD_CODER_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("CLOYD_CODER_PORT", "8766")), type=int)
    args = parser.parse_args()
    uvicorn.run("freyja.cloyd_coder:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
