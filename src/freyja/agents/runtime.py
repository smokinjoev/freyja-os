"""Agent Smith dry-run runtime: read-only execution, policy enforcement,
loop detection, retry limits, and sanitized audit persistence.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from freyja.config import settings
from freyja.tools.errors import ToolNotFoundError
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry

from .models import AuditEvent, ObjectiveClass, SmithPlan, SmithRunSummary, SmithStepResult, SmithTask, TaskStatus
from .policy import AgentPolicy
from .smith import PolicyViolationError, SmithOrchestrator

logger = logging.getLogger(__name__)

_SANITIZED_TERMS = {"api key", "authorization", "bearer", "sk-", "token", "password", "secret"}

_DRY_RUN_READ_ONLY_TOOLS = frozenset(
    {
        "repository_status",
        "repository_diff_summary",
        "compile_project",
        "run_test_suite",
        "validate_diff",
    }
)

_READ_ONLY_ALLOWLIST = _DRY_RUN_READ_ONLY_TOOLS | {"system_health"}

_PROHIBITED_WRITE_KEYWORDS = frozenset(
    {
        "commit",
        "write",
        "modify",
        "edit",
        "overwrite",
        "patch",
        "delete",
        "remove",
        "stage",
        "add",
    }
)

_PROHIBITED_PRIVILEGED_KEYWORDS = frozenset(
    {
        "restart",
        "reboot",
        "shutdown",
        "terminate",
        "kill",
        "systemctl",
        "launchctl",
        "install",
        "upgrade",
        "update",
        "deploy",
        "shell",
        "command",
        "exec",
        "run ",
        "sudo",
        "chmod",
        "chown",
        "password",
        "secret",
        "credential",
        "token",
        "api key",
        "privilege",
        "elevated",
    }
)

_INSPECTION_KEYWORDS = frozenset(
    {
        "check",
        "status",
        "inspect",
        "view",
        "show",
        "list",
        "diff",
        "summary",
        "what",
    }
)

_VALIDATION_KEYWORDS = frozenset(
    {
        "test",
        "validate",
        "verify",
        "compile",
        "build",
        "lint",
        "format",
        "pytest",
    }
)

_DIAGNOSTICS_KEYWORDS = frozenset(
    {
        "health",
        "diagnose",
        "debug",
        "trace",
        "error",
        "failure",
        "why is",
        "what is wrong",
    }
)


class SmithRuntime:
    """Read-only dry-run executor for Agent Smith maintenance planning."""

    def __init__(
        self,
        orchestrator: SmithOrchestrator | None = None,
        policy: AgentPolicy | None = None,
        max_steps: int | None = None,
        max_retries: int | None = None,
        audit_log_path: str | None = None,
        read_only_tools: frozenset[str] | None = None,
    ) -> None:
        self._orchestrator = orchestrator or SmithOrchestrator()
        self._policy = policy or self._orchestrator.policy
        self._max_steps = max_steps if max_steps is not None else int(settings.agent_smith_max_steps)
        self._max_retries = max_retries if max_retries is not None else int(settings.agent_smith_dry_run_max_retries)
        self._max_retries = max(self._max_retries, 1)
        self._audit_log_path = audit_log_path or str(settings.agent_smith_audit_log_path)
        self._read_only_tools = read_only_tools or _READ_ONLY_ALLOWLIST
        self._audit_records: list[dict[str, Any]] = []
        self._loop_fingerprints: list[str] = []

    @property
    def orchestrator(self) -> SmithOrchestrator:
        return self._orchestrator

    @property
    def policy(self) -> AgentPolicy:
        return self._policy

    async def run_dry(
        self,
        objective: str,
        actor: str = "agent_smith",
        request_id: str | None = None,
    ) -> SmithRunSummary:
        start = time.monotonic()
        request_id = request_id or self._new_request_id()
        self._audit("run_dry", "started", request_id=request_id, actor=actor, objective=objective)

        plan = await self._orchestrator.plan(objective, request_id=request_id)
        steps_taken = 0
        loop_detected = False

        while not self._is_plan_terminal(plan) and steps_taken < self._max_steps:
            task = plan.next_runnable_task()
            if task is None:
                break
            result = await self._execute_dry_step(task, plan.request_id, actor)
            steps_taken += 1
            self._loop_fingerprints.append(self._fingerprint(task, result))
            if self._policy.detect_loop(self._loop_fingerprints):
                loop_detected = True
                task.status = TaskStatus.LOOP_DETECTED
                self._audit(
                    "loop_detected",
                    "blocked",
                    request_id=request_id,
                    actor=actor,
                    task_id=task.id,
                )
                break
            self._update_task_status(task, result)

        summary = self._summarize(plan, request_id, actor, loop_detected, steps_taken, start)
        self._audit("run_dry", summary.status, request_id=request_id, actor=actor, summary=summary.model_dump(mode="json"))
        self._persist_audit_records()
        return summary

    async def run_read_only(
        self,
        objective: str,
        actor: str | None = None,
        request_id: str | None = None,
    ) -> SmithRunSummary:
        """Execute a read-only objective using only the approved read-only allowlist.

        The public interface is ``run_read_only(objective, actor=None, request_id=None)``.
        If ``actor`` is omitted, the audit trail records the run as ``agent_smith``.

        * Classifies the objective and refuses ambiguous, write, or privileged requests
          before invoking any tool.
        * Only tools in ``_READ_ONLY_ALLOWLIST`` may be invoked.
        * Controlled-write and privileged tools are explicitly denied.
        * Sanitized audit records are persisted to the configured JSONL log.
        """
        start = time.monotonic()
        request_id = request_id or self._new_request_id()
        actor = actor or "agent_smith"
        classification = _classify_objective(objective)

        self._audit(
            "run_read_only",
            "started",
            request_id=request_id,
            actor=actor,
            objective=objective,
            classification=classification.value,
        )

        if classification == ObjectiveClass.AMBIGUOUS:
            summary = _classification_summary(
                request_id,
                objective,
                actor,
                classification,
                "Objective is ambiguous and cannot be executed in read-only mode.",
                start,
                self._audit_records,
            )
            self._audit("run_read_only", summary.status, request_id=request_id, actor=actor, summary=summary.model_dump(mode="json"))
            self._persist_audit_records()
            return summary

        if classification in {ObjectiveClass.PROHIBITED_WRITE, ObjectiveClass.PROHIBITED_PRIVILEGED}:
            summary = _classification_summary(
                request_id,
                objective,
                actor,
                classification,
                f"Objective classified as {classification.value}; read-only execution refused.",
                start,
                self._audit_records,
            )
            self._audit("run_read_only", summary.status, request_id=request_id, actor=actor, summary=summary.model_dump(mode="json"))
            self._persist_audit_records()
            return summary

        plan = await self._orchestrator.plan(objective, request_id=request_id)
        steps_taken = 0
        loop_detected = False

        while not self._is_plan_terminal(plan) and steps_taken < self._max_steps:
            task = plan.next_runnable_task()
            if task is None:
                break
            tool_name = task.metadata.get("tool") or "no-op"
            if not self._is_read_only_tool(tool_name):
                result = self._deny_non_read_only_tool(task, plan.request_id, actor, tool_name)
            else:
                result = await self._execute_dry_step(task, plan.request_id, actor)
            steps_taken += 1
            self._loop_fingerprints.append(self._fingerprint(task, result))
            if self._policy.detect_loop(self._loop_fingerprints):
                loop_detected = True
                task.status = TaskStatus.LOOP_DETECTED
                self._audit(
                    "loop_detected",
                    "blocked",
                    request_id=request_id,
                    actor=actor,
                    task_id=task.id,
                )
                break
            self._update_task_status(task, result)

        summary = self._summarize(plan, request_id, actor, loop_detected, steps_taken, start)
        summary.message = self._read_only_message(summary, classification)
        summary.metadata = {"classification": classification.value}
        self._audit("run_read_only", summary.status, request_id=request_id, actor=actor, summary=summary.model_dump(mode="json"))
        self._persist_audit_records()
        return summary

    def _is_read_only_tool(self, tool_name: str) -> bool:
        if tool_name == "no-op":
            return True
        return tool_name in self._read_only_tools or tool_name in _READ_ONLY_ALLOWLIST

    def _deny_non_read_only_tool(
        self,
        task: SmithTask,
        request_id: str,
        actor: str,
        tool_name: str,
    ) -> SmithStepResult:
        task.status = TaskStatus.IN_PROGRESS
        task.request_id = request_id
        error = f"Tool '{tool_name}' is not in the read-only allowlist."
        audit_record = self._record_step_audit(
            request_id,
            actor,
            tool_name,
            "denied",
            task,
            error=error,
        )
        return SmithStepResult(
            task_id=task.id,
            request_id=request_id,
            tool_name=tool_name,
            success=False,
            attempts=1,
            error=error,
            audit_record=audit_record,
            actor=actor,
        )

    def _read_only_message(self, summary: SmithRunSummary, classification: ObjectiveClass) -> str:
        if summary.status == "loop_detected":
            return "Read-only run terminated due to detected loop."
        if summary.status in {"needs_attention", "incomplete"}:
            return f"Read-only {classification.value} run completed with blocked or failed operations."
        if summary.status == "complete":
            return f"Read-only {classification.value} run completed successfully."
        return summary.message

    async def _execute_dry_step(
        self,
        task: SmithTask,
        request_id: str,
        actor: str,
    ) -> SmithStepResult:
        task.status = TaskStatus.IN_PROGRESS
        task.request_id = request_id
        tool_name = task.metadata.get("tool")
        if tool_name is None:
            tool_name = "no-op"
        arguments = task.metadata.get("arguments", {})

        permission = await self._can_invoke(tool_name, arguments)
        if permission.decision.value == "deny":
            audit_record = self._record_step_audit(
                request_id,
                actor,
                tool_name,
                "denied",
                task,
                error=permission.reason,
            )
            return SmithStepResult(
                task_id=task.id,
                request_id=request_id,
                tool_name=tool_name,
                success=False,
                attempts=1,
                error=permission.reason,
                audit_record=audit_record,
                actor=actor,
            )

        if permission.approval_required or permission.decision.value == "approve":
            audit_record = self._record_step_audit(
                request_id,
                actor,
                tool_name,
                "approval_required",
                task,
                error=permission.reason,
                approval_required=True,
            )
            return SmithStepResult(
                task_id=task.id,
                request_id=request_id,
                tool_name=tool_name,
                success=False,
                attempts=1,
                error=permission.reason,
                approval_required=True,
                audit_record=audit_record,
                actor=actor,
            )

        definition = self._orchestrator.registry.get_tool(tool_name)
        if tool_name == "no-op" or definition is None:
            audit_record = self._record_step_audit(
                request_id,
                actor,
                tool_name,
                "success",
                task,
                output={"conceptual": True},
            )
            return SmithStepResult(
                task_id=task.id,
                request_id=request_id,
                tool_name=tool_name,
                success=True,
                attempts=1,
                output={"conceptual": True},
                audit_record=audit_record,
                actor=actor,
            )

        last_error: str | None = None
        for attempt in range(1, self._max_retries + 1):
            step_start = time.monotonic()
            try:
                request = ToolExecutionRequest(
                    tool_name=tool_name,
                    arguments=arguments,
                    request_id=request_id,
                    actor=actor,
                )
                tool_result = await self._orchestrator.registry.execute(request)
                duration_ms = _elapsed_ms(step_start)

                if tool_result.success:
                    audit_record = self._record_step_audit(
                        request_id,
                        actor,
                        tool_name,
                        "success",
                        task,
                        output=tool_result.output,
                        attempts=attempt,
                        duration_ms=duration_ms,
                    )
                    return SmithStepResult(
                        task_id=task.id,
                        request_id=request_id,
                        tool_name=tool_name,
                        success=True,
                        attempts=attempt,
                        output=tool_result.output,
                        audit_record=audit_record,
                        duration_ms=duration_ms,
                        actor=actor,
                    )

                last_error = tool_result.public_error_message or tool_result.error_code or "unknown"
                retryable = tool_result.error_code not in {
                    "tool_not_found",
                    "tool_disabled",
                    "validation_error",
                } and not last_error.lower().startswith("policy violation")
                if not retryable or attempt >= self._max_retries:
                    audit_record = self._record_step_audit(
                        request_id,
                        actor,
                        tool_name,
                        "failure",
                        task,
                        error=last_error,
                        attempts=attempt,
                        duration_ms=duration_ms,
                    )
                    return SmithStepResult(
                        task_id=task.id,
                        request_id=request_id,
                        tool_name=tool_name,
                        success=False,
                        retryable=retryable,
                        attempts=attempt,
                        error=last_error,
                        audit_record=audit_record,
                        duration_ms=duration_ms,
                        actor=actor,
                    )
            except Exception as exc:  # noqa: BLE001
                duration_ms = _elapsed_ms(step_start)
                last_error = str(exc)
                retryable = self._is_retryable(exc)
                if not retryable or attempt >= self._max_retries:
                    audit_record = self._record_step_audit(
                        request_id,
                        actor,
                        tool_name,
                        "failure",
                        task,
                        error=last_error,
                        attempts=attempt,
                        duration_ms=duration_ms,
                    )
                    return SmithStepResult(
                        task_id=task.id,
                        request_id=request_id,
                        tool_name=tool_name,
                        success=False,
                        retryable=retryable,
                        attempts=attempt,
                        error=last_error,
                        audit_record=audit_record,
                        duration_ms=duration_ms,
                        actor=actor,
                    )

        error = "Max retries exceeded"
        audit_record = self._record_step_audit(
            request_id,
            actor,
            tool_name,
            "failure",
            task,
            error=error,
            attempts=self._max_retries,
        )
        return SmithStepResult(
            task_id=task.id,
            request_id=request_id,
            tool_name=tool_name,
            success=False,
            attempts=self._max_retries,
            error=error,
            audit_record=audit_record,
            actor=actor,
        )

    def _update_task_status(self, task: SmithTask, result: SmithStepResult) -> None:
        if result.approval_required:
            task.status = TaskStatus.APPROVAL_REQUIRED
        elif result.success:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.FAILED

    def _summarize(
        self,
        plan: SmithPlan,
        request_id: str,
        actor: str,
        loop_detected: bool,
        steps_taken: int,
        start: float,
    ) -> SmithRunSummary:
        completed = sum(1 for task in plan.tasks if task.status == TaskStatus.COMPLETED)
        failed = sum(1 for task in plan.tasks if task.status == TaskStatus.FAILED)
        escalated = sum(1 for task in plan.tasks if task.status == TaskStatus.ESCALATED)
        approvals = sum(1 for task in plan.tasks if task.status == TaskStatus.APPROVAL_REQUIRED)
        loops = sum(1 for task in plan.tasks if task.status == TaskStatus.LOOP_DETECTED) + (1 if loop_detected else 0)

        if loop_detected:
            status = "loop_detected"
            message = "Dry-run terminated due to detected loop."
        elif escalated > 0 or failed > 0:
            status = "needs_attention"
            message = "Dry-run completed with failures or blocked operations."
        elif approvals > 0:
            status = "approval_required"
            message = "Dry-run completed; approval would be required for one or more changes."
        elif completed == len(plan.tasks):
            status = "complete"
            message = "All read-only tasks completed successfully."
        else:
            status = "incomplete"
            message = "Dry-run did not complete all tasks."

        return SmithRunSummary(
            request_id=request_id,
            objective=plan.objective,
            total_tasks=len(plan.tasks),
            completed_tasks=completed,
            failed_tasks=failed,
            escalated_tasks=escalated,
            approval_required_count=approvals,
            loop_detected_count=loops,
            status=status,
            message=message,
            audit_records=list(self._audit_records),
            actor=actor,
            duration_ms=_elapsed_ms(start),
        )

    async def _can_invoke(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "no-op":
            from .policy import PolicyCheckResult, PolicyDecision

            return PolicyCheckResult(decision=PolicyDecision.ALLOW)
        definition = self._orchestrator.registry.get_tool(tool_name)
        if definition is None:
            return self._policy.check_tool_permitted(tool_name, ToolRiskLevel.READ_ONLY)
        if definition.risk_level != ToolRiskLevel.READ_ONLY:
            return self._policy.check_tool_permitted(tool_name, definition.risk_level)
        if tool_name not in self._read_only_tools and tool_name not in self._policy.smith_read_only_tools:
            from .policy import PolicyCheckResult, PolicyDecision

            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool '{tool_name}' is not in the dry-run read-only whitelist.",
            )
        target_path = arguments.get("path") or arguments.get("target_path") or arguments.get("file_path")
        if target_path:
            path_permission = self._policy.check_path(target_path)
            if path_permission.decision.value == "deny":
                return path_permission
        from .policy import PolicyCheckResult, PolicyDecision

        return PolicyCheckResult(decision=PolicyDecision.ALLOW)

    def _is_retryable(self, exc: Exception) -> bool:
        return not isinstance(exc, ToolNotFoundError) and not isinstance(exc, PolicyViolationError)

    def _fingerprint(self, task: SmithTask, result: SmithStepResult) -> str:
        return f"{task.id}:{task.description}:{result.tool_name}:{result.error}"

    def _is_plan_terminal(self, plan: SmithPlan) -> bool:
        return all(
            task.status
            in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.ESCALATED,
                TaskStatus.APPROVAL_REQUIRED,
                TaskStatus.LOOP_DETECTED,
            }
            for task in plan.tasks
        )

    def _record_step_audit(
        self,
        request_id: str,
        actor: str,
        tool_name: str | None,
        outcome: str,
        task: SmithTask,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        attempts: int = 1,
        approval_required: bool = False,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        details = {
            "actor": actor,
            "task_id": task.id,
            "task_description": task.description,
            "tool_name": tool_name,
            "success": outcome == "success",
            "error": error,
            "attempts": attempts,
            "approval_required": approval_required,
            "output": output or {},
        }
        if duration_ms is not None:
            details["duration_ms"] = duration_ms
        event = AuditEvent(
            request_id=request_id,
            actor=actor,
            action=f"dry_run_step:{tool_name or 'no-op'}",
            outcome=outcome,
            details=_sanitize_for_audit(details),
        )
        record = event.to_dict()
        self._audit_records.append(record)
        return record

    def _audit(
        self,
        action: str,
        outcome: str,
        *,
        request_id: str,
        actor: str = "agent_smith",
        **details: Any,
    ) -> dict[str, Any]:
        event = AuditEvent(
            request_id=request_id,
            actor=actor,
            action=action,
            outcome=outcome,
            details=_sanitize_for_audit(details),
        )
        record = event.to_dict()
        self._audit_records.append(record)
        return record

    def _persist_audit_records(self) -> None:
        if not bool(getattr(settings, "agent_smith_audit_enabled", True)):
            return
        path = Path(self._audit_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in self._audit_records:
                handle.write(json.dumps(record, separators=(",", ":"), default=str))
                handle.write("\n")

    @staticmethod
    def _new_request_id() -> str:
        import uuid

        return str(uuid.uuid4())


def _classify_objective(objective: str) -> ObjectiveClass:
    """Classify an objective before read-only execution begins.

    Order matters: write and privileged keywords are checked first so they
    always take precedence over inspection/validation/diagnostics keywords.
    If no decisive category is matched, the objective is ambiguous.
    """
    lowered = objective.lower()
    words = frozenset(re.findall(r"[a-z]+", lowered))

    if any(kw in lowered for kw in _PROHIBITED_WRITE_KEYWORDS) or _PROHIBITED_WRITE_KEYWORDS & words:
        return ObjectiveClass.PROHIBITED_WRITE

    multiword_privileged = {kw for kw in _PROHIBITED_PRIVILEGED_KEYWORDS if len(kw.split()) > 1 and kw in lowered}
    single_privileged = {kw for kw in _PROHIBITED_PRIVILEGED_KEYWORDS if len(kw.split()) == 1}
    if multiword_privileged or (single_privileged & words):
        return ObjectiveClass.PROHIBITED_PRIVILEGED

    inspection_count = sum(1 for kw in _INSPECTION_KEYWORDS if kw in lowered)
    validation_count = sum(1 for kw in _VALIDATION_KEYWORDS if kw in lowered)
    diagnostics_count = sum(1 for kw in _DIAGNOSTICS_KEYWORDS if kw in lowered)
    total_score = inspection_count + validation_count + diagnostics_count

    if total_score > 0 and total_score >= len(words) * 0.25:
        if diagnostics_count >= inspection_count and diagnostics_count >= validation_count:
            return ObjectiveClass.DIAGNOSTICS
        if validation_count >= inspection_count:
            return ObjectiveClass.VALIDATION
        return ObjectiveClass.INSPECTION

    return ObjectiveClass.AMBIGUOUS


def _classification_summary(
    request_id: str,
    objective: str,
    actor: str,
    classification: ObjectiveClass,
    message: str,
    start: float,
    audit_records: list[dict[str, Any]],
) -> SmithRunSummary:
    return SmithRunSummary(
        request_id=request_id,
        objective=objective,
        total_tasks=0,
        completed_tasks=0,
        failed_tasks=0,
        escalated_tasks=0,
        approval_required_count=0,
        status="blocked" if classification != ObjectiveClass.AMBIGUOUS else "ambiguous",
        message=message,
        audit_records=audit_records,
        actor=actor,
        duration_ms=_elapsed_ms(start),
        metadata={"classification": classification.value},
    )


def _sanitize_for_audit(value: Any) -> Any:
    """Recursively redact likely secrets from audit records."""
    if isinstance(value, dict):
        return {k: _sanitize_for_audit(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_audit(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(term in lowered for term in _SANITIZED_TERMS):
            return "<redacted>"
        return value
    return value


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
