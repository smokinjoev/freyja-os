"""Tests for Agent Smith approved-write pilot framework.

All write/commit tests use isolated temporary Git repositories.  No test
modifies the real Freyja-OS repository or runs a live write pilot.
"""

import asyncio
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from freyja.agents import (
    AgentPolicy,
    ApprovalCallback,
    SmithOrchestrator,
    SmithRuntime,
    WritePilotResult,
    WritePilotState,
    register_smith_tools,
)
from freyja.agents.approval_provider import PersistentApprovalProvider
from freyja.agents.approval_store import SmithApprovalStore
from freyja.config import settings
from freyja.main import app
from freyja.tools.builtin import register_smith_write_pilot_tools
from freyja.tools.models import ToolRiskLevel
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create an isolated Git repository with docs/smith-pilot/."""
    repo = tmp_path / "repo"
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
def write_pilot_policy(tmp_path, tmp_git_repo):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        f"""
allowed_root: {tmp_git_repo}
read_only_builtin_tools:
  - system_health
smith_read_only_tools:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
  - validate_diff
write_pilot_allowed_tools:
  - write_pilot_file_write
  - write_pilot_git_add
  - write_pilot_git_commit
write_pilot_sandbox: {tmp_git_repo}/docs/smith-pilot
auto_allowed_operations:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
  - validate_diff
  - inspect
  - no-op
  - summarize
approval_required_operations:
  - write_pilot_git_commit
  - write_pilot_file_write
  - write_pilot_git_add
prohibited_operations:
  - git_push
  - git_force_push
  - git_reset
  - git_clean
  - git_rebase
  - destructive_git_operation
  - arbitrary_shell
  - arbitrary_filesystem_write
  - package_installation
  - service_termination
  - credential_access
  - secret_extraction
  - outside_root_access
  - execute_command
max_retries: 2
secret_patterns:
  - "\\\\.env$"
  - "(^|/)secrets?(/|$)"
  - "\\\\.pem$"
  - "\\\\.key$"
  - "\\\\.pfx$"
  - "\\\\.p12$"
  - "\\\\.crt$"
  - "token"
  - "api_key"
  - "password"
"""
    )
    return str(policy_path)


@pytest.fixture
def write_pilot_registry(tmp_path, write_pilot_policy, tmp_git_repo):
    registry = ToolRegistry()
    register_smith_write_pilot_tools(registry)
    for tool in registry.list_tools(include_disabled=True):
        registry.set_enabled(tool.name, True)
    return registry


@pytest.fixture
def write_pilot_runtime(write_pilot_registry, write_pilot_policy, tmp_git_repo, monkeypatch):
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_audit_enabled", False)
    policy = AgentPolicy(write_pilot_policy)
    orchestrator = SmithOrchestrator(registry=write_pilot_registry, policy=policy, max_retries=2)
    runtime = SmithRuntime(
        orchestrator=orchestrator,
        policy=policy,
        max_steps=5,
        max_retries=2,
        audit_log_path=str(tmp_git_repo / "audit.jsonl"),
    )
    # Bind the runtime to the temporary repo so file/git tools operate there.
    runtime._repo_root_for_write_pilot = tmp_git_repo
    return runtime


@pytest.fixture
def approving_callback():
    async def _callback(approval_type, request_id, context):
        return ApprovalCallback(
            approval_type=approval_type,
            request_id=request_id,
            approved=True,
            target_path=context.get("target_path"),
            commit_message=context.get("commit_message"),
        )

    return _callback


def _force_repo_root(runtime, repo_root):
    """Point the write-pilot executor at the temporary Git repository."""
    original_execute = runtime._WritePilotRun_class_execute if hasattr(runtime, "_WritePilotRun_class_execute") else None


@pytest.fixture
def test_client_write_pilot_enabled(tmp_path, monkeypatch):
    policy_path = tmp_path / "policy.yaml"
    repo_root = tmp_path / "freyja-os"
    repo_root.mkdir()
    (repo_root / "docs" / "smith-pilot").mkdir(parents=True)
    policy_path.write_text(
        f"""
allowed_root: {repo_root}
read_only_builtin_tools:
  - system_health
smith_read_only_tools:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
  - validate_diff
write_pilot_allowed_tools:
  - write_pilot_file_write
  - write_pilot_git_add
  - write_pilot_git_commit
