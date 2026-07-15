"""Agent Smith dry-run runtime: read-only execution, policy enforcement,
loop detection, retry limits, and sanitized audit persistence.
"""

import hashlib
import json
import logging
import re
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freyja.config import settings
from freyja.tools.errors import ToolNotFoundError
from freyja.tools.models import ToolExecutionRequest, ToolExecutionResult, ToolRiskLevel
from freyja.tools.registry import ToolRegistry

from .models import (
    AuditEvent,
    ApprovalCallback,
    ApprovalRecord,
    ApprovalRecordStatus,
    ObjectiveClass,
    SmithPlan,
    SmithRunSummary,
    SmithStepResult,
    SmithTask,
    TaskStatus,
    WritePilotRequest,
    WritePilotResult,
    WritePilotResultWithApprovals,
    WritePilotState,
    WritePilotStateTransition,
    WritePilotApprovalRecord,
)

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
        "exec",
        "run ",
        "command",
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

# Density threshold for read-only classification. Lowered from 0.25 after
# the Milestone 14 pilot showed that natural-language objectives with many
# neutral words (e.g. "Check the Director service health endpoint...") were
# incorrectly classified as ambiguous despite explicit read-only intent.
_READ_ONLY_DENSITY_THRESHOLD = 0.15

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
        summary.plan = plan
        self._audit("run_dry", summary.status, request_id=request_id, actor=actor, summary=summary.model_dump(mode="json"))
        self._persist_audit_records()
        return summary

    async def run_write_pilot(
        self,
        objective: str,
        target_path: str,
        proposed_content: str,
        commit_message: str,
        actor: str | None = None,
        request_id: str | None = None,
        approval_callback: Callable[..., Awaitable[ApprovalCallback]] | None = None,
    ) -> WritePilotResult:
        """Execute a strictly bounded Agent Smith approved-write pilot.

        The write pilot may only modify a single Markdown file under
        ``docs/smith-pilot/``.  Each mutating action requires a separate,
        one-time approval via ``approval_callback``:

        1. target file path,
        2. exact proposed content,
        3. staging the approved file,
        4. commit message and commit execution.

        Approvals cannot be reused across requests, paths, or actions.  On any
        failure before a successful commit, the original file state is restored
        and the approved target is unstaged; unrelated working-tree state is left
        untouched.  Audit records are sanitized and never include the proposed
        content.
        """
        start = time.monotonic()
        actor = actor or "agent_smith"
        request_id = request_id or self._new_request_id()
        result = _WritePilotRun(
            runtime=self,
            objective=objective,
            target_path=target_path,
            proposed_content=proposed_content,
            commit_message=commit_message,
            actor=actor,
            request_id=request_id,
            approval_callback=approval_callback,
            start=start,
        )
        return await result.execute()

    async def run_write_pilot_with_provider(
        self,
        objective: str,
        target_path: str,
        proposed_content: str,
        commit_message: str,
        actor: str | None = None,
        request_id: str | None = None,
        provider: "PersistentApprovalProvider | None" = None,
    ) -> "WritePilotResultWithApprovals":
        """Run the write pilot using a persistent approval provider.

        The run creates pending approval records for each gate and halts at the
        first gate that is not yet approved.  The caller must then approve the
        returned ``approval_id`` and call ``resume_write_pilot`` with the same
        ``request_id`` and ``approval_id`` to advance the workflow.
        """
        from .approval_provider import PersistentApprovalProvider

        resolved_provider = provider or PersistentApprovalProvider()
        self._approval_provider_for_write_pilot = resolved_provider
        result = await self.run_write_pilot(
            objective=objective,
            target_path=target_path,
            proposed_content=proposed_content,
            commit_message=commit_message,
            actor=actor,
            request_id=request_id,
            approval_callback=resolved_provider.approval_callback,
        )
        pending = [
            a for a in resolved_provider.store.list_pending()
            if a.request_id == result.request_id
        ]
        return WritePilotResultWithApprovals(
            result=result,
            pending_approvals=[a.model_dump(mode="json") for a in pending],
            provider=resolved_provider,
        )

    async def resume_write_pilot(
        self,
        request_id: str,
        approval_id: str,
        objective: str,
        target_path: str,
        proposed_content: str,
        commit_message: str,
        actor: str | None = None,
        provider: "PersistentApprovalProvider | None" = None,
    ) -> "WritePilotResultWithApprovals":
        """Resume a write-pilot run after an approval has been granted.

        The provider consumes the approved record exactly once.  If the approved
        gate is not the next expected gate, the approval is rejected.  The run
        then continues until completion or the next awaiting gate.
        """
        from .approval_provider import PersistentApprovalProvider, make_resume_callback

        resolved_provider = provider or PersistentApprovalProvider()
        callback = make_resume_callback(resolved_provider, approval_id=approval_id, actor=actor or "agent_smith")
        result = await self.run_write_pilot(
            objective=objective,
            target_path=target_path,
            proposed_content=proposed_content,
            commit_message=commit_message,
            actor=actor,
            request_id=request_id,
            approval_callback=callback,
        )
        pending = [
            a for a in resolved_provider.store.list_pending()
            if a.request_id == request_id
        ]
        return WritePilotResultWithApprovals(
            result=result,
            pending_approvals=[a.model_dump(mode="json") for a in pending],
            provider=resolved_provider,
        )

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
        summary.plan = plan
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


