"""Tests for Agent Smith dry-run runtime (SmithRuntime)."""

import json
import subprocess
from pathlib import Path
from unittest import mock
from uuid import uuid4

import pytest

from freyja.agents import (
    AgentPolicy,
    SmithOrchestrator,
    SmithRuntime,
    SmithPlan,
    SmithTask,
    TaskStatus,
    register_smith_tools,
)
from freyja.agents.runtime import _DRY_RUN_READ_ONLY_TOOLS
from freyja.config import settings
from freyja.tools.builtin import (
    _run_test_suite_implementation,
    register_builtin_tools,
)
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry
from freyja.main import app


@pytest.fixture
def test_client(tmp_path, monkeypatch):
    policy_path = tmp_path / "policy.yaml"
    repo_root = tmp_path / "freyja-os"
    repo_root.mkdir()
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
  - git_commit
  - bounded_file_write
prohibited_operations:
  - arbitrary_shell
  - arbitrary_filesystem_write
  - outside_root_access
  - execute_command
max_retries: 2
loop_detection:
  consecutive_identical_fingerprints: 4
  pair_repetitions: 2
  recent_window: 6
"""
    )
    monkeypatch.setattr(settings, "agent_smith_max_steps", 20)
    monkeypatch.setattr(settings, "agent_smith_dry_run_max_retries", 2)
    monkeypatch.setattr(settings, "agent_smith_audit_enabled", False)
    monkeypatch.setattr(settings, "agent_smith_policy_path", str(policy_path))
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def tmp_policy(tmp_path):
    repo_root = tmp_path / "freyja-os"
    repo_root.mkdir()
    policy_path = tmp_path / "policy.yaml"
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
  - git_commit
  - bounded_file_write
prohibited_operations:
  - arbitrary_shell
  - arbitrary_filesystem_write
  - outside_root_access
  - execute_command
max_retries: 2
loop_detection:
  consecutive_identical_fingerprints: 4
  pair_repetitions: 2
  recent_window: 6
"""
    )
    return str(policy_path)


@pytest.fixture
def registry(tmp_path, tmp_policy):
    tool_registry = ToolRegistry()
    register_builtin_tools(tool_registry)
    register_smith_tools(tool_registry)
    return tool_registry