write_pilot_sandbox: {repo_root}/docs/smith-pilot
auto_allowed_operations:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
  - validate_diff
  - inspect
  - no-op
  - summarize
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
    monkeypatch.setattr(settings, "agent_smith_policy_path", str(policy_path))
    monkeypatch.setattr(settings, "agent_smith_approval_db_path", str(tmp_path / "smith-approvals.sqlite3"))
    monkeypatch.setattr(settings, "agent_smith_audit_log_path", str(tmp_path / "agent-smith-audit.jsonl"))
    from fastapi.testclient import TestClient

    return TestClient(app)


# ---------------------------------------------------------------------------
# Runtime gating tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_pilot_blocked_when_smith_disabled(write_pilot_runtime, tmp_git_repo):
    from freyja.config import settings

    settings.agent_smith_enabled = False
    runtime = write_pilot_runtime
    result = await runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "blocked"
    assert result.state == WritePilotState.PLANNED.value
    assert "Agent Smith is disabled" in result.message


@pytest.mark.asyncio
async def test_write_pilot_blocked_when_write_pilot_disabled(write_pilot_runtime, tmp_git_repo):
    from freyja.config import settings

    settings.agent_smith_enabled = True
    settings.agent_smith_write_pilot_enabled = False
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "blocked"
    assert "write-pilot mode is disabled" in result.message


# ---------------------------------------------------------------------------
# Approval workflow tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_pilot_path_approval_required_and_denied(write_pilot_runtime, tmp_git_repo):
    async def _deny(approval_type, request_id, context):
        return ApprovalCallback("path", request_id, approved=False)

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_deny,
    )
    assert result.status == "failed"
    assert result.state in {WritePilotState.AWAITING_PATH_APPROVAL.value, WritePilotState.PLANNED.value}
    assert "Path approval denied" in result.message
    assert any(a["approval_type"] == "path" and not a["approved"] for a in result.approvals)


@pytest.mark.asyncio
async def test_write_pilot_content_approval_required_and_denied(write_pilot_runtime, tmp_git_repo):
    calls = []

    async def _deny_content(approval_type, request_id, context):
        calls.append(approval_type)
        if approval_type == "path":
            return ApprovalCallback("path", request_id, approved=True, target_path=context.get("target_path"))
        return ApprovalCallback("content", request_id, approved=False)

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_deny_content,
    )
    assert result.status == "failed"
    assert result.state == WritePilotState.AWAITING_CONTENT_APPROVAL.value
    assert "Content approval denied" in result.message
    assert "path" in calls and "content" in calls


@pytest.mark.asyncio
async def test_write_pilot_stage_approval_required_and_denied(write_pilot_runtime, tmp_git_repo):
    async def _approve_through_content(approval_type, request_id, context):
        if approval_type in {"path", "content"}:
            return ApprovalCallback(
                approval_type,
                request_id,
                approved=True,
                target_path=context.get("target_path"),
            )
        return ApprovalCallback("stage", request_id, approved=False, target_path=context.get("target_path"))

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_approve_through_content,
    )
    assert result.status == "failed"
    assert result.state == WritePilotState.AWAITING_STAGE_APPROVAL.value
    assert "Stage approval denied" in result.message
    target = tmp_git_repo / "docs" / "smith-pilot" / "test.md"
    assert not target.exists(), "Denied stage must roll back the write"


@pytest.mark.asyncio
async def test_write_pilot_commit_approval_required_and_denied(write_pilot_runtime, tmp_git_repo):
    async def _approve_through_stage(approval_type, request_id, context):
        if approval_type == "commit":
            return ApprovalCallback(
                approval_type,
                request_id,
                approved=False,
                target_path=context.get("target_path"),
                commit_message=context.get("commit_message"),
            )
        return ApprovalCallback(
            approval_type,
            request_id,
            approved=True,
            target_path=context.get("target_path"),
            commit_message=context.get("commit_message"),
        )

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_approve_through_stage,
    )
    assert result.status == "failed"
    assert result.state == WritePilotState.AWAITING_COMMIT_APPROVAL.value
    assert "Commit approval denied" in result.message
    target = tmp_git_repo / "docs" / "smith-pilot" / "test.md"
    assert not target.exists(), "Denied commit must roll back the write"


