"""Tests for the Agent Smith persistent approval store and provider."""

from __future__ import annotations

import asyncio
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from freyja.agents import AgentPolicy, ApprovalStoreError, SmithOrchestrator, SmithRuntime
from freyja.agents.approval_provider import PersistentApprovalProvider, make_resume_callback
from freyja.agents.approval_store import SmithApprovalStore
from freyja.agents.models import ApprovalRecordStatus
from freyja.tools.builtin import register_smith_write_pilot_tools
from freyja.tools.registry import ToolRegistry


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
  - git_push
  - git_reset
max_retries: 2
secret_patterns:
  - "\\\\.env$"
"""
    )
    return path


@pytest.fixture
def enabled_settings(monkeypatch):
    from freyja.config import settings

    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_write_pilot_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_audit_enabled", False)


@pytest.fixture
def runtime_with_provider(tmp_path: Path, policy_path: Path, tmp_git_repo: Path, enabled_settings) -> tuple[SmithRuntime, PersistentApprovalProvider, Path]:
    db_path = tmp_path / "approvals.sqlite3"
    registry = ToolRegistry()
    register_smith_write_pilot_tools(registry)
    for tool in registry.list_tools(include_disabled=True):
        registry.set_enabled(tool.name, True)
    policy = AgentPolicy(str(policy_path))
    orchestrator = SmithOrchestrator(registry=registry, policy=policy, max_retries=2)
    provider = PersistentApprovalProvider(SmithApprovalStore(str(db_path)))
    runtime = SmithRuntime(
        orchestrator=orchestrator,
        policy=policy,
        max_steps=5,
        max_retries=2,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    runtime._repo_root_for_write_pilot = tmp_git_repo
    runtime._approval_provider_for_write_pilot = provider
    return runtime, provider, db_path


@pytest.fixture
def approving_provider():
    class Approver:
        def __init__(self, provider: PersistentApprovalProvider):
            self.provider = provider

        async def approve_next(self, request_id: str, action: str) -> str:
            pending = [a for a in self.provider.store.list_pending() if a.request_id == request_id and a.action == action]
            assert pending, f"No pending {action} approval for {request_id}"
            self.provider.store.approve(pending[0].id)
            return pending[0].id

    return Approver


def test_store_creates_pending_record(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(
        request_id="req-1",
        action="path",
        target_path="docs/smith-pilot/note.md",
        content_hash="hash-content",
        commit_message_hash="hash-commit",
        summary="path approval",
    )
    assert record.status == ApprovalRecordStatus.PENDING
    assert record.request_id == "req-1"
    assert record.action == "path"
    assert record.target_path == "docs/smith-pilot/note.md"
    assert record.content_hash == "hash-content"
    assert record.commit_message_hash == "hash-commit"
    assert record.summary == "path approval"
    assert record.expires_at > record.created_at


def test_store_get_and_list(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    r1 = store.create(request_id="req-1", action="path", target_path="a.md", summary="s1")
    r2 = store.create(request_id="req-2", action="content", target_path="b.md", summary="s2")
    store.approve(r1.id)
    assert store.get(r1.id) is not None
    assert store.get("no-such-id") is None
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].id == r2.id


def test_store_approve_and_consume(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(
        request_id="req-1",
        action="path",
        target_path="a.md",
        content_hash="hash-content",
        summary="s",
    )
    approved = store.approve(record.id, actor="operator-1")
    assert approved.status == ApprovalRecordStatus.APPROVED
    assert approved.resolved_by == "operator-1"
    consumed = store.consume(
        record.id,
        request_id="req-1",
        action="path",
        target_path="a.md",
        content_hash="hash-content",
    )
    assert consumed.status == ApprovalRecordStatus.CONSUMED
    assert consumed.consumed_at is not None


def test_store_deny(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s")
    denied = store.deny(record.id, actor="operator-1", reason="not today")
    assert denied.status == ApprovalRecordStatus.DENIED
    assert denied.denial_reason == "not today"
    assert denied.resolved_by == "operator-1"


def test_store_cancel(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s")
    cancelled = store.cancel(record.id)
    assert cancelled.status == ApprovalRecordStatus.CANCELLED


def test_store_approve_unknown_raises(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    with pytest.raises(ApprovalStoreError) as exc_info:
        store.approve("no-such-id")
    assert exc_info.value.status_code == 404


def test_store_double_approval_raises(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s")
    store.approve(record.id)
    with pytest.raises(ApprovalStoreError) as exc_info:
        store.approve(record.id)
    assert exc_info.value.status_code == 409


def test_store_double_consumption_raises(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s")
    store.approve(record.id)
    store.consume(record.id, request_id="req-1", action="path", target_path="a.md")
    with pytest.raises(ApprovalStoreError) as exc_info:
        store.consume(record.id, request_id="req-1", action="path", target_path="a.md")
    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", "req-2"),
        ("action", "content"),
        ("target_path", "other.md"),
        ("content_hash", "wrong-hash"),
    ],
)
def test_store_consume_mismatch_raises(tmp_path: Path, field: str, value: str):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    kwargs = {
        "request_id": "req-1",
        "action": "path",
        "target_path": "a.md",
        "content_hash": "hash-content",
        "commit_message_hash": "hash-commit",
    }
    record = store.create(**kwargs, summary="s")
    store.approve(record.id)
    consume_kwargs = {
        "approval_id": record.id,
        "request_id": "req-1",
        "action": "path",
        "target_path": "a.md",
        "content_hash": "hash-content",
        "commit_message_hash": "hash-commit",
    }
    consume_kwargs[field] = value
    with pytest.raises(ApprovalStoreError) as exc_info:
        store.consume(**consume_kwargs)
    assert exc_info.value.status_code == 409


def test_store_commit_message_hash_mismatch(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(
        request_id="req-1",
        action="commit",
        target_path="a.md",
        commit_message_hash="hash-commit",
        summary="s",
    )
    store.approve(record.id)
    with pytest.raises(ApprovalStoreError) as exc_info:
        store.consume(
            record.id,
            request_id="req-1",
            action="commit",
            target_path="a.md",
            commit_message_hash="wrong-hash",
        )
    assert exc_info.value.status_code == 409


def test_store_expiration(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s", ttl_seconds=-1)
    assert record.expires_at <= record.created_at
    with pytest.raises(ApprovalStoreError) as exc_info:
        store.approve(record.id)
    assert exc_info.value.status_code == 410


def test_store_cleanup_expired(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s", ttl_seconds=-1)
    cleaned = store.cleanup_expired()
    assert cleaned == 1
    fetched = store.get(record.id)
    assert fetched is not None
    assert fetched.status == ApprovalRecordStatus.EXPIRED


def test_store_persists_across_instances(tmp_path: Path):
    db = str(tmp_path / "approvals.sqlite3")
    store1 = SmithApprovalStore(db)
    record = store1.create(request_id="req-1", action="path", target_path="a.md", summary="s")
    store2 = SmithApprovalStore(db)
    fetched = store2.get(record.id)
    assert fetched is not None
    assert fetched.request_id == "req-1"


def test_store_file_permissions(tmp_path: Path):
    db = tmp_path / "approvals.sqlite3"
    store = SmithApprovalStore(str(db))
    store.initialize()
    import os

    mode = db.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_store_parent_directory_permissions(tmp_path: Path):
    parent = tmp_path / "state" / "freyja"
    db = parent / "approvals.sqlite3"
    store = SmithApprovalStore(str(db))
    store.initialize()
    import os

    parent_mode = parent.stat().st_mode & 0o777
    assert parent_mode == 0o700, f"expected 0o700, got {oct(parent_mode)}"


def test_default_approval_db_path_is_outside_repo():
    from freyja.config import settings

    default_path = Path(settings.agent_smith_approval_db_path).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        default_path.relative_to(repo_root)
        assert False, f"default database path {default_path} is inside the repository"
    except ValueError:
        pass


def test_store_uses_configured_database_path(tmp_path: Path):
    custom_db = tmp_path / "custom.sqlite3"
    store = SmithApprovalStore(str(custom_db))
    store.create(request_id="req-1", action="path", target_path="a.md", summary="s")
    assert custom_db.exists()
    second = SmithApprovalStore(str(custom_db))
    assert second.list_pending()


def test_provider_creates_pending_and_callback_returns_false(tmp_path: Path):
    provider = PersistentApprovalProvider(SmithApprovalStore(str(tmp_path / "approvals.sqlite3")))
    callback = provider.approval_callback
    token = asyncio.run(callback("path", "req-1", {"target_path": "a.md", "summary": "path approval"}))
    assert token.approved is False
    assert token.approval_type == "path"
    assert token.request_id == "req-1"
    pending = provider.store.list_pending()
    assert len(pending) == 1
    assert pending[0].action == "path"


def test_provider_resume_consumes_approval(tmp_path: Path):
    provider = PersistentApprovalProvider(SmithApprovalStore(str(tmp_path / "approvals.sqlite3")))
    asyncio.run(
        provider.request_approval(
            "content",
            "req-1",
            {"target_path": "a.md", "content": "# note\n", "summary": "content approval"},
        )
    )
    pending = provider.store.list_pending()
    provider.store.approve(pending[0].id)
    token = asyncio.run(
        provider.resume_approval(
            pending[0].id,
            "content",
            "req-1",
            {"target_path": "a.md", "content": "# note\n"},
        )
    )
    assert token.approved is True
    record = provider.store.get(pending[0].id)
    assert record.status == ApprovalRecordStatus.CONSUMED


@pytest.mark.asyncio
async def test_write_pilot_happy_path_with_provider(
    runtime_with_provider,
    approving_provider,
):
    runtime, provider, _db = runtime_with_provider
    approver = approving_provider(provider)

    first = await runtime.run_write_pilot_with_provider(
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        request_id="req-happy",
        provider=provider,
    )
    assert first.result.state == "awaiting_path_approval"
    assert first.result.status == "failed"
    pending = [a for a in first.pending_approvals if a["request_id"] == "req-happy"]
    assert pending

    path_id = await approver.approve_next("req-happy", "path")
    second = await runtime.resume_write_pilot(
        request_id="req-happy",
        approval_id=path_id,
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        provider=provider,
    )
    assert second.result.state == "awaiting_content_approval"

    content_id = await approver.approve_next("req-happy", "content")
    third = await runtime.resume_write_pilot(
        request_id="req-happy",
        approval_id=content_id,
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        provider=provider,
    )
    assert third.result.state == "awaiting_stage_approval"

    stage_id = await approver.approve_next("req-happy", "stage")
    fourth = await runtime.resume_write_pilot(
        request_id="req-happy",
        approval_id=stage_id,
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        provider=provider,
    )
    assert fourth.result.state == "awaiting_commit_approval"

    commit_id = await approver.approve_next("req-happy", "commit")
    final = await runtime.resume_write_pilot(
        request_id="req-happy",
        approval_id=commit_id,
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        provider=provider,
    )
    assert final.result.state == "verified"
    assert final.result.committed is True
    assert final.result.commit_hash is not None


@pytest.mark.asyncio
async def test_write_pilot_resume_after_denial(
    runtime_with_provider,
    approving_provider,
):
    runtime, provider, _db = runtime_with_provider

    first = await runtime.run_write_pilot_with_provider(
        objective="add note",
        target_path="docs/smith-pilot/denied.md",
        proposed_content="# denied\n",
        commit_message="add denied note",
        request_id="req-denied",
        provider=provider,
    )
    pending = provider.store.list_pending()
    denied_record = next(a for a in pending if a.request_id == "req-denied" and a.action == "path")
    provider.store.deny(denied_record.id, reason="operator declined")

    second = await runtime.resume_write_pilot(
        request_id="req-denied",
        approval_id=denied_record.id,
        objective="add note",
        target_path="docs/smith-pilot/denied.md",
        proposed_content="# denied\n",
        commit_message="add denied note",
        provider=provider,
    )
    assert second.result.state == "awaiting_path_approval"
    assert "Path approval denied" in second.result.message
    assert second.result.wrote_content is False


@pytest.mark.asyncio
async def test_write_pilot_resume_after_expiration(
    runtime_with_provider,
):
    runtime, provider, _db = runtime_with_provider

    first = await runtime.run_write_pilot_with_provider(
        objective="add note",
        target_path="docs/smith-pilot/expired.md",
        proposed_content="# expired\n",
        commit_message="add expired note",
        request_id="req-expired",
        provider=provider,
    )
    pending = provider.store.list_pending()
    path_record = next(a for a in pending if a.request_id == "req-expired" and a.action == "path")
    # Force expiration by rewriting the record's expires_at in the database.
    conn = sqlite3.connect(provider.store.database_path)
    conn.execute(
        "UPDATE approvals SET expires_at = ? WHERE id = ?",
        ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), path_record.id),
    )
    conn.commit()
    conn.close()

    second = await runtime.resume_write_pilot(
        request_id="req-expired",
        approval_id=path_record.id,
        objective="add note",
        target_path="docs/smith-pilot/expired.md",
        proposed_content="# expired\n",
        commit_message="add expired note",
        provider=provider,
    )
    assert second.result.state == "awaiting_path_approval"
    assert "Path approval denied" in second.result.message or "expired" in second.result.message.lower()
    assert second.result.wrote_content is False


@pytest.mark.asyncio
async def test_write_pilot_unrelated_staged_files_untouched(
    runtime_with_provider,
    approving_provider,
    tmp_git_repo: Path,
):
    runtime, provider, _db = runtime_with_provider
    approver = approving_provider(provider)

    other = tmp_git_repo / "docs" / "other.md"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("# other\n")
    subprocess.run(["git", "add", "docs/other.md"], cwd=tmp_git_repo, check=True, capture_output=True)

    request_id = "req-unrelated"
    first = await runtime.run_write_pilot_with_provider(
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# note\n",
        commit_message="add note",
        request_id=request_id,
        provider=provider,
    )
    for action in ["path", "content", "stage", "commit"]:
        approval_id = await approver.approve_next(request_id, action)
        first = await runtime.resume_write_pilot(
            request_id=request_id,
            approval_id=approval_id,
            objective="add note",
            target_path="docs/smith-pilot/note.md",
            proposed_content="# note\n",
            commit_message="add note",
            provider=provider,
        )

    assert first.result.state == "verified"
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "docs/other.md" in status.stdout, "unrelated staged file should still be staged"


@pytest.mark.asyncio
async def test_provider_audit_records_exclude_content(runtime_with_provider):
    runtime, provider, _db = runtime_with_provider
    result = await runtime.run_write_pilot_with_provider(
        objective="add note",
        target_path="docs/smith-pilot/note.md",
        proposed_content="# TOP-SECRET-CONTENT\n",
        commit_message="add note",
        request_id="req-secret",
        provider=provider,
    )
    audit_blob = str(result.result.audit_records)
    assert "TOP-SECRET-CONTENT" not in audit_blob
    assert "# TOP-SECRET" not in audit_blob


@pytest.mark.asyncio
async def test_concurrent_approve_consumption(tmp_path: Path):
    store = SmithApprovalStore(str(tmp_path / "approvals.sqlite3"))
    record = store.create(request_id="req-1", action="path", target_path="a.md", summary="s")

    async def _approve_and_consume() -> bool:
        try:
            store.approve(record.id)
            store.consume(record.id, request_id="req-1", action="path", target_path="a.md")
            return True
        except ApprovalStoreError:
            return False

    results = await asyncio.gather(*[_approve_and_consume() for _ in range(5)])
    assert sum(results) == 1, "only one concurrent attempt should succeed"
    final = store.get(record.id)
    assert final.status == ApprovalRecordStatus.CONSUMED


def test_make_resume_callback(tmp_path: Path):
    provider = PersistentApprovalProvider(SmithApprovalStore(str(tmp_path / "approvals.sqlite3")))
    asyncio.run(
        provider.request_approval(
            "content",
            "req-1",
            {"target_path": "a.md", "content": "# note\n"},
        )
    )
    pending = provider.store.list_pending()
    provider.store.approve(pending[0].id)
    callback = make_resume_callback(provider, pending[0].id)
    token = asyncio.run(callback("content", "req-1", {"target_path": "a.md", "content": "# note\n"}))
    assert token.approved is True