@pytest.fixture
def runtime(registry, tmp_policy, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agent_smith_max_steps", 20)
    monkeypatch.setattr(settings, "agent_smith_dry_run_max_retries", 2)
    monkeypatch.setattr(settings, "agent_smith_audit_enabled", True)
    audit_log = tmp_path / "agent-smith-audit.jsonl"
    monkeypatch.setattr(settings, "agent_smith_audit_log_path", str(audit_log))
    policy = AgentPolicy(tmp_policy)
    orchestrator = SmithOrchestrator(registry=registry, policy=policy, max_retries=2)
    return SmithRuntime(
        orchestrator=orchestrator,
        policy=policy,
        max_steps=20,
        max_retries=2,
        audit_log_path=str(audit_log),
    )


@pytest.fixture
def controlled_registry(registry):
    for name in ("bounded_file_write", "git_commit"):
        if registry.get_tool(name) is not None:
            registry.unregister(name)
    registry.register(
        ToolDefinition(
            name="bounded_file_write",
            description="Write a bounded file to disk.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=True,
        ),
        lambda request: {"written": True},
    )
    registry.register(
        ToolDefinition(
            name="git_commit",
            description="Commit changes.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=True,
        ),
        lambda request: {"committed": True},
    )
    return registry


@pytest.fixture
def privileged_registry(registry):
    registry.register(
        ToolDefinition(
            name="restart_service",
            description="Restart a service.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.PRIVILEGED,
            enabled=True,
        ),
        lambda request: {"restarted": True},
    )
    return registry


@pytest.fixture
def spy_registry(registry):
    calls = []

    async def _repository_status(request: ToolExecutionRequest) -> dict:
        calls.append(("repository_status", request.arguments))
        return {"status": "ok"}

    registry.register(
        ToolDefinition(
            name="repository_status",
            description="Read-only git status.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
        ),
        _repository_status,
    )
    registry._calls = calls
    return registry


@pytest.fixture
def mock_run_test_suite(registry):
    calls = []

    async def _mock(request: ToolExecutionRequest) -> dict:
        calls.append((request.tool_name, request.arguments, request.request_id, request.actor))
        return {
            "returncode": 0,
            "passed": True,
            "stdout_tail": "1 passed in 0.01s",
            "stderr_tail": "",
        }

    if registry.get_tool("run_test_suite") is not None:
        registry.unregister("run_test_suite")
    registry.register(
        ToolDefinition(
            name="run_test_suite",
            description="Run the project pytest suite and return results.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
        ),
        _mock,
    )
    registry._run_test_suite_calls = calls
    return registry


@pytest.mark.asyncio
async def test_run_dry_read_only_objective_completes(runtime):
    summary = await runtime.run_dry("check repository status")

    assert summary.status == "complete"
    assert summary.completed_tasks == summary.total_tasks
    assert summary.failed_tasks == 0
    assert summary.approval_required_count == 0
    assert summary.objective == "check repository status"
    assert summary.actor == "agent_smith"
    assert summary.duration_ms is not None
    assert all(record["actor"] == "agent_smith" for record in summary.audit_records)


@pytest.mark.asyncio
async def test_run_dry_test_objective_uses_mocked_run_test_suite_no_recursive_pytest(
    runtime, mock_run_test_suite
):
    orchestrator = SmithOrchestrator(registry=mock_run_test_suite, policy=runtime.policy, max_retries=2)
    runtime = SmithRuntime(orchestrator=orchestrator, policy=runtime.policy, max_steps=5, max_retries=2)

    summary = await runtime.run_dry("run the test suite", actor="test_runner")

    assert summary.status == "complete"
    assert summary.completed_tasks == summary.total_tasks
    assert summary.failed_tasks == 0
    assert summary.approval_required_count == 0
    assert mock_run_test_suite._run_test_suite_calls
    tool_name, _arguments, request_id, actor = mock_run_test_suite._run_test_suite_calls[0]
    assert tool_name == "run_test_suite"
    assert request_id == summary.request_id
    assert actor == "test_runner"
    # Confirm no subprocess.run was invoked by this test through the real tool.
    assert all(
        record.get("details", {}).get("tool_name") != "pytest"
        for record in summary.audit_records
    )


@pytest.mark.asyncio
async def test_run_dry_rejects_controlled_write_tools(runtime, controlled_registry):
    runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(registry=controlled_registry, policy=runtime.policy, max_retries=2),
        policy=runtime.policy,
    )
    summary = await runtime.run_dry("commit changes")

    assert summary.approval_required_count >= 1
    assert any(
        record["outcome"] == "approval_required" for record in summary.audit_records
    )
    assert summary.status in {"approval_required", "needs_attention"}


@pytest.mark.asyncio
async def test_run_dry_rejects_privileged_tools(runtime, privileged_registry, monkeypatch):
    async def _plan_with_restart(*args, request_id=None, **kwargs):
        return SmithPlan(
            request_id=request_id or str(uuid4()),
            objective="restart service",
            tasks=[
                SmithTask(
                    description="Restart the service",
                    metadata={"tool": "restart_service"},
                ),
            ],
        )

    monkeypatch.setattr(SmithOrchestrator, "plan", _plan_with_restart)
    runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(registry=privileged_registry, policy=runtime.policy, max_retries=2),
        policy=runtime.policy,
    )
    summary = await runtime.run_dry("restart service", actor="operator")

    assert summary.status in {"needs_attention", "incomplete"}
    assert summary.failed_tasks >= 1 or summary.approval_required_count >= 1


