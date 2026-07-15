"""Agent Smith orchestration: inspect, plan, execute, validate, record,
retry/escalate, approval gating, and summarisation.
"""

import logging
from typing import Any, Awaitable, Callable

from freyja.tools.errors import ToolNotFoundError
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry

from .models import (
    ApprovalStatus,
    PolicyCheckResult,
    SmithPlan,
    SmithRunSummary,
    SmithStepResult,
    SmithTask,
    TaskStatus,
)
from .policy import AgentPolicy, PolicyDecision

logger = logging.getLogger(__name__)

StepImplementation = Callable[[SmithTask, str], Awaitable[dict[str, Any]]]


class SmithOrchestrator:
    """Agent Smith maintenance orchestrator implementing the policy-first cycle."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy: AgentPolicy | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._registry = registry or ToolRegistry()
        self._policy = policy or AgentPolicy()
        self._max_retries = max_retries if max_retries is not None else self._policy.max_retries
        self._audit_records: list[dict[str, Any]] = []
        self._loop_fingerprints: list[str] = []
        self._approval_callbacks: dict[str, Callable[[str, str], Awaitable[bool]]] = {}

    @property
    def policy(self) -> AgentPolicy:
        return self._policy

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    async def inspect(self, objective: str, *, request_id: str | None = None) -> SmithPlan:
        request_id = request_id or self._new_request_id()
        self._audit("inspect", "started", request_id=request_id, objective=objective)
        tasks = self._decompose(objective)
        plan = SmithPlan(request_id=request_id, objective=objective, tasks=tasks)
        self._audit("inspect", "planned", request_id=request_id, task_count=len(tasks))
        return plan

    async def plan(self, objective: str, *, request_id: str | None = None) -> SmithPlan:
        return await self.inspect(objective, request_id=request_id)

    async def run(self, objective: str, *, request_id: str | None = None) -> SmithRunSummary:
        plan = await self.plan(objective, request_id=request_id)
        while not plan.is_complete():
            task = plan.next_runnable_task()
            if task is None:
                break
            await self.execute_step(task, plan.request_id)
        return self.summarize(plan)

    async def execute_step(self, task: SmithTask, request_id: str) -> SmithStepResult:
        task.status = TaskStatus.IN_PROGRESS
        task.request_id = request_id
        task.updated_at = _utc_now()

        tool_name = task.metadata.get("tool")
        if tool_name is None:
            result = await self._execute_tool_step(task, request_id, "no-op", {})
        else:
            result = await self._execute_tool_step(task, request_id, tool_name, task.metadata.get("arguments", {}))

        if result.approval_required:
            task.status = TaskStatus.APPROVAL_REQUIRED
            task.approval_status = ApprovalStatus.REQUIRED
        elif result.success:
            task.status = TaskStatus.COMPLETED
            task.approval_status = ApprovalStatus.NOT_REQUIRED
        elif result.attempts >= self._max_retries:
            task.status = TaskStatus.ESCALATED
        else:
            task.status = TaskStatus.FAILED

        task.updated_at = _utc_now()
        self._loop_fingerprints.append(self._fingerprint(task, result))
        return result

    async def _execute_tool_step(
        self,
        task: SmithTask,
        request_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> SmithStepResult:
        permission = await self._can_invoke(tool_name, arguments)
        if permission.decision == PolicyDecision.DENY:
            return self._step_result(
                task,
                request_id,
                tool_name,
                success=False,
                error=permission.reason,
            )
        if permission.decision == PolicyDecision.APPROVE:
            callback = self._approval_callbacks.get(tool_name)
            approved = False
            if callback is not None:
                approved = await callback(tool_name, task.description)
            if not approved:
                return self._step_result(
                    task,
                    request_id,
                    tool_name,
                    success=False,
                    error=permission.reason,
                    approval_required=True,
                )
            if self._registry.get_tool(tool_name) is None:
                return self._step_result(
                    task,
                    request_id,
                    tool_name,
                    success=True,
                    output={"approved": True, "conceptual": True},
                )

        for attempt in range(1, self._max_retries + 1):
            try:
                output = await self._invoke_tool(tool_name, arguments, request_id)
                return self._step_result(
                    task,
                    request_id,
                    tool_name,
                    success=True,
                    attempts=attempt,
                    output=output,
                )
            except Exception as exc:  # noqa: BLE001
                retryable = self._is_retryable(exc)
                if not retryable or attempt >= self._max_retries:
                    return self._step_result(
                        task,
                        request_id,
                        tool_name,
                        success=False,
                        attempts=attempt,
                        error=str(exc),
                        retryable=retryable,
                    )

        return self._step_result(
            task,
            request_id,
            tool_name,
            success=False,
            error="Max retries exceeded",
        )

    def summarize(self, plan: SmithPlan) -> SmithRunSummary:
        completed = sum(1 for task in plan.tasks if task.status == TaskStatus.COMPLETED)
        failed = sum(1 for task in plan.tasks if task.status == TaskStatus.FAILED)
        escalated = sum(1 for task in plan.tasks if task.status == TaskStatus.ESCALATED)
        approvals = sum(
            1 for task in plan.tasks if task.status == TaskStatus.APPROVAL_REQUIRED
        ) + sum(
            1
            for task in plan.tasks
            if task.approval_status in {ApprovalStatus.REQUIRED, ApprovalStatus.REQUESTED}
        )
        if escalated > 0 or failed > 0:
            status = "needs_attention"
            message = "Run completed with failures or escalations."
        elif approvals > 0:
            status = "approval_required"
            message = "Run completed; approval is required for one or more changes."
        elif completed == len(plan.tasks):
            status = "complete"
            message = "All tasks completed successfully."
        else:
            status = "incomplete"
            message = "Run did not complete all tasks."
        summary = SmithRunSummary(
            request_id=plan.request_id,
            objective=plan.objective,
            total_tasks=len(plan.tasks),
            completed_tasks=completed,
            failed_tasks=failed,
            escalated_tasks=escalated,
            approval_required_count=approvals,
            status=status,
            message=message,
            audit_records=list(self._audit_records),
        )
        self._audit("summarize", status, request_id=plan.request_id, summary=summary.model_dump(mode="json"))
        return summary

    def register_approval_callback(
        self,
        operation: str,
        callback: Callable[[str, str], Awaitable[bool]],
    ) -> None:
        self._approval_callbacks[operation] = callback

    def _decompose(self, objective: str) -> list[SmithTask]:
        if "commit" in objective.lower() or "git commit" in objective.lower():
            return [
                SmithTask(
                    description="Review repository status",
                    metadata={"tool": "repository_status"},
                ),
                SmithTask(
                    description="Stage and commit changes",
                    metadata={"tool": "git_commit", "arguments": {"objective": objective}},
                    approval_status=ApprovalStatus.REQUIRED,
                ),
            ]
        if "test" in objective.lower():
            return [
                SmithTask(
                    description="Run project test suite",
                    metadata={"tool": "run_test_suite"},
                ),
            ]
        if "compile" in objective.lower() or "build" in objective.lower():
            return [
                SmithTask(
                    description="Compile project sources",
                    metadata={"tool": "compile_project"},
                ),
            ]
        return [
            SmithTask(
                description=f"Inspect objective: {objective}",
                metadata={"tool": "repository_status"},
            ),
            SmithTask(
                description="Produce final summary",
                metadata={"tool": "no-op"},
            ),
        ]

    def _step_result(
        self,
        task: SmithTask,
        request_id: str,
        tool_name: str | None,
        *,
        success: bool,
        attempts: int = 1,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        retryable: bool = False,
        approval_required: bool = False,
    ) -> SmithStepResult:
        outcome = "success" if success else "failure"
        if approval_required:
            outcome = "approval_required"
        audit_record = self._policy.record_audit(
            request_id=request_id,
            action=f"execute_step:{tool_name}",
            outcome=outcome,
            details={
                "task_id": task.id,
                "task_description": task.description,
                "tool_name": tool_name,
                "success": success,
                "error": error,
                "attempts": attempts,
                "approval_required": approval_required,
            },
        )
        self._audit_records.append(audit_record)
        return SmithStepResult(
            task_id=task.id,
            request_id=request_id,
            tool_name=tool_name,
            success=success,
            retryable=retryable,
            attempts=attempts,
            output=output or {},
            error=error,
            approval_required=approval_required,
            audit_record=audit_record,
        )

    async def _can_invoke(self, tool_name: str, arguments: dict[str, Any]) -> PolicyCheckResult:
        definition = self._registry.get_tool(tool_name)
        if tool_name == "no-op":
            return PolicyCheckResult(decision=PolicyDecision.ALLOW)
        if definition is None:
            operation_permission = self._policy.check_operation(tool_name)
            if operation_permission.decision in {PolicyDecision.ALLOW, PolicyDecision.APPROVE}:
                return operation_permission
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool '{tool_name}' is not registered.",
            )
        permission = self._policy.check_tool_permitted(tool_name, definition.risk_level)
        if permission.decision == PolicyDecision.DENY:
            return permission
        target_path = arguments.get("path") or arguments.get("target_path") or arguments.get("file_path")
        if target_path:
            path_permission = self._policy.check_path(target_path)
            if path_permission.decision == PolicyDecision.DENY:
                return path_permission
        return permission

    async def _invoke_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        if tool_name == "no-op":
            return {"noop": True}
        request = ToolExecutionRequest(
            tool_name=tool_name,
            arguments=arguments,
            request_id=request_id,
            actor="agent_smith",
        )
        result = await self._registry.execute(request)
        if not result.success:
            raise ToolInvocationError(result.public_error_message or result.error_code or "unknown")
        return result.output

    def _is_retryable(self, exc: Exception) -> bool:
        return not isinstance(exc, ToolNotFoundError) and not isinstance(exc, PolicyViolationError)

    def _fingerprint(self, task: SmithTask, result: SmithStepResult) -> str:
        return f"{task.id}:{task.description}:{result.tool_name}:{result.error}"

    def _audit(
        self,
        action: str,
        outcome: str,
        *,
        request_id: str,
        **details: Any,
    ) -> None:
        record = self._policy.record_audit(request_id, action, outcome, details)
        self._audit_records.append(record)

    @staticmethod
    def _new_request_id() -> str:
        from uuid import uuid4

        return str(uuid4())


class ToolInvocationError(Exception):
    """Raised when a registered tool fails."""


class PolicyViolationError(Exception):
    """Raised when Agent Smith policy would be violated."""


def _utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