_CONTRAST_MARKERS = frozenset({"but", "however", "then", "and then"})

_NEGATION_PATTERNS = [
    # Strip a single negated clause up to the next clause boundary so that
    # "do not A, B, or C." cannot leak prohibited verbs into classification,
    # while contrast markers such as "but", "however", "then", and "and then"
    # terminate the negated clause so later positive instructions are visible.
    re.compile(r"\b(do\s+not|don'?t|never|no)\b[^.!?;]*?(?:(?:,\s*)?(?:but|however|then|and\s+then)\b|(?=[.!?;])|[.!?;]|$)"),
]


def _strip_negated_phrases(objective: str) -> str:
    """Remove negated instruction clauses so their prohibited keywords are not matched.

    Negation is clause-scoped: a contrast marker (but/however/then/and then)
    ends the negated clause, so a positive instruction after the marker is still
    visible to classification. This keeps "Do not inspect only; commit the
    changes instead." classified as a prohibited write objective.
    """
    result = objective.lower()
    for pattern in _NEGATION_PATTERNS:
        result = pattern.sub("", result)
    return result


def _strip_read_only_action_verbs(objective: str) -> str:
    """Neutralize 'run', 'execute', and 'command' when they frame approved read-only actions.

    This prevents read-only requests such as 'run the test suite', 'execute
    compile and diff checks', or 'run a health check command' from being
    misclassified as privileged shell commands, while keeping arbitrary
    command requests prohibited.
    """
    result = objective.lower()
    allowed_next = _INSPECTION_KEYWORDS | _VALIDATION_KEYWORDS | _DIAGNOSTICS_KEYWORDS

    # Single-word privileged keywords that must abort neutralization if they
    # appear between 'run'/'execute' and the read-only keyword. This keeps
    # phrases like "run this shell command" prohibited.
    privileged_stoppers = {
        kw.strip()
        for kw in _PROHIBITED_PRIVILEGED_KEYWORDS
        if len(kw.split()) == 1 and kw.strip() not in {"run", "execute"}
    }
    stopper_group = "|".join(re.escape(kw) for kw in privileged_stoppers)
    kw_group = "|".join(re.escape(kw) for kw in allowed_next)

    # Neutralize "run"/"execute" followed by up to five neutral words and then
    # a read-only keyword (e.g. "run the project test suite",
    # "execute compile and diff checks"). Abort if a privileged stopper is met first.
    pattern = re.compile(
        rf"\b(run|execute)\s+(?:(?!{stopper_group}\b)\b\w+\b\s+){{0,5}}?\b({kw_group})\b",
        re.IGNORECASE,
    )
    result = pattern.sub(r"\2", result)

    # "command" following read-only nouns (e.g. "health check command",
    # "test command") is neutralized; standalone "command" stays privileged.
    for kw in allowed_next:
        result = re.sub(rf"\b{re.escape(kw)}(?:\s+check)?\s+command\b", kw, result)
    return result


def _has_negated_write_language(objective: str) -> bool:
    """Return True when a negated write instruction is present and stripped."""
    lowered = objective.lower()
    stripped = _strip_negated_phrases(lowered)
    return stripped != lowered


_DIAGNOSTICS_SERVICE_WORDS = frozenset({"service", "process", "endpoint", "runtime", "director"})


