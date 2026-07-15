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
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=args.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout
    except FileNotFoundError:
        return ""


def _git_diff_check(args: argparse.Namespace) -> bool:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--check", "--", args.target or DEFAULT_TARGET_PATH],
            cwd=args.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and not proc.stdout.strip()
    except FileNotFoundError:
        return False


def _git_diff_stat(args: argparse.Namespace) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--stat", "--", args.target or DEFAULT_TARGET_PATH],
            cwd=args.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        return ""


def _git_staged_stat(args: argparse.Namespace) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--stat", "--", args.target or DEFAULT_TARGET_PATH],
            cwd=args.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        return ""


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
            status = _git_status(args)
            if status and target_path not in status:
                print("Error: working tree shows unexpected changes.", file=sys.stderr)
                print(status)
                print("Aborting before staging.")
                return 3
            if not _git_diff_check(args):
                print("Error: git diff --check reported whitespace errors.", file=sys.stderr)
                print("Aborting before staging.")
                return 3
            diff_stat = _git_diff_stat(args)
            if diff_stat:
                print("Diff stat for approved file:")
                print(diff_stat)

        if action == "commit":
            print()
            print("WARNING: This approval will create a local Git commit. It will not push.")
            staged = _git_staged_stat(args)
            if staged:
                print("Staged changes:")
                print(staged)
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
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
