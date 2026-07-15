import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from freyja.agents import (
    AgentPolicy,
    PolicyCheckResult,
    PolicyDecision,
    SmithOrchestrator,
    SmithPlan,
    SmithRunSummary,
    SmithStepResult,
    SmithTask,
    TaskStatus,
    register_smith_tools,
)
from freyja.agents.models import ApprovalStatus
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def registry(tmp_path):
    tool_registry = ToolRegistry()
    register_builtin_tools(tool_registry)
    register_smith_tools(tool_registry)
    return tool_registry


@pytest.fixture
def policy(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    repo_root = tmp_path / "freyja-os"
    repo_root.mkdir()
    policy_path.write_text(
        f"""
allowed_root: {repo_root}
read_only_builtin_tools:
  - system_health
  - list_models
  - recall_conversation
smith_read_only_tools:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
auto_allowed_operations:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
  - inspect
  - no-op
  - summarize
approval_required_operations:
  - git_commit
  - dependency_change
  - bounded_file_write
  - restart_freyja_director
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
max_retries: 3
secret_patterns:
  - '\\.env$'
  - '(^|/)secrets?(/|$)'
  - '\\.pem$'
  - '\\.key$'
  - 'token'
  - 'api_key'
  - 'password'
""",
        encoding="utf-8",
    )
    return AgentPolicy(str(policy_path))


@pytest.fixture
def orchestrator(registry, policy):
    return SmithOrchestrator(registry=registry, policy=policy, max_retries=3)


@pytest.fixture
def policy_with_extra_tools(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    repo_root = tmp_path / "freyja-os"
    repo_root.mkdir()
    policy_path.write_text(
        f"""
allowed_root: {repo_root}
read_only_builtin_tools:
  - system_health
  - list_models
  - recall_conversation
smith_read_only_tools:
  - repository_status
  - repository_diff_summary
  - run_test_suite
  - compile_project
  - validate_diff
  - flaky_tool
  - always_fail
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
  - dependency_change
  - bounded_file_write
  - restart_freyja_director
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
max_retries: 3
secret_patterns:
  - '\\.env$'
  - '(^|/)secrets?(/|$)'
  - '\\.pem$'
  - '\\.key$'
  - 'token'
  - 'api_key'
  - 'password'
""",
        encoding="utf-8",
    )
    return AgentPolicy(str(policy_path))


def test_models_task_defaults():
    task = SmithTask(description="test task")
    assert task.status == TaskStatus.PENDING
    assert task.approval_status == ApprovalStatus.NOT_REQUIRED
    assert task.id
    assert task.created_at


def test_plan_next_runnable_task_respects_dependencies():
    first = SmithTask(description="first")
    second = SmithTask(description="second", depends_on=[first.id])
    plan = SmithPlan(objective="ordered run", tasks=[first, second])
    assert plan.next_runnable_task() == first
    first.status = TaskStatus.COMPLETED
    assert plan.next_runnable_task() == second


def test_plan_is_complete_only_when_all_final():
    task = SmithTask(description="only task")
    plan = SmithPlan(objective="simple run", tasks=[task])
    assert not plan.is_complete()
    task.status = TaskStatus.COMPLETED
    assert plan.is_complete()
    task.status = TaskStatus.FAILED
    assert plan.is_complete()
    task.status = TaskStatus.ESCALATED
    assert plan.is_complete()


@pytest.mark.anyio
async def test_orchestrator_inspect_creates_plan(orchestrator, policy):
    plan = await orchestrator.inspect("run tests")
    assert isinstance(plan, SmithPlan)
    assert plan.objective == "run tests"
    assert plan.request_id
    assert any("test" in task.description.lower() for task in plan.tasks)


@pytest.mark.anyio
async def test_orchestrator_run_test_objective(orchestrator, policy):
    summary = await orchestrator.run("run tests")
    assert isinstance(summary, SmithRunSummary)
    assert summary.total_tasks == 1
    assert summary.completed_tasks == 1
    assert summary.status == "complete"


@pytest.mark.anyio
async def test_decompose_negated_commit_does_not_emit_commit_task(orchestrator):
    plan = await orchestrator.inspect("do not commit the current changes")
    assert not any(task.metadata.get("tool") == "git_commit" for task in plan.tasks)


@pytest.mark.anyio
async def test_decompose_commit_after_contrast_marker_emits_commit_task(orchestrator):
    plan = await orchestrator.inspect("do not commit yet, but commit the changes later")
    commit_tasks = [task for task in plan.tasks if task.metadata.get("tool") == "git_commit"]
    assert commit_tasks
    assert all(task.approval_status == ApprovalStatus.REQUIRED for task in commit_tasks)


@pytest.mark.anyio
async def test_decompose_positive_commit_task_requires_approval(orchestrator):
    plan = await orchestrator.inspect("commit the latest changes")
    commit_tasks = [task for task in plan.tasks if task.metadata.get("tool") == "git_commit"]
    assert commit_tasks
    assert all(task.approval_status == ApprovalStatus.REQUIRED for task in commit_tasks)


@pytest.mark.anyio
async def test_decompose_negated_commit_with_then_positive_is_blocked(orchestrator):
    plan = await orchestrator.inspect("never commit, then show repository status")
    assert not any(task.metadata.get("tool") == "git_commit" for task in plan.tasks)


@pytest.mark.anyio
async def test_retryable_failure_then_success(registry, policy_with_extra_tools):
    attempts = 0

    async def flaky_implementation(request: ToolExecutionRequest) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("transient")
        return {"ok": True}

    tool_registry = ToolRegistry()
    tool_registry.register(
        ToolDefinition(
            name="flaky_tool",
            description="Sometimes fails",
            risk_level=ToolRiskLevel.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
        ),
        flaky_implementation,
    )
    register_smith_tools(tool_registry)
    orchestrator = SmithOrchestrator(registry=tool_registry, policy=policy_with_extra_tools, max_retries=3)
    task = SmithTask(description="use flaky tool", metadata={"tool": "flaky_tool"})
    result = await orchestrator.execute_step(task, request_id="req-1")
    assert result.attempts == 2
    assert result.success
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.anyio
async def test_retry_limit_escalation(registry, policy_with_extra_tools):
    async def always_failing(request: ToolExecutionRequest) -> dict:
        raise RuntimeError("permanent")

    tool_registry = ToolRegistry()
    tool_registry.register(
        ToolDefinition(
            name="always_fail",
            description="Always fails",
            risk_level=ToolRiskLevel.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
        ),
        always_failing,
    )
    register_smith_tools(tool_registry)
    orchestrator = SmithOrchestrator(registry=tool_registry, policy=policy_with_extra_tools, max_retries=3)
    task = SmithTask(description="use failing tool", metadata={"tool": "always_fail"})
    result = await orchestrator.execute_step(task, request_id="req-2")
    assert result.attempts == 3
    assert not result.success
    assert task.status == TaskStatus.ESCALATED


@pytest.mark.anyio
async def test_approval_required_before_commit(orchestrator, policy):
    summary = await orchestrator.run("commit the changes")
    assert summary.approval_required_count >= 1
    assert summary.status == "approval_required"
    commit_task = [task for task in summary.audit_records if "git_commit" in str(task.get("details", {}))]
    assert summary.audit_records


@pytest.mark.anyio
async def test_prohibited_operation_rejected(orchestrator, policy):
    result = policy.check_operation("git_push")
    assert result.decision == PolicyDecision.DENY
    assert "prohibited" in result.reason.lower()


@pytest.mark.anyio
async def test_path_boundary_outside_root_rejected(policy):
    result = policy.check_path("/tmp/outside.txt")
    assert result.decision == PolicyDecision.DENY
    assert "outside" in result.reason.lower()


@pytest.mark.anyio
async def test_secret_path_rejected(policy):
    result = policy.check_path("/Users/freyja/freyja-os/secrets/api.key")
    assert result.decision == PolicyDecision.DENY
    assert "secret" in result.reason.lower()


@pytest.mark.anyio
async def test_audit_record_created_per_step(orchestrator):
    plan = await orchestrator.plan("run tests")
    task = plan.next_runnable_task()
    result = await orchestrator.execute_step(task, plan.request_id)
    assert result.audit_record is not None
    assert result.audit_record["action"].startswith("execute_step:")
    assert result.audit_record["request_id"] == plan.request_id


@pytest.mark.anyio
async def test_final_summary_records_audit_records(orchestrator):
    summary = await orchestrator.run("run tests")
    assert isinstance(summary, SmithRunSummary)
    assert summary.audit_records
    assert summary.request_id


@pytest.mark.anyio
async def test_privileged_tool_not_executable_by_smith(registry, policy):
    tool_registry = ToolRegistry()
    tool_registry.register(
        ToolDefinition(
            name="dangerous_shell",
            description="Run arbitrary shell command",
            risk_level=ToolRiskLevel.PRIVILEGED,
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        ),
        lambda request: {"ran": request.arguments.get("command")},
    )
    register_smith_tools(tool_registry)
    orchestrator = SmithOrchestrator(registry=tool_registry, policy=policy, max_retries=3)
    task = SmithTask(
        description="run shell",
        metadata={"tool": "dangerous_shell", "arguments": {"command": "rm -rf /"}},
    )
    result = await orchestrator.execute_step(task, request_id="req-3")
    assert not result.success
    assert "not in the Agent Smith whitelist" in result.error


@pytest.mark.anyio
async def test_loop_detection(policy):
    fingerprints = ["a", "a", "a", "a"]
    assert policy.detect_loop(fingerprints)
    fingerprints = ["a", "b", "a", "b", "a", "b"]
    assert policy.detect_loop(fingerprints)
    fingerprints = ["a", "b", "c", "d"]
    assert not policy.detect_loop(fingerprints)


@pytest.mark.anyio
async def test_approval_callback_allows_operation(policy, registry):
    async def approve(tool_name: str, description: str) -> bool:
        return True

    orchestrator = SmithOrchestrator(registry=registry, policy=policy, max_retries=3)
    orchestrator.register_approval_callback("dependency_change", approve)
    task = SmithTask(
        description="update dependencies",
        metadata={"tool": "dependency_change"},
        approval_status=ApprovalStatus.REQUIRED,
    )
    result = await orchestrator.execute_step(task, request_id="req-4")
    assert result.success
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.anyio
async def test_prohibited_arbitrary_shell(policy):
    result = policy.check_operation("arbitrary_shell")
    assert result.decision == PolicyDecision.DENY


@pytest.mark.anyio
async def test_policy_allows_read_only_whitelisted_tools(policy):
    result = policy.check_tool_permitted("repository_status", ToolRiskLevel.READ_ONLY)
    assert result.decision == PolicyDecision.ALLOW


@pytest.mark.anyio
async def test_policy_denies_non_whitelisted_read_only_tool(policy):
    result = policy.check_tool_permitted("unlisted_read_tool", ToolRiskLevel.READ_ONLY)
    assert result.decision == PolicyDecision.DENY