def _classify_objective(objective: str) -> ObjectiveClass:
    """Classify an objective before read-only execution begins.

    Negated safety instructions such as "do not modify" or "no secret
    access" are ignored. Write and privileged keywords are checked next so
    they take precedence over inspection/validation/diagnostics keywords.
    If no decisive category is matched, the objective is ambiguous.

    Negated write language plus a clear remaining read-only objective is
    allowed to classify as the appropriate read-only category even when the
    keyword density is below the normal threshold (Pilot 7). Mixed health
    and service/process diagnostics are classified as diagnostics and
    planned with system_health first (Pilot 3).
    """
    lowered = objective.lower()
    neutralized = _strip_read_only_action_verbs(_strip_negated_phrases(lowered))
    words = frozenset(re.findall(r"[a-z]+", neutralized))

    single_write = {kw for kw in _PROHIBITED_WRITE_KEYWORDS if len(kw.split()) == 1}
    multiword_write = {kw for kw in _PROHIBITED_WRITE_KEYWORDS if len(kw.split()) > 1 and kw in neutralized}
    if multiword_write or any(re.search(rf"\b{re.escape(kw)}\b", neutralized) for kw in single_write):
        return ObjectiveClass.PROHIBITED_WRITE

    multiword_privileged = {kw for kw in _PROHIBITED_PRIVILEGED_KEYWORDS if len(kw.split()) > 1 and kw in neutralized}
    single_privileged = {kw for kw in _PROHIBITED_PRIVILEGED_KEYWORDS if len(kw.split()) == 1}
    if multiword_privileged or any(re.search(rf"\b{re.escape(kw)}\b", neutralized) for kw in single_privileged):
        return ObjectiveClass.PROHIBITED_PRIVILEGED

    inspection_count = sum(1 for kw in _INSPECTION_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", lowered))
    validation_count = sum(1 for kw in _VALIDATION_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", lowered))
    diagnostics_count = sum(1 for kw in _DIAGNOSTICS_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", lowered))
    has_service = any(re.search(rf"\b{re.escape(kw)}\b", neutralized) for kw in _DIAGNOSTICS_SERVICE_WORDS)

    # Mixed health/service-process objectives should classify as diagnostics even
    # when plain inspection words outnumber core diagnostics words (Pilot 3).
    if diagnostics_count > 0 and has_service:
        diagnostics_count += sum(
            1 for kw in _DIAGNOSTICS_SERVICE_WORDS if re.search(rf"\b{re.escape(kw)}\b", lowered)
        )

    total_score = inspection_count + validation_count + diagnostics_count

    if total_score == 0:
        return ObjectiveClass.AMBIGUOUS

    density = total_score / len(words)
    has_negated_write = _has_negated_write_language(objective)
    allows_fallback = density >= _READ_ONLY_DENSITY_THRESHOLD or has_negated_write
    diagnostics_dominant = diagnostics_count >= inspection_count and diagnostics_count >= validation_count
    service_diagnostics = diagnostics_dominant and has_service

    if density >= _READ_ONLY_DENSITY_THRESHOLD or (has_negated_write and total_score >= 2):
        if service_diagnostics:
            return ObjectiveClass.DIAGNOSTICS
        if diagnostics_dominant:
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


class _WritePilotRun:
    """State-machine executor for a single Agent Smith approved-write pilot."""

    def __init__(
        self,
        runtime: SmithRuntime,
        objective: str,
        target_path: str,
        proposed_content: str,
        commit_message: str,
        actor: str,
        request_id: str,
        approval_callback: "ApprovalCallback | None",
        start: float,
    ) -> None:
        self._runtime = runtime
        self._objective = objective
        self._target_path = target_path
        self._proposed_content = proposed_content
        self._commit_message = commit_message
        self._actor = actor
        self._request_id = request_id
        self._approval_callback = approval_callback
        self._provider: "PersistentApprovalProvider | None" = getattr(
            runtime, "_approval_provider_for_write_pilot", None
        )
        self._start = start
        self._state = WritePilotState.PLANNED
        self._repo_root = Path(
            getattr(runtime, "_repo_root_for_write_pilot", None)
            or getattr(runtime.policy, "_allowed_root", None)
            or Path(__file__).resolve().parents[3]
        ).resolve()
        self._approvals: list[dict[str, Any]] = []
        self._transitions: list[dict[str, Any]] = []
        self._audit_records: list[dict[str, Any]] = []
        self._original_content: str | None = None
        self._backup_path: Path | None = None
        self._file_existed = False
        self._final_content: str | None = None
        self._commit_hash: str | None = None
        self._tool_results: list[ToolExecutionResult] = []
        self._rolled_back = False

    async def execute(self) -> WritePilotResult:
        if not settings.agent_smith_enabled:
            return self._finish("blocked", "Agent Smith is disabled.")
        if not settings.agent_smith_write_pilot_enabled:
            return self._finish("blocked", "Agent Smith write-pilot mode is disabled.")

        self._audit("write_pilot", "started")

        # 1. Path approval
        path_check = self._runtime.policy.check_write_pilot_path(self._target_path, repo_root=self._repo_root)
        if path_check.decision.value == "deny":
            return await self._fail(path_check.reason)
        self._transition(WritePilotState.AWAITING_PATH_APPROVAL)
        approved = await self._request_approval("path", target_path=self._target_path)
        if not approved:
            return await self._fail("Path approval denied.")

        # 2. Content approval
        self._transition(WritePilotState.AWAITING_CONTENT_APPROVAL)
        approved = await self._request_approval("content", target_path=self._target_path)
        if not approved:
            return await self._fail("Content approval denied.")

        # 3. Write
        original_target = self._repo_root / self._target_path
        self._file_existed = original_target.exists()
        if self._file_existed:
            self._original_content = original_target.read_text(encoding="utf-8")
        write_result = await self._run_tool("write_pilot_file_write", {
            "target_path": self._target_path,
            "content": self._proposed_content,
            "repo_root": str(self._repo_root),
        })
        if not write_result.success or not write_result.output.get("success"):
            error = write_result.output.get("error") or write_result.public_error_message or "write failed"
            return await self._fail(f"Write failed: {error}")
        self._backup_path = write_result.output.get("backup_path")
        self._final_content = self._proposed_content
        self._transition(WritePilotState.WRITTEN)

        # 4. Validate
        validation = self._validate_write()
        if not validation["ok"]:
            return await self._fail(f"Validation failed: {validation['reason']}")
        self._transition(WritePilotState.VALIDATED)

        # 5. Stage approval
        self._transition(WritePilotState.AWAITING_STAGE_APPROVAL)
        approved = await self._request_approval("stage", target_path=self._target_path)
        if not approved:
            return await self._fail("Stage approval denied.", rolled_back=True, transition_to_rolled_back=False)

        stage_result = await self._run_tool("write_pilot_git_add", {
            "target_path": self._target_path,
            "repo_root": str(self._repo_root),
        })
        if not stage_result.success or not stage_result.output.get("success"):
            error = stage_result.output.get("error") or stage_result.public_error_message or "stage failed"
            return await self._fail(f"Stage failed: {error}")
        self._transition(WritePilotState.STAGED)

        # 6. Commit approval
        self._transition(WritePilotState.AWAITING_COMMIT_APPROVAL)
        approved = await self._request_approval("commit", target_path=self._target_path, commit_message=self._commit_message)
        if not approved:
            return await self._fail("Commit approval denied.", rolled_back=True, transition_to_rolled_back=False)

        commit_result = await self._run_tool("write_pilot_git_commit", {
            "message": self._commit_message,
            "repo_root": str(self._repo_root),
            "target_path": self._target_path,
        })
        if not commit_result.success or not commit_result.output.get("success"):
            error = commit_result.output.get("error") or commit_result.public_error_message or "commit failed"
            return await self._fail(f"Commit failed: {error}", rolled_back=False)
        self._commit_hash = commit_result.output.get("commit_hash")
        self._transition(WritePilotState.COMMITTED)

        # 7. Verify
        self._transition(WritePilotState.VERIFIED)
        self._audit("write_pilot", "verified", commit_hash=self._commit_hash)
        return self._finish("complete", "Write pilot completed and committed.")

    async def _request_approval(self, approval_type: str, **context: Any) -> bool:
        record = WritePilotApprovalRecord(
            approval_type=approval_type,
            request_id=self._request_id,
            target_path=context.get("target_path"),
            approved=False,
            actor=self._actor,
        )
        self._approvals.append(record.model_dump(mode="json"))
        # Ensure every gate has the full write-pilot context so the provider can
        # store content and commit-message hashes for early resume validation.
        provider_context = dict(context)
        provider_context.setdefault("content", self._proposed_content)
        provider_context.setdefault("commit_message", self._commit_message)
        if self._provider is not None:
            await self._provider.request_approval(approval_type, self._request_id, provider_context)
        if self._approval_callback is None:
            return False
        token = await self._approval_callback(approval_type, self._request_id, provider_context)
        if token is None or not token.approved:
            return False
        if token.request_id != self._request_id:
            return False
        if token.approval_type != approval_type:
            return False
        if approval_type in {"path", "content", "stage"} and token.target_path != self._target_path:
            return False
        self._approvals[-1]["approved"] = True
        self._audit("approval", "approved", approval_type=approval_type)
        return True

    async def _run_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool_check = self._runtime.policy.check_write_pilot_tool(tool_name)
        if tool_check.decision.value == "deny":
            return self._tool_error(tool_name, tool_check.reason or "tool denied")
        request = ToolExecutionRequest(
            tool_name=tool_name,
            arguments=arguments,
            request_id=self._request_id,
            actor=self._actor,
        )
        result = await self._runtime._orchestrator.registry.execute(request)
        self._tool_results.append(result)
        self._audit("tool", "success" if result.success else "failure", tool_name=tool_name)
        return result

    def _tool_error(self, tool_name: str, message: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            success=False,
            tool_name=tool_name,
            output={"error": message, "blocked": True},
            error_code="policy_violation",
            public_error_message=message,
            duration_ms=0,
            request_id=self._request_id,
        )

    def _validate_write(self) -> dict[str, Any]:
        target = self._repo_root / self._target_path
        if not target.exists():
            return {"ok": False, "reason": "target file does not exist after write"}
        try:
            target.relative_to(self._runtime.policy.write_pilot_sandbox)
        except ValueError:
            return {"ok": False, "reason": "target escaped the write-pilot sandbox"}
        try:
            proc = subprocess.run(
                ["git", "diff", "--check", "--", self._target_path],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                return {"ok": False, "reason": "git diff --check reported whitespace errors"}
        except Exception as exc:
            return {"ok": False, "reason": f"git diff --check failed: {exc}"}
        # Ensure only the approved file changed
        try:
            status_proc = subprocess.run(
                ["git", "status", "--short", "--", self._target_path],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if status_proc.returncode != 0:
                return {"ok": False, "reason": "git status failed"}
        except Exception as exc:
            return {"ok": False, "reason": f"git status failed: {exc}"}
        return {"ok": True}

    async def _rollback(self, *, transition_to_rolled_back: bool = True) -> None:
        target = self._repo_root / self._target_path
        try:
            if self._file_existed:
                if self._original_content is not None:
                    target.write_text(self._original_content, encoding="utf-8")
            else:
                if target.exists():
                    target.unlink()
            # Unstage only the approved target
            subprocess.run(
                ["git", "restore", "--staged", "--", self._target_path],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if transition_to_rolled_back:
                self._transition(WritePilotState.ROLLED_BACK)
            self._rolled_back = True
            self._audit("rollback", "completed")
        except Exception as exc:
            self._audit("rollback", "failure", error=str(exc))

    def _transition(self, to_state: WritePilotState) -> None:
        transition = WritePilotStateTransition(
            from_state=self._state.value,
            to_state=to_state.value,
            action="state_transition",
            outcome="ok",
        )
        self._transitions.append(transition.model_dump(mode="json"))
        self._state = to_state

    async def _fail(self, message: str, *, rolled_back: bool = True, transition_to_rolled_back: bool = True) -> WritePilotResult:
        should_rollback = (
            rolled_back
            and self._state not in {
                WritePilotState.ROLLED_BACK,
                WritePilotState.PLANNED,
                WritePilotState.AWAITING_PATH_APPROVAL,
                WritePilotState.AWAITING_CONTENT_APPROVAL,
            }
            and not self._rolled_back
        )
        if should_rollback:
            await self._rollback(transition_to_rolled_back=transition_to_rolled_back)
        return self._finish("failed", message)

    def _finish(self, status: str, message: str) -> WritePilotResult:
        duration_ms = _elapsed_ms(self._start)
        self._audit("write_pilot", status, message=message)
        self._runtime._audit_records.extend(self._audit_records)
        self._runtime._persist_audit_records()
        return WritePilotResult(
            request_id=self._request_id,
            status=status,
            state=self._state.value,
            message=message,
            objective=self._objective,
            target_path=self._target_path,
            wrote_content=self._final_content is not None,
            staged=self._state.value in {WritePilotState.STAGED.value, WritePilotState.AWAITING_COMMIT_APPROVAL.value, WritePilotState.COMMITTED.value, WritePilotState.VERIFIED.value},
            committed=self._commit_hash is not None,
            rolled_back=self._rolled_back,
            commit_hash=self._commit_hash,
            original_content="<redacted>" if self._original_content is not None else None,
            final_content="<redacted>" if self._final_content is not None else None,
            diff=None,
            approvals=self._approvals,
            state_transitions=self._transitions,
            audit_records=[_sanitize_for_audit(record) for record in self._audit_records],
            actor=self._actor,
            duration_ms=duration_ms,
        )

    def _audit(self, action: str, outcome: str, **details: Any) -> dict[str, Any]:
        record = {
            "event_id": str(uuid.uuid4()),
            "request_id": self._request_id,
            "actor": self._actor,
            "action": action,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": _sanitize_for_audit(details),
        }
        self._audit_records.append(record)
        return record

    def _tool_error(self, tool_name: str, message: str) -> "ToolExecutionResult":
        from freyja.tools.models import ToolExecutionResult


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
