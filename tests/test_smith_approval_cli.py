"""Tests for the local operator CLI in src/freyja/cli/smith_approval.py.

All tests use temporary Git repositories, temporary approval databases,
temporary operator-state directories, and an in-process loopback TestClient.
No test modifies the real Freyja-OS repository or runs a live write pilot.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from freyja.cli import smith_approval
from freyja.config import settings
from freyja.main import app
from freyja.tools.builtin import register_smith_write_pilot_tools
from freyja.tools.registry import get_registry

from tests.smith_approval_cli_helpers import make_test_client_transport


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "docs" / "smith-pilot").mkdir(parents=True)
    (repo / "docs" / "smith-pilot" / ".gitkeep").write_text("")
    (repo / "README.md").write_text("# repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def policy_path(tmp_path: Path, tmp_git_repo: Path) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(
        f"""
allowed_root: {tmp_git_repo}
read_only_builtin_tools:
  - system_health
smith_read_only_tools:
  - repository_status
write_pilot_allowed_tools:
  - write_pilot_file_write
  - write_pilot_git_add
  - write_pilot_git_commit
write_pilot_sandbox: {tmp_git_repo}/docs/smith-pilot
auto_allowed_operations:
  - repository_status
  - no-op
approval_required_operations:
  - write_pilot_git_commit
  - write_pilot_file_write
  - write_pilot_git_add
prohibited_operations:
  - arbitrary_shell
  - arbitrary_filesystem_write
  - outside_root_access
  - execute_command