@pytest.mark.asyncio
async def test_write_pilot_approval_reuse_rejected(write_pilot_runtime, tmp_git_repo):
    reused = ApprovalCallback("path", "req-1", approved=True, target_path="docs/smith-pilot/test.md")

    async def _reuse(*args, **kwargs):
        return reused

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_reuse,
    )
    assert result.status == "failed"
    assert "Content approval denied" in result.message or "Stage approval denied" in result.message


@pytest.mark.asyncio
async def test_write_pilot_request_id_mismatch_rejected(write_pilot_runtime, tmp_git_repo):
    async def _wrong_request(approval_type, request_id, context):
        return ApprovalCallback(approval_type, "wrong-id", approved=True, target_path=context.get("target_path"))

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_wrong_request,
    )
    assert result.status == "failed"
    assert "Path approval denied" in result.message


@pytest.mark.asyncio
async def test_write_pilot_path_mismatch_rejected(write_pilot_runtime, tmp_git_repo):
    async def _wrong_path(approval_type, request_id, context):
        return ApprovalCallback(approval_type, request_id, approved=True, target_path="docs/smith-pilot/other.md")

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_wrong_path,
    )
    assert result.status == "failed"
    assert "Path approval denied" in result.message


@pytest.mark.asyncio
async def test_write_pilot_approval_type_mismatch_rejected(write_pilot_runtime, tmp_git_repo):
    async def _stage_as_path(approval_type, request_id, context):
        # Approve everything but pretend it is the wrong type.
        return ApprovalCallback("stage", request_id, approved=True, target_path=context.get("target_path"))

    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.md",
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=_stage_as_path,
    )
    assert result.status == "failed"
    assert "Path approval denied" in result.message


# ---------------------------------------------------------------------------
# Path restriction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_pilot_rejects_multiple_paths(write_pilot_runtime, tmp_git_repo):
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/a.md docs/smith-pilot/b.md",
        proposed_content="# a\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert result.state == WritePilotState.PLANNED.value


@pytest.mark.asyncio
async def test_write_pilot_rejects_absolute_path(write_pilot_runtime, tmp_git_repo):
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path=str(tmp_git_repo / "docs" / "smith-pilot" / "test.md"),
        proposed_content="# test\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert "absolute" in result.message.lower()


@pytest.mark.asyncio
async def test_write_pilot_rejects_parent_traversal(write_pilot_runtime, tmp_git_repo):
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/../secret.md",
        proposed_content="# secret\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert "parent directory traversal" in result.message


@pytest.mark.asyncio
async def test_write_pilot_rejects_hidden_file(write_pilot_runtime, tmp_git_repo):
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/.hidden.md",
        proposed_content="# hidden\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert "hidden" in result.message.lower()


@pytest.mark.asyncio
async def test_write_pilot_rejects_non_markdown(write_pilot_runtime, tmp_git_repo):
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/test.txt",
        proposed_content="text\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert "Markdown" in result.message


@pytest.mark.asyncio
async def test_write_pilot_rejects_symlink(write_pilot_runtime, tmp_git_repo):
    target = tmp_git_repo / "docs" / "smith-pilot" / "link.md"
    target.symlink_to(tmp_git_repo / "README.md")
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/link.md",
        proposed_content="# link\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert "symlink" in result.message.lower()


@pytest.mark.asyncio
async def test_write_pilot_rejects_protected_path(write_pilot_runtime, tmp_git_repo):
    result = await write_pilot_runtime.run_write_pilot(
        objective="test",
        target_path="docs/smith-pilot/env.md",
        proposed_content="# env\n",
        commit_message="test commit",
        request_id="req-1",
        approval_callback=None,
    )
    assert result.status == "failed"
    assert "protected" in result.message.lower() or "secret" in result.message.lower()


