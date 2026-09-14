#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JOBS_FILE = Path("/app/backend/data/cloyd-smith-loop-jobs.json")
ALIASES_FILE = Path("/app/backend/data/opencode-runtime-aliases.json")
MODEL = {"providerID": "vulcan-nexus", "modelID": "@preset/freyja-coder"}
MAX_BUSY_CHECKS = int(os.environ.get("FREYJA52_MAX_BUSY_CHECKS", "12"))
DEFAULT_ALIASES = {
    "atlas-dashboard": {
        "base_url": "http://100.119.235.114:4097",
        "directory": "/home/joe/cloyd-services",
        "password_file": "/app/backend/data/secrets/opencode-password",
        "session": "",
        "username": "joe",
    },
    "freyja-code": {
        "base_url": "http://100.115.228.56:4097",
        "directory": "/Users/freyja/freyja-os",
        "password_file": "/app/backend/data/secrets/opencode-iris-password",
        "session": "",
        "username": "joe",
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def merge_save_ledger(ledger: dict[str, Any], touched_jobs: set[str]) -> None:
    latest = load_ledger()
    for job_id in touched_jobs:
        if job_id in ledger.get("jobs", {}):
            latest.setdefault("jobs", {})[job_id] = ledger["jobs"][job_id]
        latest_events = latest.setdefault("events", {}).setdefault(job_id, [])
        seen = {
            (event.get("event_type"), event.get("created_at"), json.dumps(event.get("payload", {}), sort_keys=True))
            for event in latest_events
        }
        for event in ledger.get("events", {}).get(job_id, []):
            key = (event.get("event_type"), event.get("created_at"), json.dumps(event.get("payload", {}), sort_keys=True))
            if key not in seen:
                latest_events.append(event)
                seen.add(key)
    save_json(JOBS_FILE, latest)


def load_ledger() -> dict[str, Any]:
    ledger = load_json(JOBS_FILE, {"jobs": {}, "events": {}})
    ledger.setdefault("jobs", {})
    ledger.setdefault("events", {})
    return ledger


def load_aliases() -> dict[str, dict[str, str]]:
    aliases = load_json(ALIASES_FILE, {})
    for alias, defaults in DEFAULT_ALIASES.items():
        aliases.setdefault(alias, defaults.copy())
    return aliases


def save_aliases(aliases: dict[str, Any]) -> None:
    save_json(ALIASES_FILE, aliases)


def alias_config(alias: str) -> dict[str, str]:
    aliases = load_aliases()
    entry = aliases.get(alias, {})
    if isinstance(entry, str):
        entry = {"session": entry}
    defaults = DEFAULT_ALIASES.get(alias, DEFAULT_ALIASES["freyja-code"])
    return {**defaults, **entry}


def opencode_request(config: dict[str, str], method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, str] | None = None, timeout: int = 300) -> Any:
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{config['base_url'].rstrip('/')}{path}", data=data, method=method)
    password = Path(config["password_file"]).read_text(encoding="utf-8").strip()
    credentials = f"{config['username']}:{password}".encode("utf-8")
    request.add_header("authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))
    if body is not None:
        request.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except TimeoutError:
        return {"ok": False, "timeout": True, "error": f"OpenCode request exceeded {timeout} seconds"}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.read().decode("utf-8", errors="replace")}
    except Exception as exc:
        text = str(exc)
        return {"ok": False, "timeout": "timed out" in text.lower(), "error": text}
    if not payload:
        return {"ok": True}
    result = json.loads(payload)
    if isinstance(result, dict):
        result.setdefault("ok", True)
    return result


def ensure_session(alias: str, config: dict[str, str]) -> tuple[dict[str, str], str]:
    session = config.get("session", "")
    if session:
        return config, session
    result = opencode_request(config, "POST", "/session", {"title": alias}, query={"directory": config["directory"]}, timeout=60)
    if not result.get("ok", True):
        raise RuntimeError(json.dumps(result))
    aliases = load_aliases()
    config["session"] = result["id"]
    aliases[alias] = config
    save_aliases(aliases)
    return config, result["id"]


def smith_prompt(job: dict[str, Any]) -> str:
    criteria = "\n".join(f"- {item}" for item in job.get("acceptance_criteria", [])) or "- Report evidence clearly."
    return f"""Freyja 5.2 Smith worker task.

Original Cloyd objective:
{job['objective']}

Current Smith task:
{job['current_prompt']}

Acceptance criteria:
{criteria}

Rules:
- Do not use subagents or task delegation.
- Use direct commands only.
- Keep work bounded and report commands, diffs, tests, blockers, and evidence.
- Stop after reporting. Cloyd owns the master plan.
"""


def add_event(ledger: dict[str, Any], job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    ledger.setdefault("events", {}).setdefault(job_id, []).append(
        {"event_type": event_type, "payload": bounded(payload), "created_at": now()}
    )


def bounded(payload: Any, limit: int = 20000) -> dict[str, Any]:
    text = json.dumps(payload, default=str)
    if len(text) <= limit:
        return payload if isinstance(payload, dict) else {"value": payload}
    return {"truncated": True, "text": text[-limit:]}


def run_once() -> list[dict[str, Any]]:
    ledger = load_ledger()
    results: list[dict[str, Any]] = []
    touched_jobs: set[str] = set()
    for job_id, job in sorted(ledger["jobs"].items(), key=lambda item: (item[1].get("created_at", ""), item[0])):
        if job.get("status") == "queued":
            try:
                config, session = ensure_session(job.get("smith_alias", "freyja-code"), alias_config(job.get("smith_alias", "freyja-code")))
                result = opencode_request(
                    config,
                    "POST",
                    f"/session/{session}/message",
                    {"model": MODEL, "agent": "build", "parts": [{"type": "text", "text": smith_prompt(job)}]},
                    timeout=25,
                )
                add_event(ledger, job_id, "smith_send", result)
                completed = bool(((result.get("info") or {}).get("time") or {}).get("completed")) if isinstance(result, dict) else False
                accepted_or_running = bool(result.get("ok", True) or result.get("timeout"))
                job["status"] = "needs_review" if completed else ("running" if accepted_or_running else "blocked")
                job["next_action"] = "cloyd_review_evidence" if completed else ("check_smith_output" if accepted_or_running else "operator_review")
                job["last_evidence"] = bounded(result)
                job["updated_at"] = now()
                touched_jobs.add(job_id)
                results.append({"job_id": job_id, "action": "sent_to_smith", "status": job["status"]})
            except Exception as exc:
                add_event(ledger, job_id, "daemon_error", {"error": str(exc)})
                job["status"] = "blocked"
                job["error"] = str(exc)
                job["next_action"] = "operator_review"
                job["updated_at"] = now()
                touched_jobs.add(job_id)
                results.append({"job_id": job_id, "action": "blocked", "status": "blocked"})
        elif job.get("status") == "running":
            config = alias_config(job.get("smith_alias", "freyja-code"))
            session = config.get("session", "")
            if not session:
                job["status"] = "blocked"
                job["error"] = "missing OpenCode session"
                job["updated_at"] = now()
                touched_jobs.add(job_id)
                continue
            status = opencode_request(config, "GET", "/session/status", timeout=30)
            add_event(ledger, job_id, "smith_status", status)
            if not status.get("ok", True):
                job["status"] = "blocked"
                job["error"] = str(status.get("error") or "status failed")
                job["updated_at"] = now()
                touched_jobs.add(job_id)
            elif status.get(session, "idle") == "idle":
                output = opencode_request(config, "GET", f"/session/{session}/message", query={"limit": "3"}, timeout=30)
                add_event(ledger, job_id, "smith_output", {"messages": output})
                job["status"] = "needs_review"
                job["next_action"] = "cloyd_review_evidence"
                job["last_evidence"] = bounded({"messages": output})
                job["updated_at"] = now()
                touched_jobs.add(job_id)
                results.append({"job_id": job_id, "action": "ready_for_review", "status": "needs_review"})
            else:
                busy_checks = int(job.get("busy_checks") or 0) + 1
                job["last_evidence"] = bounded(status)
                job["updated_at"] = now()
                job["busy_checks"] = busy_checks
                if busy_checks >= MAX_BUSY_CHECKS:
                    job["status"] = "blocked"
                    job["error"] = f"Smith stayed busy for {busy_checks} checks"
                    job["next_action"] = "operator_review"
                    results.append({"job_id": job_id, "action": "busy_timeout", "status": "blocked"})
                else:
                    results.append({"job_id": job_id, "action": "still_running", "status": "running", "busy_checks": busy_checks})
                touched_jobs.add(job_id)
    if touched_jobs:
        merge_save_ledger(ledger, touched_jobs)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Freyja 5.2 OpenWebUI Cloyd-Smith daemon.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_once(), indent=2))
        return 0
    while True:
        results = run_once()
        if results:
            print(json.dumps({"results": results}, sort_keys=True), flush=True)
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