@pytest.mark.asyncio
async def test_run_dry_blocks_tool_not_on_dry_run_whitelist(runtime, registry):
    registry.register(
        ToolDefinition(
            name="inspect",
            description="Inspect a file.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
        ),
        lambda request: {"content": "ok"},
    )
    runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(registry=registry, policy=runtime.policy, max_retries=2),
        policy=runtime.policy,
    )
    plan = await runtime.orchestrator.plan("inspect objective")
    plan.tasks = [type(plan.tasks[0])(description="Inspect", metadata={"tool": "inspect"})]

    result = await runtime._execute_dry_step(plan.tasks[0], plan.request_id, "agent_smith")
    assert result.success is False
    assert "not in the dry-run read-only whitelist" in result.error


@pytest.mark.asyncio
async def test_run_dry_loop_detection_stops_execution(runtime, mock_run_test_suite):
    orchestrator = SmithOrchestrator(
        registry=mock_run_test_suite, policy=runtime.policy, max_retries=2
    )
    runtime = SmithRuntime(
        orchestrator=orchestrator, policy=runtime.policy, max_steps=5, max_retries=2
    )
    plan = await runtime.orchestrator.plan("loop test")
    task = plan.tasks[0]
    task.id = "loop-task"
    runtime._loop_fingerprints = ["loop-task:loop test:run_test_suite:None"] * 5

    summary = await runtime.run_dry("loop test")

    assert summary.loop_detected_count >= 1
    assert summary.status == "loop_detected"
    assert any(record["action"] == "loop_detected" for record in summary.audit_records)


@pytest.mark.asyncio
async def test_run_dry_retry_limit_then_failure(runtime, registry):
    attempts = []

    async def _flaky(request: ToolExecutionRequest) -> dict:
        attempts.append(1)
        raise RuntimeError("always fails")

    if registry.get_tool("repository_status") is not None:
        registry.unregister("repository_status")
    registry.register(
        ToolDefinition(
            name="repository_status",
            description="Read-only git status.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
        ),
        _flaky,
    )
    runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(registry=registry, policy=runtime.policy, max_retries=2),
        policy=runtime.policy,
        max_retries=2,
    )
    summary = await runtime.run_dry("check repository status")

    assert len(attempts) == 2
    assert summary.failed_tasks >= 1
    assert summary.status == "needs_attention"


@pytest.mark.asyncio
async def test_run_dry_persists_sanitized_audit_records(runtime, tmp_path):
    audit_log = tmp_path / "audit.jsonl"
    runtime._audit_log_path = str(audit_log)
    await runtime.run_dry("verify token secret safe")

    assert audit_log.exists()
    lines = audit_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 0
    for line in lines:
        record = json.loads(line)
        assert "event_id" in record
        assert "timestamp" in record
        if "details" in record:
            _assert_no_secrets_in_value(record["details"])


@pytest.mark.asyncio
async def test_run_dry_actor_passed_through(runtime, mock_run_test_suite):
    orchestrator = SmithOrchestrator(
        registry=mock_run_test_suite, policy=runtime.policy, max_retries=2
    )
    runtime = SmithRuntime(orchestrator=orchestrator, policy=runtime.policy, max_steps=5, max_retries=2)
    summary = await runtime.run_dry("run the test suite", actor="test_runner")
    assert summary.actor == "test_runner"
    assert all(record["actor"] == "test_runner" for record in summary.audit_records)
    assert mock_run_test_suite._run_test_suite_calls


@pytest.mark.asyncio
async def test_run_dry_request_id_used_when_provided(runtime):
    request_id = str(uuid4())
    summary = await runtime.run_dry("check build", request_id=request_id)
    assert summary.request_id == request_id
    assert all(record["request_id"] == request_id for record in summary.audit_records)


@pytest.mark.asyncio
async def test_run_dry_max_steps_limits_execution(runtime, monkeypatch):
    async def _plan_with_many_steps(*args, request_id=None, **kwargs):
        return SmithPlan(
            request_id=request_id or str(uuid4()),
            objective="many steps",
            tasks=[
                SmithTask(description=f"Step {i}", metadata={"tool": "no-op"})
                for i in range(50)
            ],
        )

    monkeypatch.setattr(SmithOrchestrator, "plan", _plan_with_many_steps)
    runtime._max_steps = 3
    summary = await runtime.run_dry("many steps")

    assert summary.total_tasks == 50
    assert summary.completed_tasks <= 3
    assert summary.status in {"incomplete", "needs_attention"}