# ---------------------------------------------------------------------------
# Tool / write behavior tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_pilot_happy_path_writes_stages_commits(write_pilot_runtime, tmp_git_repo, approving_callback):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo

    result = await runtime.run_write_pilot(
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        request_id="req-happy",
        approval_callback=approving_callback,
    )
    assert result.status == "complete"
    assert result.state == WritePilotState.VERIFIED.value
    assert result.committed is True
    assert result.commit_hash is not None
    assert result.wrote_content is True
    assert result.staged is True

    target = tmp_git_repo / "docs" / "smith-pilot" / "note.md"
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
    assert log_proc.stdout.strip() == "add note"

    transitions = {t["from_state"]: t["to_state"] for t in result.state_transitions}
    assert WritePilotState.PLANNED.value in transitions
    assert WritePilotState.AWAITING_PATH_APPROVAL.value in transitions.values()
    assert WritePilotState.COMMITTED.value in transitions.values()
    assert WritePilotState.VERIFIED.value in transitions.values()


@pytest.mark.asyncio
async def test_write_pilot_resolves_symlinked_repo_root(tmp_path, approving_callback, monkeypatch):
    """A symlinked or non-canonical repo root must be resolved before containment checks."""
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_audit_enabled", False)

    real_repo = tmp_path / "real_repo"
    real_repo.mkdir()
    subprocess.run(["git", "init"], cwd=real_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=real_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=real_repo,
        check=True,
        capture_output=True,
    )
    (real_repo / "docs" / "smith-pilot").mkdir(parents=True)
    (real_repo / "docs" / "smith-pilot" / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "."], cwd=real_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=real_repo,
        check=True,
        capture_output=True,
    )

    link_repo = tmp_path / "link_repo"
    link_repo.symlink_to(real_repo)
    assert link_repo.is_symlink()

    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        f"""
allowed_root: {link_repo}
read_only_builtin_tools:
  - system_health
smith_read_only_tools:
  - repository_status
write_pilot_allowed_tools:
  - write_pilot_file_write
  - write_pilot_git_add
  - write_pilot_git_commit
write_pilot_sandbox: {link_repo}/docs/smith-pilot
auto_allowed_operations:
  - repository_status
  - no-op
approval_required_operations:
  - write_pilot_git_commit
  - write_pilot_file_write
  - write_pilot_git_add
prohibited_operations:
  - git_push
  - git_reset
max_retries: 2
secret_patterns:
  - "\\\\.env$"
"""
    )

    registry = ToolRegistry()
    register_smith_write_pilot_tools(registry)
    for tool in registry.list_tools(include_disabled=True):
        registry.set_enabled(tool.name, True)

    policy = AgentPolicy(str(policy_path))
    orchestrator = SmithOrchestrator(registry=registry, policy=policy, max_retries=2)
    runtime = SmithRuntime(
        orchestrator=orchestrator,
        policy=policy,
        max_steps=5,
        max_retries=2,
        audit_log_path=str(link_repo / "audit.jsonl"),
    )
    # Intentionally bind the non-resolved symlink path.
    runtime._repo_root_for_write_pilot = link_repo

    result = await runtime.run_write_pilot(
        objective="add note through symlink root",
        target_path="docs/smith-pilot/link-note.md",
        proposed_content="# link note\n",
        commit_message="add link note",
        request_id="req-symlink",
        approval_callback=approving_callback,
    )
    assert result.status == "complete"
    assert result.state == WritePilotState.VERIFIED.value
    target = real_repo / "docs" / "smith-pilot" / "link-note.md"
    assert target.read_text(encoding="utf-8") == "# link note\n"


@pytest.mark.asyncio
async def test_write_pilot_atomic_write_and_backup(write_pilot_runtime, tmp_git_repo, approving_callback):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo
    target = tmp_git_repo / "docs" / "smith-pilot" / "atomic.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("original\n", encoding="utf-8")

    result = await runtime.run_write_pilot(
        objective="update note",
        target_path="docs/smith-pilot/atomic.md",
        proposed_content="updated\n",
        commit_message="update note",
        request_id="req-atomic",
        approval_callback=approving_callback,
    )
    assert result.status == "complete"
    # Backups are created before overwriting an existing tracked file and then
    # cleaned up once the commit succeeds, so no backup remains after completion.
    assert result.commit_hash is not None
    assert not list((tmp_git_repo / "docs" / "smith-pilot").glob("atomic.md.bak.*"))


