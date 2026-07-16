#!/usr/bin/env python3
"""Local operator CLI for Agent Smith write-pilot approvals.

This CLI communicates only with the Freyja Director loopback API. It never
enables Agent Smith, never performs arbitrary shell execution, and never
stores proposed content in the operator state file.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import ipaddress
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TARGET_PATH = "docs/smith-pilot/operator-test.md"
DEFAULT_COMMIT_MESSAGE = "docs: add operator pilot note"


def _default_state_dir() -> Path:
    home = Path.home()
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = home / ".local" / "state"
    return base / "freyja" / "smith-operator"


def _ensure_state_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _restrict_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_loopback(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return False
        addr = ipaddress.ip_address(host)
        return addr.is_loopback
    except ValueError:
        return False


_transport: Any = None


def _api_call(
    base_url: str,
    method: str,
    path: str,
    data: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    if _transport is not None:
        return _transport(method, path, data)

    url = urljoin(base_url, path)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        try:
            payload = json.loads(error_body)
        except json.JSONDecodeError:
            payload = {"detail": error_body}
        raise ApiError(exc.code, payload.get("detail", error_body), payload) from exc
    except urllib.error.URLError as exc:
        raise ApiError(None, f"Could not reach Director at {url}: {exc.reason}", {}) from exc


class ApiError(Exception):
    def __init__(self, status: int | None, message: str, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.payload = payload


class StateError(Exception):
    pass


def _request_state_path(state_dir: Path, request_id: str) -> Path:
    safe_id = "".join(c for c in request_id if c.isalnum() or c in "-_")
    if not safe_id:
        raise StateError("Invalid request ID")
    return state_dir / f"{safe_id}.json"


def _load_request_state(state_dir: Path, request_id: str) -> dict[str, Any]:
    path = _request_state_path(state_dir, request_id)
    if not path.exists():
        raise StateError(f"No operator state for request {request_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_request_state(state_dir: Path, request_id: str, state: dict[str, Any]) -> None:
    path = _request_state_path(state_dir, request_id)
    _ensure_state_dir(state_dir)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    _restrict_file(path)


def _generate_request_id() -> str:
    return "smith-op-" + secrets.token_urlsafe(12)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_content_source(path: str) -> str:
    content_path = Path(path).expanduser().resolve()
    if not content_path.exists():
        raise StateError(f"Content source file not found: {content_path}")
    return content_path.read_text(encoding="utf-8")


def _format_approval(record: dict[str, Any]) -> str:
    lines = [
        f"  Approval ID:    {record.get('id')}",
        f"  Request ID:     {record.get('request_id')}",
        f"  Gate:           {record.get('action')}",
        f"  Status:         {record.get('status')}",
        f"  Target path:    {record.get('target_path')}",
        f"  Summary:        {record.get('summary')}",
        f"  Created:        {record.get('created_at')}",
        f"  Expires:        {record.get('expires_at')}",
    ]
    return "\n".join(lines)


def _find_next_pending_approval(base_url: str, request_id: str) -> dict[str, Any] | None:
    all_pending = _api_call(base_url, "GET", "/agents/smith/approvals").get("approvals", [])
    for record in all_pending:
        if record.get("request_id") == request_id:
            return record
    return None


def _find_pending_approval_for_gate(
    base_url: str,
    request_id: str,
    action: str,
) -> dict[str, Any] | None:
    all_pending = _api_call(base_url, "GET", "/agents/smith/approvals").get("approvals", [])
    for record in all_pending:
        if record.get("request_id") == request_id and record.get("action") == action:
            return record
    return None


def _find_consumed_approval_for_gate(
    base_url: str,
    request_id: str,
    action: str,
) -> dict[str, Any] | None:
    approvals = _api_call(base_url, "GET", "/agents/smith/approvals").get("approvals", [])
    for record in approvals:
        if record.get("request_id") == request_id and record.get("action") == action and record.get("status") == "consumed":
            return record
    return None


_GATE_FOR_STATE: dict[str, str] = {
    "awaiting_path_approval": "path",
    "awaiting_content_approval": "content",
    "awaiting_stage_approval": "stage",
    "awaiting_commit_approval": "commit",
}


def _gate_action(state_name: str) -> str | None:
    return _GATE_FOR_STATE.get(state_name)


def _gate_display_name(action: str) -> str:
    return {
        "path": "path approval (which file to write)",
        "content": "content approval (exact proposed content)",
        "stage": "staging approval (add file to index)",
        "commit": "commit approval (create local Git commit)",
    }.get(action, action)


def _git_status_full(repo_root: str, target: str | None = None) -> str:
    import subprocess

    cmd = ["git", "status", "--short"]
    if target:
        cmd.extend(["--", target])
    try:
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        return proc.stdout
    except FileNotFoundError:
        return ""


def _git_diff_check_full(repo_root: str, target: str) -> bool:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--check", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and not proc.stdout.strip()
    except FileNotFoundError:
        return False


def _git_diff_name_only(repo_root: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(["git", "diff", "--name-only"], cwd=repo_root, capture_output=True, text=True, check=False)
        return proc.stdout
    except FileNotFoundError:
        return ""


def _git_diff_cached_name_only(repo_root: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=repo_root, capture_output=True, text=True, check=False)
        return proc.stdout
    except FileNotFoundError:
        return ""


def _git_diff_cached_stat(repo_root: str, target: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--stat", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        return ""


def _git_diff_cached_check(repo_root: str, target: str) -> bool:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--check", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and not proc.stdout.strip()
    except FileNotFoundError:
        return False


def _git_diff_cached(repo_root: str, target: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout
    except FileNotFoundError:
        return ""


def _command_start(args: argparse.Namespace) -> int:
    target_path = args.target or DEFAULT_TARGET_PATH
    if not target_path.startswith("docs/smith-pilot/"):
        print("Error: target path must be under docs/smith-pilot/", file=sys.stderr)
        return 1
    content = _read_content_source(args.content_file)
    content_hash = _sha256(content)
    commit_message = args.commit_message or DEFAULT_COMMIT_MESSAGE
    commit_hash = _sha256(commit_message)
    request_id = args.request_id or _generate_request_id()

    payload = {
        "objective": args.objective,
        "target_path": target_path,
        "proposed_content": content,
        "commit_message": commit_message,
        "actor": args.actor,
        "request_id": request_id,
    }
    try:
        response = _api_call(args.base_url, "POST", "/agents/smith/write-pilot", payload)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    result = response.get("result", {})
    pending = response.get("pending_approvals", [])
    next_gate = result.get("state", "unknown")

    state = {
        "request_id": request_id,
        "target_path": target_path,
        "content_source_file": str(Path(args.content_file).expanduser().resolve()),
        "content_hash": content_hash,
        "commit_message": commit_message,
        "commit_message_hash": commit_hash,
        "current_gate": next_gate,
        "created_at": _now(),
    }
    _save_request_state(args.state_dir, request_id, state)

    print(f"Started write-pilot request: {request_id}")
    print(f"Target path:     {target_path}")
    print(f"Content size:    {len(content)} bytes")
    print(f"Content SHA-256: {content_hash}")
    print(f"Next gate:       {next_gate}")
    if pending:
        print("Pending approvals:")
        for record in pending:
            print(_format_approval(record))
    else:
        print("No pending approvals returned.")
    print(f"Operator state:  {_request_state_path(args.state_dir, request_id)}")
    return 0


def _command_pending(args: argparse.Namespace) -> int:
    try:
        response = _api_call(args.base_url, "GET", "/agents/smith/approvals")
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    records = response.get("approvals", [])
    if not records:
        print("No pending approvals.")
        return 0
    print(f"Pending approvals ({len(records)}):")
    for record in records:
        print(_format_approval(record))
        print()
    return 0


def _command_show(args: argparse.Namespace) -> int:
    if not args.approval_id:
        print("Error: approval ID is required.", file=sys.stderr)
        return 1
    try:
        record = _api_call(args.base_url, "GET", f"/agents/smith/approvals/{args.approval_id}")
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    print(_format_approval(record))
    return 0


def _confirm_approval() -> bool:
    print("Type APPROVE to confirm this approval.")
    try:
        answer = input("> ").strip()
    except EOFError:
        return False
    return answer == "APPROVE"


def _command_approve(args: argparse.Namespace) -> int:
    if not args.approval_id:
        print("Error: approval ID is required.", file=sys.stderr)
        return 1
    if args.yes:
        if not args.actor or args.actor == "operator":
            print("Error: non-interactive approval requires --actor with an explicit operator name.", file=sys.stderr)
            return 1
        confirmed = True
    else:
        try:
            record = _api_call(args.base_url, "GET", f"/agents/smith/approvals/{args.approval_id}")
        except ApiError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
        print("You are about to approve the following gate:")
        print(_format_approval(record))
        confirmed = _confirm_approval()

    if not confirmed:
        print("Approval cancelled.")
        return 2

    payload = {"actor": args.actor}
    try:
        record = _api_call(args.base_url, "POST", f"/agents/smith/approvals/{args.approval_id}/approve", payload)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    print(f"Approved {record['action']} gate for request {record['request_id']}.")
    return 0


def _command_deny(args: argparse.Namespace) -> int:
    if not args.approval_id:
        print("Error: approval ID is required.", file=sys.stderr)
        return 1
    if not args.actor:
        print("Error: --actor is required to deny an approval.", file=sys.stderr)
        return 1
    if not args.reason:
        print("Error: --reason is required to deny an approval.", file=sys.stderr)
        return 1
    payload = {"actor": args.actor, "reason": args.reason}
    try:
        record = _api_call(args.base_url, "POST", f"/agents/smith/approvals/{args.approval_id}/deny", payload)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    print(f"Denied {record['action']} gate for request {record['request_id']}.")
    return 0


def _command_resume(args: argparse.Namespace) -> int:
    if not args.request_id:
        print("Error: request ID is required.", file=sys.stderr)
        return 1
    if not args.approval_id:
        print("Error: approval ID is required.", file=sys.stderr)
        return 1
    request_id = args.request_id
    try:
        state = _load_request_state(args.state_dir, request_id)
    except StateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    content = _read_content_source(state["content_source_file"])
    if _sha256(content) != state["content_hash"]:
        print("Error: content source file has changed since the request was created.", file=sys.stderr)
        return 1

    approval_id = args.approval_id
    payload = {
        "request_id": request_id,
        "approval_id": approval_id,
        "objective": args.objective or state.get("objective", "operator pilot"),
        "target_path": state["target_path"],
        "proposed_content": content,
        "commit_message": state["commit_message"],
        "actor": args.actor,
        "rollback_on_unapproved": False,
    }
    try:
        response = _api_call(args.base_url, "POST", "/agents/smith/write-pilot/resume", payload)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    result = response.get("result", {})
    next_gate = result.get("state", "unknown")
    state["current_gate"] = next_gate
    state["last_resume_at"] = _now()
    _save_request_state(args.state_dir, request_id, state)

    print(f"Resumed request: {request_id}")
    print(f"Target path:     {state['target_path']}")
    print(f"Next gate:       {next_gate}")
    print(f"Status:          {result.get('status')}")
    print(f"Message:         {result.get('message')}")
    return 1 if result.get("status") == "failed" else 0


def _prompt_yn(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def _git_status(args: argparse.Namespace) -> str:
    return _git_status_str(args.repo_root)


def _git_diff_check(args: argparse.Namespace) -> bool:
    return _git_diff_check_str(args.repo_root, args.target or DEFAULT_TARGET_PATH)


def _git_diff_stat(args: argparse.Namespace) -> str:
    return _git_diff_stat_str(args.repo_root, args.target or DEFAULT_TARGET_PATH)


def _git_staged_stat(args: argparse.Namespace) -> str:
    return _git_staged_stat_str(args.repo_root, args.target or DEFAULT_TARGET_PATH)


def _git_status_str(repo_root: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout
    except FileNotFoundError:
        return ""


def _git_diff_check_str(repo_root: str, target: str) -> bool:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--check", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and not proc.stdout.strip()
    except FileNotFoundError:
        return False


def _git_diff_stat_str(repo_root: str, target: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--stat", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        return ""


def _git_staged_stat_str(repo_root: str, target: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--stat", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        return ""


def _command_start_pilot(args: argparse.Namespace) -> int:
    """Start a resumable write-pilot request and persist operator state."""
    target_path = args.target or DEFAULT_TARGET_PATH
    if not target_path.startswith("docs/smith-pilot/"):
        print("Error: target path must be under docs/smith-pilot/", file=sys.stderr)
        return 1
    content = _read_content_source(args.content_file)
    content_hash = _sha256(content)
    commit_message = args.commit_message or DEFAULT_COMMIT_MESSAGE
    commit_hash = _sha256(commit_message)
    request_id = args.request_id or _generate_request_id()

    payload = {
        "objective": args.objective,
        "target_path": target_path,
        "proposed_content": content,
        "commit_message": commit_message,
        "actor": args.actor,
        "request_id": request_id,
    }
    try:
        response = _api_call(args.base_url, "POST", "/agents/smith/write-pilot", payload)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    result = response.get("result", {})
    pending = response.get("pending_approvals", [])
    next_gate = result.get("state", "unknown")
    current_action = _gate_action(next_gate)
    current_approval_id: str | None = None
    if current_action and pending:
        for record in pending:
            if record.get("action") == current_action:
                current_approval_id = record.get("id")
                break

    state = {
        "request_id": request_id,
        "target_path": target_path,
        "content_source_file": str(Path(args.content_file).expanduser().resolve()),
        "content_hash": content_hash,
        "commit_message": commit_message,
        "commit_message_hash": commit_hash,
        "current_gate": next_gate,
        "current_approval_id": current_approval_id,
        "objective": args.objective,
        "created_at": _now(),
    }
    _save_request_state(args.state_dir, request_id, state)

    print(f"Started write-pilot request: {request_id}")
    print(f"Target path:     {target_path}")
    print(f"Content size:    {len(content)} bytes")
    print(f"Content SHA-256: {content_hash}")
    print(f"Next gate:       {next_gate}")
    if current_approval_id:
        print(f"Approval ID:     {current_approval_id}")
    if pending:
        print("Pending approvals:")
        for record in pending:
            if record.get("request_id") == request_id:
                print(_format_approval(record))
    else:
        print("No pending approvals returned.")
    print(f"Operator state:  {_request_state_path(args.state_dir, request_id)}")
    print()
    print("Next: run 'smith-approval show-current-gate --request-id {request_id}' to review.")
    return 0


def _command_show_current_gate(args: argparse.Namespace) -> int:
    if not args.request_id:
        print("Error: --request-id is required.", file=sys.stderr)
        return 1
    try:
        state = _load_request_state(args.state_dir, args.request_id)
    except StateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    current_gate = state.get("current_gate", "unknown")
    current_action = _gate_action(current_gate)
    print(f"Request ID:  {state['request_id']}")
    print(f"Target path: {state['target_path']}")
    print(f"Current gate: {current_gate}")

    if current_gate == "complete":
        print("Request is complete. No further approvals required.")
        return 0
    if current_gate == "failed":
        print("Request has failed. Inspect the state and abort or retry.")
        return 1
    if current_action is None:
        print(f"Unknown gate state: {current_gate}")
        return 1

    approval = _find_pending_approval_for_gate(args.base_url, state["request_id"], current_action)
    if approval is None:
        print(f"No pending {current_action} approval found.")
        return 1

    print()
    print(f"=== {_gate_display_name(current_action)} ===")
    print(_format_approval(approval))
    print()
    print(f"Run 'smith-approval approve-current-gate --request-id {state['request_id']}' to approve.")
    return 0


def _command_approve_current_gate(args: argparse.Namespace) -> int:
    if not args.request_id:
        print("Error: --request-id is required.", file=sys.stderr)
        return 1
    try:
        state = _load_request_state(args.state_dir, args.request_id)
    except StateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    current_gate = state.get("current_gate", "unknown")
    current_action = _gate_action(current_gate)
    if current_action is None:
        print(f"No pending gate to approve (state: {current_gate}).", file=sys.stderr)
        return 1

    approval = _find_pending_approval_for_gate(args.base_url, state["request_id"], current_action)
    if approval is None:
        print(f"No pending {current_action} approval found.", file=sys.stderr)
        return 1

    print(f"=== {_gate_display_name(current_action)} ===")
    print(_format_approval(approval))

    if current_action == "commit":
        print()
        print("WARNING: This approval will create a local Git commit. It will not push.")
        if args.repo_root:
            staged_stat = _git_diff_cached_stat(args.repo_root, state["target_path"])
            if staged_stat:
                print("Staged changes:")
                print(staged_stat)
        print(f"Commit message: {state['commit_message']}")
        if not _prompt_yn("Approve commit?"):
            print("Commit approval cancelled.")
            return 2
    elif current_action == "stage":
        if args.repo_root:
            print()
            print("Safety check before staging approval:")
            status = _git_status_full(args.repo_root)
            if status:
                if state["target_path"] not in status:
                    print("Error: working tree shows unexpected changes.", file=sys.stderr)
                    print(status)
                    return 3
                print("Working tree changes:")
                print(status)
            else:
                print("No working tree changes found for the target file.")
            if not _git_diff_check_full(args.repo_root, state["target_path"]):
                print("Error: git diff --check reported whitespace errors.", file=sys.stderr)
                return 3
            diff_names = _git_diff_name_only(args.repo_root).strip()
            if diff_names and diff_names != state["target_path"]:
                print("Error: diff contains unexpected files.", file=sys.stderr)
                print(diff_names)
                return 3
            cached_names = _git_diff_cached_name_only(args.repo_root).strip()
            if cached_names:
                print("Error: staged changes already exist.", file=sys.stderr)
                print(cached_names)
                return 3
        print("Type APPROVE to confirm staging, or anything else to abort.")
        if not _confirm_approval():
            print("Staging approval cancelled.")
            return 2
    else:
        print("Type APPROVE to confirm, or anything else to abort.")
        if not _confirm_approval():
            print(f"{current_action} approval cancelled.")
            return 2

    try:
        record = _api_call(
            args.base_url,
            "POST",
            f"/agents/smith/approvals/{approval['id']}/approve",
            {"actor": args.actor},
        )
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    state["last_approved_gate"] = current_action
    state["last_approved_approval_id"] = approval["id"]
    state["last_approved_at"] = _now()
    _save_request_state(args.state_dir, state["request_id"], state)

    print(f"Approved {record['action']} gate for request {record['request_id']}.")
    print(f"Run 'smith-approval resume-pilot --request-id {state['request_id']}' to advance.")
    return 0


def _command_deny_current_gate(args: argparse.Namespace) -> int:
    if not args.request_id:
        print("Error: --request-id is required.", file=sys.stderr)
        return 1
    if not args.reason:
        print("Error: --reason is required.", file=sys.stderr)
        return 1
    try:
        state = _load_request_state(args.state_dir, args.request_id)
    except StateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    current_gate = state.get("current_gate", "unknown")
    current_action = _gate_action(current_gate)
    if current_action is None:
        print(f"No pending gate to deny (state: {current_gate}).", file=sys.stderr)
        return 1

    approval = _find_pending_approval_for_gate(args.base_url, state["request_id"], current_action)
    if approval is None:
        print(f"No pending {current_action} approval found.", file=sys.stderr)
        return 1

    try:
        record = _api_call(
            args.base_url,
            "POST",
            f"/agents/smith/approvals/{approval['id']}/deny",
            {"actor": args.actor, "reason": args.reason},
        )
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    # Trigger a resume so the runtime detects the denial and rolls back any
    # file writes or staged changes for this request.
    try:
        content = _read_content_source(state["content_source_file"])
        _api_call(
            args.base_url,
            "POST",
            "/agents/smith/write-pilot/resume",
            {
                "request_id": state["request_id"],
                "approval_id": approval["id"],
                "objective": state.get("objective", "operator pilot"),
                "target_path": state["target_path"],
                "proposed_content": content,
                "commit_message": state["commit_message"],
                "actor": args.actor,
                "rollback_on_unapproved": True,
            },
        )
    except ApiError:
        # A 409/410 from the resume endpoint is expected because the approval
        # is now denied; the runtime will have performed rollback already.
        pass

    state["last_denied_gate"] = current_action
    state["last_denied_approval_id"] = approval["id"]
    state["last_denied_at"] = _now()
    state["current_gate"] = "rolled_back"
    _save_request_state(args.state_dir, state["request_id"], state)

    print(f"Denied {record['action']} gate for request {record['request_id']}.")
    return 0


def _command_resume_pilot(args: argparse.Namespace) -> int:
    if not args.request_id:
        print("Error: --request-id is required.", file=sys.stderr)
        return 1
    try:
        state = _load_request_state(args.state_dir, args.request_id)
    except StateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    content = _read_content_source(state["content_source_file"])
    if _sha256(content) != state["content_hash"]:
        print("Error: content source file has changed since the request was created.", file=sys.stderr)
        return 1

    approval_id = state.get("last_approved_approval_id")
    if not approval_id:
        print("Error: no approved gate to resume from. Run approve-current-gate first.", file=sys.stderr)
        return 1

    payload = {
        "request_id": state["request_id"],
        "approval_id": approval_id,
        "objective": state.get("objective", "operator pilot"),
        "target_path": state["target_path"],
        "proposed_content": content,
        "commit_message": state["commit_message"],
        "actor": args.actor,
        "rollback_on_unapproved": False,
    }
    try:
        response = _api_call(args.base_url, "POST", "/agents/smith/write-pilot/resume", payload)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    result = response.get("result", {})
    next_gate = result.get("state", "unknown")
    next_action = _gate_action(next_gate)
    next_approval_id: str | None = None
    pending = response.get("pending_approvals", [])
    if next_action and pending:
        for record in pending:
            if record.get("action") == next_action and record.get("request_id") == state["request_id"]:
                next_approval_id = record.get("id")
                break

    state["current_gate"] = next_gate
    state["current_approval_id"] = next_approval_id
    state["last_resume_at"] = _now()
    _save_request_state(args.state_dir, state["request_id"], state)

    print(f"Resumed request: {state['request_id']}")
    print(f"Target path:     {state['target_path']}")
    print(f"Status:          {result.get('status')}")
    print(f"Message:         {result.get('message')}")
    print(f"Next gate:       {next_gate}")
    if next_approval_id:
        print(f"Approval ID:     {next_approval_id}")
        print(f"Run 'smith-approval show-current-gate --request-id {state['request_id']}' to review.")
    elif result.get("status") == "complete":
        print()
        print("Write-pilot run complete.")
        print(f"Committed: {result.get('committed')}")
        print(f"Commit hash: {result.get('commit_hash')}")
        print("No push was performed.")
    return 0 if result.get("status") in {"complete", "awaiting"} or str(next_gate).startswith("awaiting_") else 1


def _command_run_pilot(args: argparse.Namespace) -> int:
    target_path = args.target or DEFAULT_TARGET_PATH
    if target_path != DEFAULT_TARGET_PATH:
        print("Error: the initial run-pilot command may only target docs/smith-pilot/operator-test.md.", file=sys.stderr)
        return 1

    content = _read_content_source(args.content_file)
    content_hash = _sha256(content)
    commit_message = args.commit_message or DEFAULT_COMMIT_MESSAGE
    request_id = args.request_id or _generate_request_id()

    # Start
    start_payload = {
        "objective": args.objective,
        "target_path": target_path,
        "proposed_content": content,
        "commit_message": commit_message,
        "actor": args.actor,
        "request_id": request_id,
    }
    try:
        response = _api_call(args.base_url, "POST", "/agents/smith/write-pilot", start_payload)
    except ApiError as exc:
        print(f"Error starting write pilot: {exc.message}", file=sys.stderr)
        return 1

    result = response.get("result", {})
    pending = response.get("pending_approvals", [])
    if not pending:
        print("No pending approvals; run finished or failed.")
        print(f"Status: {result.get('status')}; state: {result.get('state')}; message: {result.get('message')}")
        return 0

    state = {
        "request_id": request_id,
        "target_path": target_path,
        "content_source_file": str(Path(args.content_file).expanduser().resolve()),
        "content_hash": content_hash,
        "commit_message": commit_message,
        "commit_message_hash": _sha256(commit_message),
        "current_gate": result.get("state", "unknown"),
        "created_at": _now(),
        "objective": args.objective,
    }
    _save_request_state(args.state_dir, request_id, state)

    gate_order = ["path", "content", "stage", "commit"]
    gate_display = {
        "path": "path approval (which file to write)",
        "content": "content approval (exact proposed content)",
        "stage": "staging approval (add file to index)",
        "commit": "commit approval (create local Git commit)",
    }

    for action in gate_order:
        # Locate the pending approval for this gate.
        approval = _find_next_pending_approval(args.base_url, request_id)
        if approval is None or approval.get("action") != action:
            print(f"No pending {action} approval; current state is {result.get('state')}. Stopping.")
            break

        print()
        print(f"=== {gate_display[action]} ===")
        print(_format_approval(approval))

        if action == "stage":
            print()
            print("Safety check: verifying only the approved file changed.")
            status = _git_status_str(args.repo_root)
            if status and target_path not in status:
                print("Error: working tree shows unexpected changes.", file=sys.stderr)
                print(status)
                print("Aborting before staging.")
                return 3
            if not _git_diff_check_str(args.repo_root, target_path):
                print("Error: git diff --check reported whitespace errors.", file=sys.stderr)
                print("Aborting before staging.")
                return 3

        if action == "commit":
            print()
            print("WARNING: This approval will create a local Git commit. It will not push.")
            staged_stat = _git_staged_stat_str(args.repo_root, target_path)
            if staged_stat:
                print("Staged changes:")
                print(staged_stat)
            print(f"Commit message: {commit_message}")
            if not _prompt_yn("Approve commit?"):
                print("Commit approval cancelled.")
                return 3
        else:
            print("Type APPROVE to confirm, or anything else to abort.")
            if not _confirm_approval():
                print(f"{action} approval cancelled.")
                return 3

        # Submit approval
        try:
            _api_call(args.base_url, "POST", f"/agents/smith/approvals/{approval['id']}/approve", {"actor": args.actor})
        except ApiError as exc:
            print(f"Error approving {action}: {exc.message}", file=sys.stderr)
            return 1

        # Resume
        try:
            response = _api_call(
                args.base_url,
                "POST",
                "/agents/smith/write-pilot/resume",
                {
                    "request_id": request_id,
                    "approval_id": approval["id"],
                    "objective": args.objective,
                    "target_path": target_path,
                    "proposed_content": content,
                    "commit_message": commit_message,
                    "actor": args.actor,
                },
            )
        except ApiError as exc:
            print(f"Error resuming after {action}: {exc.message}", file=sys.stderr)
            return 1

        result = response.get("result", {})
        state["current_gate"] = result.get("state", "unknown")
        state["last_gate_approved"] = action
        state["last_resume_at"] = _now()
        _save_request_state(args.state_dir, request_id, state)

        print(f"Approved {action} gate. Current state: {result.get('state')}")

        if result.get("status") == "complete":
            print()
            print("Write-pilot run complete.")
            print(f"Committed: {result.get('committed')}")
            print(f"Commit hash: {result.get('commit_hash')}")
            print(f"No push was performed.")
            return 0
        # A 'failed' status with an awaiting state is the runtime's way of
        # signalling that the next gate needs approval; continue the loop.
        if result.get("status") == "failed" and str(result.get("state", "")).startswith("awaiting_"):
            continue
        if result.get("status") != "failed":
            continue
        print(f"Run failed at state {result.get('state')}: {result.get('message')}")
        return 1

    print()
    print("Write-pilot run stopped.")
    print(f"Final state: {result.get('state')}")
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smith-approval",
        description="Local operator CLI for Agent Smith write-pilot approvals.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Freyja Director base URL (default: http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for operator state files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start a new write-pilot request.")
    start.add_argument("--target", default=DEFAULT_TARGET_PATH, help="Repository-relative target path.")
    start.add_argument("--content-file", required=True, help="Path to a local file containing proposed content.")
    start.add_argument("--commit-message", default=DEFAULT_COMMIT_MESSAGE)
    start.add_argument("--objective", default="operator write-pilot")
    start.add_argument("--actor", default="operator")
    start.add_argument("--request-id", default=None)

    sub.add_parser("pending", help="List pending approvals.")

    show = sub.add_parser("show", help="Show one approval.")
    show.add_argument("approval_id", nargs="?", default=None)
    show.add_argument("--approval-id", dest="approval_id_opt", default=None)

    approve = sub.add_parser("approve", help="Approve an approval.")
    approve.add_argument("approval_id", nargs="?", default=None)
    approve.add_argument("--approval-id", dest="approval_id_opt", default=None)
    approve.add_argument("--yes", action="store_true", help="Non-interactive mode; requires --actor.")
    approve.add_argument("--actor", default="operator")

    deny = sub.add_parser("deny", help="Deny an approval.")
    deny.add_argument("approval_id", nargs="?", default=None)
    deny.add_argument("--approval-id", dest="approval_id_opt", default=None)
    deny.add_argument("--actor", required=True)
    deny.add_argument("--reason", required=True)

    resume = sub.add_parser("resume", help="Resume a write-pilot request after an approval.")
    resume.add_argument("request_id", nargs="?", default=None)
    resume.add_argument("approval_id", nargs="?", default=None)
    resume.add_argument("--request-id", dest="request_id_opt", default=None)
    resume.add_argument("--approval-id", dest="approval_id_opt", default=None)
    resume.add_argument("--objective", default=None)
    resume.add_argument("--actor", default="operator")

    run_pilot = sub.add_parser("run-pilot", help="Operator-assisted end-to-end pilot through all gates.")
    run_pilot.add_argument("--content-file", required=True)
    run_pilot.add_argument("--target", default=DEFAULT_TARGET_PATH)
    run_pilot.add_argument("--commit-message", default=DEFAULT_COMMIT_MESSAGE)
    run_pilot.add_argument("--objective", default="operator write-pilot")
    run_pilot.add_argument("--actor", default="operator")
    run_pilot.add_argument("--request-id", default=None)
    run_pilot.add_argument("--repo-root", default=".", help="Path to the Git repository for local safety checks.")

    start_pilot = sub.add_parser("start-pilot", help="Start a resumable write-pilot request.")
    start_pilot.add_argument("--target", default=DEFAULT_TARGET_PATH)
    start_pilot.add_argument("--content-file", required=True)
    start_pilot.add_argument("--commit-message", default=DEFAULT_COMMIT_MESSAGE)
    start_pilot.add_argument("--objective", default="operator write-pilot")
    start_pilot.add_argument("--actor", default="operator")
    start_pilot.add_argument("--request-id", default=None)

    show_gate = sub.add_parser("show-current-gate", help="Show the pending gate for a resumable request.")
    show_gate.add_argument("--request-id", required=True)

    approve_gate = sub.add_parser("approve-current-gate", help="Approve the current pending gate interactively.")
    approve_gate.add_argument("--request-id", required=True)
    approve_gate.add_argument("--actor", default="operator")
    approve_gate.add_argument("--repo-root", default=".")

    deny_gate = sub.add_parser("deny-current-gate", help="Deny the current pending gate.")
    deny_gate.add_argument("--request-id", required=True)
    deny_gate.add_argument("--actor", default="operator")
    deny_gate.add_argument("--reason", required=True)

    resume_pilot = sub.add_parser("resume-pilot", help="Resume a resumable request after the current gate is approved.")
    resume_pilot.add_argument("--request-id", required=True)
    resume_pilot.add_argument("--actor", default="operator")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.state_dir is None:
        args.state_dir = _default_state_dir()
    args.state_dir = args.state_dir.expanduser().resolve()

    if not _is_loopback(args.base_url):
        print(
            "Error: base URL must use a loopback address. "
            "Non-loopback operation is not supported by this milestone.",
            file=sys.stderr,
        )
        return 1

    # Resolve positional vs option-style IDs, supporting IDs that start with '-'.
    if hasattr(args, "approval_id_opt") and args.approval_id_opt is not None:
        args.approval_id = args.approval_id_opt
    if hasattr(args, "request_id_opt") and args.request_id_opt is not None:
        args.request_id = args.request_id_opt

    handlers: dict[str, Any] = {
        "start": _command_start,
        "pending": _command_pending,
        "show": _command_show,
        "approve": _command_approve,
        "deny": _command_deny,
        "resume": _command_resume,
        "run-pilot": _command_run_pilot,
        "start-pilot": _command_start_pilot,
        "show-current-gate": _command_show_current_gate,
        "approve-current-gate": _command_approve_current_gate,
        "deny-current-gate": _command_deny_current_gate,
        "resume-pilot": _command_resume_pilot,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