@pytest.mark.asyncio
async def test_run_dry_path_outside_root_blocked(runtime, tmp_path):
    plan = await runtime.orchestrator.plan("diff summary")
    task = plan.tasks[0]
    task.metadata["arguments"] = {"path": "/tmp"}

    result = await runtime._execute_dry_step(task, plan.request_id, "agent_smith")
    assert result.success is False
    assert "outside the allowed repository root" in result.error


def test_dry_run_read_only_whitelist_is_unchanging():
    assert _DRY_RUN_READ_ONLY_TOOLS == {
        "repository_status",
        "repository_diff_summary",
        "compile_project",
        "run_test_suite",
        "validate_diff",
    }


def _assert_no_secrets_in_value(value):
    if isinstance(value, dict):
        for k, v in value.items():
            assert "secret" not in str(k).lower() or v == "<redacted>"
            _assert_no_secrets_in_value(v)
    elif isinstance(value, list):
        for item in value:
            _assert_no_secrets_in_value(item)


@pytest.mark.asyncio
async def test_run_read_only_inspection_objective_completes(runtime):
    summary = await runtime.run_read_only("check repository status")

    assert summary.status == "complete"
    assert summary.completed_tasks == summary.total_tasks
    assert summary.failed_tasks == 0
    assert summary.escalated_tasks == 0
    assert summary.approval_required_count == 0
    assert summary.objective == "check repository status"
    assert summary.actor == "agent_smith"
    assert summary.duration_ms is not None
    assert summary.metadata is not None
    assert summary.metadata.get("classification") == "inspection"
    assert all(record["actor"] == "agent_smith" for record in summary.audit_records)
    assert any(record["action"] == "run_read_only" for record in summary.audit_records)


@pytest.mark.asyncio
async def test_run_read_only_validation_objective_completes(runtime, mock_run_test_suite):
    orchestrator = SmithOrchestrator(
        registry=mock_run_test_suite, policy=runtime.policy, max_retries=2
    )
    runtime = SmithRuntime(
        orchestrator=orchestrator, policy=runtime.policy, max_steps=5, max_retries=2
    )

    summary = await runtime.run_read_only("validate the test suite", actor="validator")

    assert summary.status == "complete"
    assert summary.completed_tasks == summary.total_tasks
    assert summary.failed_tasks == 0
    assert summary.approval_required_count == 0
    assert summary.metadata.get("classification") == "validation"
    assert summary.actor == "validator"
    assert all(record["actor"] == "validator" for record in summary.audit_records)
    assert mock_run_test_suite._run_test_suite_calls
    tool_name, _arguments, request_id, actor = mock_run_test_suite._run_test_suite_calls[0]
    assert tool_name == "run_test_suite"
    assert request_id == summary.request_id
    assert actor == "validator"


@pytest.mark.asyncio
async def test_run_read_only_diagnostics_objective_completes(runtime):
    summary = await runtime.run_read_only("diagnose repository health")

    assert summary.status == "complete"
    assert summary.completed_tasks == summary.total_tasks
    assert summary.failed_tasks == 0
    assert summary.approval_required_count == 0
    assert summary.metadata.get("classification") == "diagnostics"


@pytest.mark.asyncio
async def test_run_read_only_rejects_write_objectives_before_execution(runtime):
    summary = await runtime.run_read_only("commit the latest changes")

    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.completed_tasks == 0
    assert summary.failed_tasks == 0
    assert summary.approval_required_count == 0
    assert summary.metadata.get("classification") == "prohibited_write"
    assert "read-only execution refused" in summary.message


@pytest.mark.asyncio
async def test_run_read_only_rejects_privileged_objectives_before_execution(runtime):
    summary = await runtime.run_read_only("restart the director service")

    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "prohibited_privileged"
    assert "read-only execution refused" in summary.message


@pytest.mark.asyncio
async def test_run_read_only_rejects_ambiguous_objectives(runtime):
    summary = await runtime.run_read_only("do something useful")

    assert summary.status == "ambiguous"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "ambiguous"
    assert "ambiguous" in summary.message.lower()