@pytest.mark.asyncio
async def test_write_pilot_removes_new_file_on_rollback(write_pilot_runtime, tmp_git_repo):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo

    async def _approve_through_content(approval_type, request_id, context):
        if approval_type in {"path", "content"}:
            return ApprovalCallback(
                approval_type,
                request_id,
                approved=True,
                target_path=context.get("target_path"),
            )
        return ApprovalCallback("stage", request_id, approved=False, target_path=context.get("target_path"))

    result = await runtime.run_write_pilot(
        objective="add note",
        target_path="docs/smith-pilot/new.md",
        proposed_content="# new\n",
        commit_message="add note",
        request_id="req-new",
        approval_callback=_approve_through_content,
    )
    assert result.status == "failed"
    assert result.rolled_back is True
    target = tmp_git_repo / "docs" / "smith-pilot" / "new.md"
    assert not target.exists()


@pytest.mark.asyncio
async def test_write_pilot_restores_existing_file_on_rollback(write_pilot_runtime, tmp_git_repo):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo
    target = tmp_git_repo / "docs" / "smith-pilot" / "existing.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("original\n", encoding="utf-8")

    async def _approve_through_content(approval_type, request_id, context):
        if approval_type in {"path", "content"}:
            return ApprovalCallback(
                approval_type,
                request_id,
                approved=True,
                target_path=context.get("target_path"),
            )
        return ApprovalCallback("stage", request_id, approved=False, target_path=context.get("target_path"))

    result = await runtime.run_write_pilot(
        objective="update note",
        target_path="docs/smith-pilot/existing.md",
        proposed_content="changed\n",
        commit_message="update note",
        request_id="req-existing",
        approval_callback=_approve_through_content,
    )
    assert result.status == "failed"
    assert result.rolled_back is True
    assert target.read_text(encoding="utf-8") == "original\n"


@pytest.mark.asyncio
async def test_write_pilot_does_not_touch_unrelated_dirty_files(write_pilot_runtime, tmp_git_repo, approving_callback):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo
    unrelated = tmp_git_repo / "README.md"
    unrelated.write_text("# changed\n", encoding="utf-8")
    before_mtime = unrelated.stat().st_mtime

    result = await runtime.run_write_pilot(
        objective="add note",
        target_path="docs/smith-pilot/clean.md",
        proposed_content="# clean\n",
        commit_message="add clean note",
        request_id="req-clean",
        approval_callback=approving_callback,
    )
    assert result.status == "complete"
    status_proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "README.md" in status_proc.stdout


@pytest.mark.asyncio
async def test_write_pilot_does_not_touch_unrelated_staged_files(write_pilot_runtime, tmp_git_repo, approving_callback):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo
    unrelated = tmp_git_repo / "other.md"
    unrelated.write_text("# other\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", "other.md"], cwd=tmp_git_repo, check=True, capture_output=True)

    result = await runtime.run_write_pilot(
        objective="add note",
        target_path="docs/smith-pilot/staged-clean.md",
        proposed_content="# staged-clean\n",
        commit_message="add staged clean note",
        request_id="req-staged-clean",
        approval_callback=approving_callback,
    )
    assert result.status == "complete"
    status_proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "other.md" in status_proc.stdout


@pytest.mark.asyncio
async def test_write_pilot_commit_failure_stops_safely(write_pilot_runtime, tmp_git_repo, approving_callback):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo
    # Prevent commit by using an empty commit message.
    result = await runtime.run_write_pilot(
        objective="add note",
        target_path="docs/smith-pilot/bad-commit.md",
        proposed_content="# bad commit\n",
        commit_message="",
        request_id="req-bad-commit",
        approval_callback=approving_callback,
    )
    assert result.status == "failed"
    assert "Commit failed" in result.message
    # The write should remain staged because we do not roll back after commit failure.
    status_proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "docs/smith-pilot/bad-commit.md" in status_proc.stdout


@pytest.mark.asyncio
async def test_write_pilot_audit_records_sanitized(write_pilot_runtime, tmp_git_repo, approving_callback):
    runtime = write_pilot_runtime
    assert runtime._repo_root_for_write_pilot == tmp_git_repo
    result = await runtime.run_write_pilot(
        objective="store token safely",
        target_path="docs/smith-pilot/safe.md",
        proposed_content="secret-token-12345\n",
        commit_message="add safe note",
        request_id="req-safe",
        approval_callback=approving_callback,
    )
    assert result.status == "complete"
    assert result.final_content == "<redacted>"
    assert result.original_content is None or result.original_content == "<redacted>"
    for record in result.audit_records:
        for key, value in _flatten(record).items():
            if isinstance(value, str) and "secret-token" in value:
                raise AssertionError("proposed content leaked into audit record")


