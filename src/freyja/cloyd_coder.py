from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import uuid
import base64
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import urllib.error
import urllib.parse
import urllib.request


PROJECTS = {
    "family-dashboard": "/home/joe/cloyd-services",
    "freyja-atlas": "/home/joe/freyja-os",
    "nextcloud": "/home/joe/nextcloud",
    "paperless": "/home/joe/paperless-ngx",
}

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
MODEL = {"providerID": "vulcan-nexus", "modelID": "@preset/freyja-coder"}


class JobNotFoundError(Exception):
    pass


class BadRequestError(Exception):
    pass


@dataclass
class Job:
    id: str
    project: str
    cwd: str
    prompt: str
    status: str
    created_at: str
    updated_at: str
    transcript_log: str = ""
    changed_files: list[str] = field(default_factory=list)
    verification_output: str = ""
    opencode_alias: str = ""
    opencode_session: str | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            id=str(data["id"]),
            project=str(data["project"]),
            cwd=str(data["cwd"]),
            prompt=str(data["prompt"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            transcript_log=str(data.get("transcript_log") or ""),
            changed_files=[str(item) for item in data.get("changed_files") or []],
            verification_output=str(data.get("verification_output") or ""),
            opencode_alias=str(data.get("opencode_alias") or ""),
            opencode_session=str(data["opencode_session"]) if data.get("opencode_session") else None,
            error=str(data["error"]) if data.get("error") else None,
        )


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


def job_to_dict(job: Job) -> dict[str, Any]:
    return asdict(job)


def load_job(job_id: str) -> Job:
    path = job_path(job_id)
    if not path.exists():
        raise JobNotFoundError("job not found")
    return Job.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_job(job: Job) -> None:
    job.updated_at = utc_now()
    path = job_path(job.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job_to_dict(job), indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    session = _opencode_start(job.opencode_alias, job.cwd)
    if not session.get("ok", True):
        return session
    session_id = str(session.get("id") or session.get("session") or "")
    current = load_job(job.id)
    current.opencode_session = session_id
    save_job(current)
    result = _opencode_request(
        "POST",
        f"/session/{session_id}/message",
        {"model": MODEL, "agent": "build", "parts": [{"type": "text", "text": job.prompt}]},
    )
    if not result.get("ok", True):
        return result
    return {"ok": True, **_summarize_opencode_message(session_id, result)}


def _default_state_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "freyja"


def _opencode_base_url() -> str:
    return os.environ.get("OPENCODE_ATLAS_BASE_URL") or os.environ.get("OPENCODE_BASE_URL") or "http://100.119.235.114:4097"


def _opencode_password_file() -> Path:
    return Path(os.environ.get("OPENCODE_PASSWORD_FILE", _default_state_dir() / "opencode" / "server-password")).expanduser()


def _opencode_credentials() -> str:
    username = os.environ.get("OPENCODE_USERNAME", "joe")
    password = _opencode_password_file().read_text(encoding="utf-8").strip()
    return base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")


def _opencode_request(method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, str] | None = None) -> Any:
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{_opencode_base_url().rstrip('/')}{path}", data=data, method=method)
    request.add_header("authorization", "Basic " + _opencode_credentials())
    if body is not None:
        request.add_header("content-type", "application/json")
    try:
        timeout = float(os.environ.get("OPENCODE_REQUEST_TIMEOUT_SECONDS", "45"))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": detail}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if not payload:
        return {"ok": True}
    result = json.loads(payload)
    if isinstance(result, dict):
        result.setdefault("ok", True)
    return result


def _opencode_start(alias: str, cwd: str) -> dict[str, Any]:
    result = _opencode_request("POST", "/session", {"title": alias}, query={"directory": cwd})
    if isinstance(result, dict) and result.get("ok", True):
        result.setdefault("session", result.get("id"))
    return result if isinstance(result, dict) else {"ok": False, "error": f"unexpected OpenCode response: {result!r}"}


def _recent_action(parts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for part in reversed(parts):
        if part.get("type") != "tool":
            continue
        state = part.get("state") or {}
        return {
            "tool": part.get("tool"),
            "status": state.get("status"),
            "input": state.get("input"),
            "output": state.get("output"),
            "error": state.get("error"),
        }
    return None


def _summarize_opencode_message(session_id: str, result: dict[str, Any]) -> dict[str, Any]:
    parts = result.get("parts", []) if isinstance(result, dict) else []
    text = "\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()
    action = _recent_action(parts)
    output = text or ((action or {}).get("output") or "")
    info = result.get("info") or {}
    return {
        "session": session_id,
        "state": "completed" if info.get("time", {}).get("completed") else "working",
        "agent": info.get("agent"),
        "working_directory": (info.get("path") or {}).get("cwd"),
        "message": info.get("id"),
        "recent_action": action,
        "result": output,
    }


def create_job(project: str, prompt: str) -> Job:
    project = project.strip()
    prompt = prompt.strip()
    if not prompt:
        raise BadRequestError("prompt is required")
    cwd = PROJECTS.get(project)
    if cwd is None:
        raise BadRequestError(f"project is not allowlisted; allowed projects: {', '.join(sorted(PROJECTS))}")
    job_id = uuid.uuid4().hex
    now = utc_now()
    job = Job(
        id=job_id,
        project=project,
        cwd=cwd,
        prompt=prompt,
        status="queued",
        created_at=now,
        updated_at=now,
        opencode_alias=f"cloyd-coder-{job_id}",
    )
    append_log(job, "job_queued", {"project": project, "cwd": cwd})
    save_job(job)
    before_files = git_files(cwd)
    thread = threading.Thread(target=run_job, args=(job_id, before_files), name=f"cloyd-coder-{job_id}", daemon=True)
    thread.start()
    return load_job(job_id)


def cancel_job(job_id: str) -> Job:
    job = load_job(job_id)
    if job.status in TERMINAL_STATUSES:
        return job
    job.status = "cancelled"
    append_log(job, "cancel_requested", {"status": "requested"})
    save_job(job)
    if job.opencode_session:
        result = _opencode_request("POST", f"/session/{job.opencode_session}/abort")
    else:
        result = {"ok": True, "status": "cancelled before OpenCode session was recorded"}
    job = load_job(job_id)
    append_log(job, "cancel_requested", result)
    if not result.get("ok"):
        job.error = str(result.get("error") or result)
    save_job(job)
    return job


def route_job_path(path: str) -> tuple[str, str | None]:
    parts = [part for part in path.split("/") if part]
    if parts == ["jobs"]:
        return "jobs", None
    if len(parts) == 2 and parts[0] == "jobs":
        return "job", parts[1]
    if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "log":
        return "job_log", parts[1]
    if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
        return "job_cancel", parts[1]
    return "not_found", None


class Handler(BaseHTTPRequestHandler):
    server_version = "cloyd-coder/0.1"

    def do_POST(self) -> None:
        route, job_id = route_job_path(urlparse(self.path).path)
        try:
            if route == "jobs":
                payload = self._read_json()
                job = create_job(str(payload.get("project") or ""), str(payload.get("prompt") or ""))
                self._json(HTTPStatus.OK, job_to_dict(job))
                return
            if route == "job_cancel" and job_id is not None:
                self._json(HTTPStatus.OK, job_to_dict(cancel_job(job_id)))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except BadRequestError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except JobNotFoundError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

    def do_GET(self) -> None:
        route, job_id = route_job_path(urlparse(self.path).path)
        try:
            if route == "job" and job_id is not None:
                self._json(HTTPStatus.OK, job_to_dict(load_job(job_id)))
                return
            if route == "job_log" and job_id is not None:
                job = load_job(job_id)
                self._json(HTTPStatus.OK, {"id": job.id, "log": job.transcript_log})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except JobNotFoundError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BadRequestError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise BadRequestError("JSON body must be an object")
        return payload

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas-local coding-agent bridge for OpenWebUI/Cloyd.")
    parser.add_argument("--host", default=os.environ.get("CLOYD_CODER_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("CLOYD_CODER_PORT", "8766")), type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"cloyd-coder listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