@pytest.mark.asyncio
async def test_run_read_only_allows_system_health_tool(runtime, registry, monkeypatch):
    calls = []

    async def _system_health(request: ToolExecutionRequest) -> dict:
        calls.append((request.tool_name, request.request_id, request.actor))
        return {"healthy": True}

    if registry.get_tool("system_health") is not None:
        registry.unregister("system_health")
    registry.register(
        ToolDefinition(
            name="system_health",
            description="Check overall system health.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
        ),
        _system_health,
    )
    runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(registry=registry, policy=runtime.policy, max_retries=2),
        policy=runtime.policy,
    )

    async def _plan_with_health(*args, request_id=None, **kwargs):
        return SmithPlan(
            request_id=request_id or str(uuid4()),
            objective="check system health",
            tasks=[
                SmithTask(
                    description="Check system health",
                    metadata={"tool": "system_health"},
                ),
            ],
        )

    monkeypatch.setattr(SmithOrchestrator, "plan", _plan_with_health)

    summary = await runtime.run_read_only("check system health")

    assert summary.status == "complete"
    assert calls
    assert calls[0][0] == "system_health"
    assert calls[0][1] == summary.request_id
    assert calls[0][2] == "agent_smith"


@pytest.mark.asyncio
async def test_run_read_only_denies_controlled_write_tool(runtime, controlled_registry):
    runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(
            registry=controlled_registry, policy=runtime.policy, max_retries=2
        ),
        policy=runtime.policy,
    )
    summary = await runtime.run_read_only("write the config file")

    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "prohibited_write"


@pytest.mark.asyncio
async def test_run_read_only_denies_privileged_tool_at_runtime(runtime, privileged_registry, monkeypatch):
    async def _plan_with_restart(*args, request_id=None, **kwargs):
        return SmithPlan(
            request_id=request_id or str(uuid4()),
            objective="check status then restart",
            tasks=[
                SmithTask(
                    description="Restart the service",
                    metadata={"tool": "restart_service"},
                ),
            ],
        )

    monkeypatch.setattr(SmithOrchestrator, "plan", _plan_with_restart)
    fresh_runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(
            registry=privileged_registry, policy=runtime.policy, max_retries=2
        ),
        policy=runtime.policy,
    )
    summary = await fresh_runtime.run_read_only("check status then restart", actor="operator")

    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "prohibited_privileged"
    assert any(
        record["outcome"] == "started" and record.get("details", {}).get("classification") == "prohibited_privileged"
        for record in summary.audit_records
    )


@pytest.mark.asyncio
async def test_run_read_only_request_id_used_when_provided(runtime):
    request_id = str(uuid4())
    summary = await runtime.run_read_only("check repository status", request_id=request_id)
    assert summary.request_id == request_id
    assert all(record["request_id"] == request_id for record in summary.audit_records)
    assert summary.metadata.get("classification") == "inspection"


@pytest.mark.asyncio
async def test_run_read_only_persists_sanitized_audit_records(runtime, tmp_path):
    audit_log = tmp_path / "read-only-audit.jsonl"
    runtime._audit_log_path = str(audit_log)
    await runtime.run_read_only("verify secret token is safe")

    assert audit_log.exists()
    lines = audit_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 0
    for line in lines:
        record = json.loads(line)
        assert "event_id" in record
        assert "timestamp" in record
        if "details" in record:
            _assert_no_secrets_in_value(record["details"])