def _flatten(obj, prefix=""):
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            result.update(_flatten(v, f"{prefix}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            result.update(_flatten(item, f"{prefix}[{i}]"))
    else:
        result[prefix] = obj
    return result


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


def test_write_pilot_endpoint_404_when_smith_disabled(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", False)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", False)
    response = test_client_write_pilot_enabled.post(
        "/agents/smith/write-pilot",
        json={
            "objective": "add note",
            "target_path": "docs/smith-pilot/note.md",
            "proposed_content": "# note\n",
            "commit_message": "add note",
        },
    )
    assert response.status_code == 404


def test_write_pilot_endpoint_403_when_write_pilot_disabled(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", False)
    response = test_client_write_pilot_enabled.post(
        "/agents/smith/write-pilot",
        json={
            "objective": "add note",
            "target_path": "docs/smith-pilot/note.md",
            "proposed_content": "# note\n",
            "commit_message": "add note",
        },
    )
    assert response.status_code == 403


def test_approval_admin_list_requires_loopback(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", True)
    non_loopback_client = TestClient(app, client=("192.0.2.1", 123))
    response = non_loopback_client.get("/agents/smith/approvals")
    assert response.status_code == 403


def test_approval_admin_404_when_smith_disabled(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", False)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", False)
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", False)
    response = test_client_write_pilot_enabled.get("/agents/smith/approvals")
    assert response.status_code == 404


def test_approval_admin_403_when_write_pilot_disabled(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", False)
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", False)
    response = test_client_write_pilot_enabled.get("/agents/smith/approvals")
    assert response.status_code == 403


def test_approval_admin_unknown_approval_id(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", False)
    response = test_client_write_pilot_enabled.get("/agents/smith/approvals/no-such-id")
    assert response.status_code == 404


def test_approval_lifecycle_via_endpoints(test_client_write_pilot_enabled, monkeypatch, tmp_path):
    from freyja.config import settings

    db_path = tmp_path / "approvals.sqlite3"
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_approval_db_path", str(db_path))
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", False)

    # Create a pending approval via the write-pilot endpoint.
    response = test_client_write_pilot_enabled.post(
        "/agents/smith/write-pilot",
        json={
            "objective": "add note",
            "target_path": "docs/smith-pilot/note.md",
            "proposed_content": "# note\n",
            "commit_message": "add note",
            "request_id": "req-api",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["state"] == "awaiting_path_approval"

    list_resp = test_client_write_pilot_enabled.get("/agents/smith/approvals")
    assert list_resp.status_code == 200
    approvals = list_resp.json()["approvals"]
    assert any(a["request_id"] == "req-api" and a["action"] == "path" for a in approvals)
    path_approval = next(a for a in approvals if a["request_id"] == "req-api" and a["action"] == "path")

    approve_resp = test_client_write_pilot_enabled.post(
        f"/agents/smith/approvals/{path_approval['id']}/approve",
        json={"actor": "operator-1"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    deny_resp = test_client_write_pilot_enabled.post(
        f"/agents/smith/approvals/{path_approval['id']}/deny",
        json={"reason": "already approved"},
    )
    assert deny_resp.status_code == 409

    get_resp = test_client_write_pilot_enabled.get(f"/agents/smith/approvals/{path_approval['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "approved"


def test_write_pilot_endpoint_rejects_non_markdown(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    response = test_client_write_pilot_enabled.post(
        "/agents/smith/write-pilot",
        json={
            "objective": "add note",
            "target_path": "docs/smith-pilot/note.txt",
            "proposed_content": "text\n",
            "commit_message": "add note",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "failed"
    assert "Markdown" in body["result"]["message"]


# ---------------------------------------------------------------------------
# Strict loopback guard tests
# ---------------------------------------------------------------------------


def _request_with_client(host: str | None, port: int = 12345):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/agents/smith/approvals",
        "headers": [],
        "client": (host, port) if host else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.mark.parametrize(
    "host,should_pass",
    [
        ("127.0.0.1", True),
        ("127.255.255.255", True),
        ("::1", True),
        ("192.0.2.1", False),
        ("2001:db8::1", False),
        ("localhost", False),
        ("not-an-ip", False),
        ("", False),
    ],
)
def test_approval_admin_loopback_strictness(monkeypatch, host, should_pass):
    from freyja.config import settings
    from freyja.main import _require_loopback

    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", True)
    request = _request_with_client(host or "")
    if should_pass:
        _require_loopback(request)
    else:
        with pytest.raises(HTTPException) as exc_info:
            _require_loopback(request)
        assert exc_info.value.status_code == 403


def test_approval_admin_spoofed_forwarded_header_rejected(test_client_write_pilot_enabled, monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", True)
    response = test_client_write_pilot_enabled.get(
        "/agents/smith/approvals",
        headers={
            "X-Forwarded-For": "192.0.2.1",
            "Forwarded": "for=192.0.2.2",
        },
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Resume payload mismatch tests
# ---------------------------------------------------------------------------


def _create_pending_path_approval(test_client_write_pilot_enabled, monkeypatch, tmp_path):
    from freyja.config import settings

    db_path = tmp_path / "approvals.sqlite3"
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_approval_db_path", str(db_path))
    monkeypatch.setattr(settings, "agent_smith_approval_loopback_only", False)

    create_resp = test_client_write_pilot_enabled.post(
        "/agents/smith/write-pilot",
        json={
            "objective": "add note",
            "target_path": "docs/smith-pilot/note.md",
            "proposed_content": "# note\n",
            "commit_message": "add note",
            "request_id": "req-mismatch",
        },
    )
    assert create_resp.status_code == 200
    approval = next(
        a for a in create_resp.json()["pending_approvals"]
        if a["request_id"] == "req-mismatch" and a["action"] == "path"
    )
    return approval, db_path


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", "req-other"),
        ("target_path", "docs/smith-pilot/other.md"),
        ("proposed_content", "# other\n"),
        ("commit_message", "other message"),
    ],
)
def test_resume_payload_mismatch_returns_409(
    test_client_write_pilot_enabled,
    monkeypatch,
    tmp_path,
    field,
    value,
):
    approval, _db = _create_pending_path_approval(test_client_write_pilot_enabled, monkeypatch, tmp_path)
    base = {
        "request_id": "req-mismatch",
        "approval_id": approval["id"],
        "objective": "add note",
        "target_path": "docs/smith-pilot/note.md",
        "proposed_content": "# note\n",
        "commit_message": "add note",
    }
    base[field] = value
    response = test_client_write_pilot_enabled.post("/agents/smith/write-pilot/resume", json=base)
    assert response.status_code == 409
    assert "mismatch" in response.json()["detail"].lower()


def test_resume_payload_correct_reaches_runtime(
    test_client_write_pilot_enabled,
    monkeypatch,
    tmp_path,
):
    approval, _db = _create_pending_path_approval(test_client_write_pilot_enabled, monkeypatch, tmp_path)
    approve_resp = test_client_write_pilot_enabled.post(
        f"/agents/smith/approvals/{approval['id']}/approve",
        json={"actor": "operator"},
    )
    assert approve_resp.status_code == 200
    response = test_client_write_pilot_enabled.post(
        "/agents/smith/write-pilot/resume",
        json={
            "request_id": "req-mismatch",
            "approval_id": approval["id"],
            "objective": "add note",
            "target_path": "docs/smith-pilot/note.md",
            "proposed_content": "# note\n",
            "commit_message": "add note",
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["state"] == "awaiting_content_approval"


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


def test_write_pilot_tools_registered_disabled_by_default():
    registry = ToolRegistry()
    register_smith_write_pilot_tools(registry)
    for name in ("write_pilot_file_write", "write_pilot_git_add", "write_pilot_git_commit"):
        tool = registry.get_tool(name)
        assert tool is not None, f"{name} not registered"
        assert tool.risk_level == ToolRiskLevel.CONTROLLED_WRITE
        assert tool.enabled is False


def test_write_pilot_tools_are_not_enabled_by_register_smith_tools():
    registry = ToolRegistry()
    register_smith_tools(registry)
    for name in ("write_pilot_file_write", "write_pilot_git_add", "write_pilot_git_commit"):
        tool = registry.get_tool(name)
        assert tool is not None
        assert tool.enabled is False