max_retries: 2
"""
    )
    return path


@pytest.fixture
def enabled_client(tmp_path: Path, policy_path: Path, monkeypatch) -> TestClient:
    db_path = tmp_path / "approvals.sqlite3"
    registry = get_registry()
    register_smith_write_pilot_tools(registry)
    for tool in registry.list_tools(include_disabled=True):
        if tool.name.startswith("write_pilot_"):
            registry.set_enabled(tool.name, True)
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_policy_path", str(policy_path))
    monkeypatch.setattr(settings, "agent_smith_approval_db_path", str(db_path))
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", False)
    client = TestClient(app)
    monkeypatch.setattr(smith_approval, "_transport", make_test_client_transport(client))
    return client


def _run_cli(argv: list[str]) -> int:
    return smith_approval.main(argv)


def _content_file(tmp_path: Path, text: str = "# note\n") -> Path:
    path = tmp_path / "proposed.md"
    path.write_text(text, encoding="utf-8")
    return path


def _find_pending_approval_id(request_id: str, client: TestClient) -> str:
    response = client.get("/agents/smith/approvals")
    response.raise_for_status()
    return next(a["id"] for a in response.json()["approvals"] if a["request_id"] == request_id)


def test_cli_help():
    with pytest.raises(SystemExit) as exc_info:
        _run_cli(["--help"])
    assert exc_info.value.code == 0


def test_cli_refuses_non_loopback_base_url():
    code = _run_cli([
        "--base-url",
        "http://192.0.2.1:8000",
        "pending",
    ])
    assert code == 1


def test_cli_refuses_base_url_with_hostname():
    code = _run_cli([
        "--base-url",
        "http://localhost:8000",
        "pending",
    ])
    assert code == 1


def test_cli_allows_explicit_loopback_ipv6():
    with pytest.raises(SystemExit) as exc_info:
        _run_cli(["--base-url", "http://[::1]:8000", "--help"])
    assert exc_info.value.code == 0


def test_start_creates_pending_approval_and_state_file(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)

    code = _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--commit-message",
        "add operator note",
        "--request-id",
        "req-start",
    ])
    assert code == 0

    state_file = state_dir / "req-start.json"
    assert state_file.exists()
    mode = state_file.stat().st_mode & 0o777
    assert mode == 0o600

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["request_id"] == "req-start"
    assert state["target_path"] == "docs/smith-pilot/operator-test.md"
    assert state["content_source_file"] == str(content_path)
    assert state["content_hash"] == smith_approval._sha256(content_path.read_text(encoding="utf-8"))
    assert state["commit_message"] == "add operator note"
    assert "commit_message_hash" in state
    assert "proposed_content" not in state


def test_start_rejects_path_outside_sandbox(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    code = _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "README.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-bad-path",
    ])
    assert code == 1


def test_pending_and_show_commands(
    enabled_client,
    tmp_path: Path,
    capsys,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-list",
    ])

    capsys.readouterr()
    code = _run_cli(["pending"])
    captured = capsys.readouterr()
    assert code == 0
    assert "req-list" in captured.out
    assert "path" in captured.out

    approval_id = _find_pending_approval_id("req-list", enabled_client)
    capsys.readouterr()
    code = _run_cli(["show", approval_id])
    captured = capsys.readouterr()
    assert code == 0
    assert approval_id in captured.out
    assert "content_hash" not in captured.out


def test_approve_requires_explicit_confirmation(
    enabled_client,
    tmp_path: Path,
    monkeypatch,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-confirm",
    ])

    approval_id = _find_pending_approval_id("req-confirm", enabled_client)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    code = _run_cli(["approve", approval_id])
    assert code == 2


def test_approve_non_interactive_requires_explicit_actor(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-noninteractive",
    ])

    approval_id = _find_pending_approval_id("req-noninteractive", enabled_client)

    # --yes without explicit actor must fail.
    code = _run_cli(["approve", approval_id, "--yes"])
    assert code == 1

    # --yes with explicit actor succeeds.
    code = _run_cli(["approve", approval_id, "--yes", "--actor", "operator-test"])
    assert code == 0


def test_deny_requires_actor_and_reason(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-deny",
    ])

    approval_id = _find_pending_approval_id("req-deny", enabled_client)

    code = _run_cli([
        "deny", approval_id, "--actor", "operator-test", "--reason", "operator declined",
    ])
    assert code == 0


def test_resume_detects_changed_content_source(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-resume-change",
    ])

    approval_id = _find_pending_approval_id("req-resume-change", enabled_client)
    content_path.write_text("# changed\n", encoding="utf-8")

    code = _run_cli([
        "--state-dir", str(state_dir),
        "resume", "--request-id", "req-resume-change", "--approval-id", approval_id,
    ])
    assert code == 1


def test_run_pilot_locked_to_initial_target(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)

    code = _run_cli([
        "--state-dir",
        str(state_dir),
        "run-pilot",
        "--content-file",
        str(content_path),
        "--target",
        "docs/smith-pilot/other.md",
        "--repo-root",
        str(tmp_path),
    ])
    assert code == 1


def test_run_pilot_aborts_at_path_gate(
    enabled_client,
    tmp_path: Path,
    monkeypatch,
    tmp_git_repo: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "no")

    code = _run_cli([
        "--state-dir",
        str(state_dir),
        "run-pilot",
        "--content-file",
        str(content_path),
        "--repo-root",
        str(tmp_git_repo),
    ])
    assert code == 3


def test_operator_state_directory_permissions(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-perms",
    ])
    mode = state_dir.stat().st_mode & 0o777
    assert mode == 0o700


def test_run_pilot_completes_all_four_gates(
    enabled_client,
    tmp_path: Path,
    monkeypatch,
    tmp_git_repo: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)

    inputs = iter(["APPROVE", "APPROVE", "APPROVE", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    code = _run_cli([
        "--state-dir",
        str(state_dir),
        "run-pilot",
        "--content-file",
        str(content_path),
        "--repo-root",
        str(tmp_git_repo),
        "--commit-message",
        "add operator note",
    ])
    assert code == 0

    target = tmp_git_repo / "docs" / "smith-pilot" / "operator-test.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "# note\n"

    status_proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert status_proc.stdout.strip() == ""

    log_proc = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert log_proc.stdout.strip() == "add operator note"


def test_run_pilot_aborts_before_commit(
    enabled_client,
    tmp_path: Path,
    monkeypatch,
    tmp_git_repo: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)

    inputs = iter(["APPROVE", "APPROVE", "APPROVE", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    code = _run_cli([
        "--state-dir",
        str(state_dir),
        "run-pilot",
        "--content-file",
        str(content_path),
        "--repo-root",
        str(tmp_git_repo),
    ])
    assert code == 3

    target = tmp_git_repo / "docs" / "smith-pilot" / "operator-test.md"
    assert not target.exists()
    status_proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "docs/smith-pilot/operator-test.md" not in status_proc.stdout


def test_content_not_copied_into_operator_state(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path, "SECRET-CONTENT-12345\n")
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-secret",
    ])
    state_file = state_dir / "req-secret.json"
    blob = state_file.read_text(encoding="utf-8")
    assert "SECRET-CONTENT-12345" not in blob


def test_api_unavailable_returns_error(
    enabled_client,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(smith_approval, "_transport", None)
    code = _run_cli(["--base-url", "http://127.0.0.1:1", "pending"])
    assert code == 1


def test_deny_then_resume_reports_denial(
    enabled_client,
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    content_path = _content_file(tmp_path)
    _run_cli([
        "--state-dir",
        str(state_dir),
        "start",
        "--target",
        "docs/smith-pilot/operator-test.md",
        "--content-file",
        str(content_path),
        "--request-id",
        "req-denied-resume",
    ])

    approval_id = _find_pending_approval_id("req-denied-resume", enabled_client)

    _run_cli([
        "deny", approval_id, "--actor", "op", "--reason", "no",
    ])

    code = _run_cli([
        "--state-dir", str(state_dir),
        "resume", "--request-id", "req-denied-resume", "--approval-id", approval_id,
    ])
    assert code == 1