@pytest.mark.asyncio
async def test_run_read_only_does_not_invoke_write_tools(runtime, controlled_registry, monkeypatch):
    write_calls = []
    original_write = controlled_registry.get_tool("bounded_file_write")
    original_commit = controlled_registry.get_tool("git_commit")

    def _tracking_write(request: ToolExecutionRequest) -> dict:
        write_calls.append(request.tool_name)
        return {"written": True}

    def _tracking_commit(request: ToolExecutionRequest) -> dict:
        write_calls.append(request.tool_name)
        return {"committed": True}

    controlled_registry.unregister("bounded_file_write")
    controlled_registry.unregister("git_commit")
    controlled_registry.register(original_write, _tracking_write)
    controlled_registry.register(original_commit, _tracking_commit)

    async def _plan_with_write(*args, request_id=None, **kwargs):
        return SmithPlan(
            request_id=request_id or str(uuid4()),
            objective="inspect repository",
            tasks=[
                SmithTask(description="Status", metadata={"tool": "repository_status"}),
                SmithTask(description="Write note", metadata={"tool": "bounded_file_write"}),
                SmithTask(description="Commit", metadata={"tool": "git_commit"}),
            ],
        )

    monkeypatch.setattr(SmithOrchestrator, "plan", _plan_with_write)
    fresh_runtime = SmithRuntime(
        orchestrator=SmithOrchestrator(
            registry=controlled_registry, policy=runtime.policy, max_retries=2
        ),
        policy=runtime.policy,
        max_steps=10,
    )

    summary = await fresh_runtime.run_read_only("inspect repository")

    assert "bounded_file_write" not in write_calls
    assert "git_commit" not in write_calls
    assert summary.status in {"complete", "needs_attention", "incomplete"}
    assert summary.completed_tasks >= 1
    denied_tool_names = {
        record.get("details", {}).get("tool_name")
        for record in summary.audit_records
        if record.get("outcome") == "denied"
    }
    assert {"bounded_file_write", "git_commit"} <= denied_tool_names


@pytest.mark.asyncio
async def test_run_read_only_repository_unchanged(runtime, tmp_path, monkeypatch):
    repo_root = tmp_path / "work" / "freyja-os"
    repo_root.mkdir(parents=True)
    (repo_root / "README.md").write_text("initial")
    before = list(repo_root.rglob("*"))

    monkeypatch.setattr(settings, "agent_smith_audit_enabled", False)
    summary = await runtime.run_read_only("check repository status")

    after = list(repo_root.rglob("*"))
    assert after == before
    assert summary.status == "complete"


@pytest.mark.asyncio
async def test_run_read_only_negated_write_objective_allows_inspection(runtime):
    summary = await runtime.run_read_only("do not commit; show repository status")
    assert summary.status in {"complete", "incomplete"}
    assert summary.metadata.get("classification") != "prohibited_write"


@pytest.mark.asyncio
async def test_run_read_only_contrast_marker_resurrects_write_block(runtime):
    summary = await runtime.run_read_only("do not inspect only; commit the changes instead")
    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "prohibited_write"


@pytest.mark.asyncio
async def test_run_read_only_negated_privileged_objective_is_safe(runtime):
    summary = await runtime.run_read_only("never restart the director")
    assert summary.status in {"complete", "incomplete", "ambiguous"}
    assert summary.metadata.get("classification") != "prohibited_privileged"


@pytest.mark.asyncio
async def test_run_read_only_positive_write_remains_blocked(runtime):
    summary = await runtime.run_read_only("commit the latest changes")
    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "prohibited_write"


@pytest.mark.asyncio
async def test_run_read_only_positive_privileged_remains_blocked(runtime):
    summary = await runtime.run_read_only("restart the director service")
    assert summary.status == "blocked"
    assert summary.total_tasks == 0
    assert summary.metadata.get("classification") == "prohibited_privileged"


@pytest.mark.asyncio
async def test_run_read_only_read_only_allowlist_unchanging():
    from freyja.agents.runtime import _READ_ONLY_ALLOWLIST

    assert _READ_ONLY_ALLOWLIST == {
        "repository_status",
        "repository_diff_summary",
        "compile_project",
        "run_test_suite",
        "validate_diff",
        "system_health",
    }


@pytest.mark.asyncio
async def test_read_only_endpoint_gated_when_disabled(test_client):
    from freyja.config import settings

    original_enabled = settings.agent_smith_enabled
    original_read_only = settings.agent_smith_read_only_enabled
    try:
        settings.agent_smith_enabled = False
        settings.agent_smith_read_only_enabled = False
        response = test_client.post("/agents/smith/read-only", json={"objective": "check status"})
        assert response.status_code == 404

        settings.agent_smith_enabled = True
        settings.agent_smith_read_only_enabled = False
        response = test_client.post("/agents/smith/read-only", json={"objective": "check status"})
        assert response.status_code == 403
    finally:
        settings.agent_smith_enabled = original_enabled
        settings.agent_smith_read_only_enabled = original_read_only


@pytest.mark.asyncio
async def test_read_only_endpoint_allows_when_enabled(test_client, monkeypatch):
    from freyja.config import settings

    original_enabled = settings.agent_smith_enabled
    original_read_only = settings.agent_smith_read_only_enabled
    try:
        settings.agent_smith_enabled = True
        settings.agent_smith_read_only_enabled = True

        async def _mock_run_read_only(self, objective, /, actor=None, request_id=None):
            from freyja.agents.models import SmithRunSummary

            return SmithRunSummary(
                request_id=request_id or "mock-id",
                objective=objective,
                total_tasks=1,
                completed_tasks=1,
                failed_tasks=0,
                escalated_tasks=0,
                approval_required_count=0,
                status="complete",
                message="ok",
                actor=actor or "agent_smith",
                metadata={"classification": "inspection"},
            )

        monkeypatch.setattr("freyja.main.SmithRuntime.run_read_only", _mock_run_read_only)
        response = test_client.post(
            "/agents/smith/read-only",
            json={"objective": "check status", "actor": "tester", "request_id": "req-1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "complete"
        assert body["metadata"]["classification"] == "inspection"
        assert body["request_id"] == "req-1"
        assert body["actor"] == "tester"
    finally:
        settings.agent_smith_enabled = original_enabled
        settings.agent_smith_read_only_enabled = original_read_only


def test_enable_smith_read_only_script_exists_and_is_executable():
    script = Path(__file__).parent.parent / "scripts" / "enable-smith-read-only.sh"
    assert script.exists()
    assert script.stat().st_mode & 0o111


def test_disable_smith_script_exists_and_is_executable():
    script = Path(__file__).parent.parent / "scripts" / "disable-smith.sh"
    assert script.exists()
    assert script.stat().st_mode & 0o111


@pytest.mark.asyncio
async def test_run_test_suite_implementation_is_bounded_and_does_not_use_shell():
    """Production run_test_suite uses a fixed command array, explicit timeout, no shell."""
    request = ToolExecutionRequest(
        tool_name="run_test_suite",
        arguments={},
        request_id="bounded-test",
        actor="unit-test",
    )
    fake_completed = subprocess.CompletedProcess(
        args=["fake-pytest", "-q"],
        returncode=0,
        stdout="".join(f"line {i}\n" for i in range(21)) + "last line\n",
        stderr="err line\n",
    )
    with mock.patch("freyja.tools.builtin.subprocess.run", return_value=fake_completed) as run_mock:
        result = await _run_test_suite_implementation(request)

    run_mock.assert_called_once()
    _args, kwargs = run_mock.call_args
    assert kwargs.get("shell") is not True
    assert "timeout" in kwargs
    assert kwargs["timeout"] <= 120
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    assert kwargs.get("check") is False
    cmd = kwargs.get("args") or _args[0]
    assert isinstance(cmd, list)
    assert all(isinstance(part, str) for part in cmd)
    assert any("pytest" in part for part in cmd)
    assert result["passed"] is True
    assert result["returncode"] == 0
    assert "last line" in result["stdout_tail"]
    assert "first" not in result["stdout_tail"]
    assert result["stderr_tail"] == "err line"


@pytest.mark.asyncio
async def test_run_test_suite_implementation_reports_timeout_clearly():
    request = ToolExecutionRequest(
        tool_name="run_test_suite",
        arguments={},
        request_id="timeout-test",
        actor="unit-test",
    )
    with mock.patch(
        "freyja.tools.builtin.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=110),
    ) as run_mock:
        result = await _run_test_suite_implementation(request)

    assert "TimeoutExpired" in result["error"] or "timed out" in result["error"].lower()
    assert run_mock.call_args.kwargs.get("timeout") == 110
