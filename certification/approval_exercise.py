from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ApprovalExercise:
    name: str
    capability: str
    consequential: bool
    approval_granted: bool
    director_authorized: bool
    allowed: bool
    required_permission: str | None
    confirmation_policy: str
    risk_level: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capability": self.capability,
            "consequential": self.consequential,
            "approval_granted": self.approval_granted,
            "director_authorized": self.director_authorized,
            "allowed": self.allowed,
            "required_permission": self.required_permission,
            "confirmation_policy": self.confirmation_policy,
            "risk_level": self.risk_level,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApprovalExerciseReport:
    timestamp: str
    actor_person_id: str
    exercises: tuple[ApprovalExercise, ...]
    schema_version: str = "1.0"
    report_paths: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        unsafe_allows = [
            exercise
            for exercise in self.exercises
            if exercise.consequential and exercise.allowed and not exercise.director_authorized
        ]
        denied_without_approval = [
            exercise
            for exercise in self.exercises
            if exercise.consequential and not exercise.allowed and not exercise.approval_granted
        ]
        allowed_with_approval = [
            exercise
            for exercise in self.exercises
            if (
                exercise.consequential
                and exercise.allowed
                and exercise.approval_granted
                and exercise.director_authorized
            )
        ]
        return bool(denied_without_approval) and bool(allowed_with_approval) and not unsafe_allows

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "actor_person_id": self.actor_person_id,
            "passed": self.passed,
            "exercises": [exercise.to_dict() for exercise in self.exercises],
            "report_paths": dict(self.report_paths),
        }


def run_approval_exercise(*, actor_person_id: str = "joe", registry: ToolRegistry | None = None) -> ApprovalExerciseReport:
    registry = registry or ToolRegistry()
    register_builtin_tools(registry)
    exercises: list[ApprovalExercise] = []
    for tool_name in ("calendar_move_event_if_conflict", "home_assistant_control_state"):
        definition = registry.get_tool(tool_name)
        if definition is None:
            raise ValueError(f"required approval exercise tool is not registered: {tool_name}")
        exercises.extend(_exercise_tool(registry, definition, actor_person_id=actor_person_id))
    return ApprovalExerciseReport(
        timestamp=datetime.now(UTC).isoformat(),
        actor_person_id=actor_person_id,
        exercises=tuple(exercises),
    )


def write_approval_exercise_report(report: ApprovalExerciseReport, output_dir: Path) -> ApprovalExerciseReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _report_stem(report.timestamp)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    with_paths = ApprovalExerciseReport(
        timestamp=report.timestamp,
        actor_person_id=report.actor_person_id,
        exercises=report.exercises,
        schema_version=report.schema_version,
        report_paths={"json": str(json_path), "markdown": str(md_path)},
    )
    json_path.write_text(json.dumps(with_paths.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_approval_exercise_markdown(with_paths), encoding="utf-8")
    return with_paths


def render_approval_exercise_markdown(report: ApprovalExerciseReport) -> str:
    lines = [
        "# Rev 2 Approval Exercise",
        "",
        f"- Timestamp: {report.timestamp}",
        f"- Actor person ID: {report.actor_person_id}",
        f"- Passed: {report.passed}",
        "",
        "| Exercise | Tool | Director authorized | Approval granted | Allowed | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for exercise in report.exercises:
        lines.append(
            "| "
            + " | ".join(
                [
                    exercise.name,
                    exercise.capability,
                    str(exercise.director_authorized),
                    str(exercise.approval_granted),
                    str(exercise.allowed),
                    exercise.reason.replace("|", "\\|"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _exercise_tool(
    registry: ToolRegistry,
    definition: ToolDefinition,
    *,
    actor_person_id: str,
) -> tuple[ApprovalExercise, ...]:
    return (
        _authorize_case(
            registry,
            definition,
            actor_person_id=actor_person_id,
            name=f"{definition.name}-denied-without-director-or-approval",
            director_authorized=False,
            approval_granted=False,
        ),
        _authorize_case(
            registry,
            definition,
            actor_person_id=actor_person_id,
            name=f"{definition.name}-denied-without-approval",
            director_authorized=True,
            approval_granted=False,
        ),
        _authorize_case(
            registry,
            definition,
            actor_person_id=actor_person_id,
            name=f"{definition.name}-approved",
            director_authorized=True,
            approval_granted=True,
        ),
        _authorize_case(
            registry,
            definition,
            actor_person_id=actor_person_id,
            name=f"{definition.name}-denied-without-director",
            director_authorized=False,
            approval_granted=True,
        ),
    )


def _authorize_case(
    registry: ToolRegistry,
    definition: ToolDefinition,
    *,
    actor_person_id: str,
    name: str,
    director_authorized: bool,
    approval_granted: bool,
) -> ApprovalExercise:
    request = ToolExecutionRequest(
        tool_name=definition.name,
        actor="rev2-approval-exercise",
        metadata={
            "person": {"person_id": actor_person_id},
            "memory_principal": {
                "client_type": "imessage",
                "client_subject": f"family-member:{actor_person_id}",
            },
            "director_authorized": director_authorized,
            "approval_granted": approval_granted,
        },
    )
    decision = registry.authorize(definition, request)
    return ApprovalExercise(
        name=name,
        capability=definition.name,
        consequential=definition.risk_level == ToolRiskLevel.CONTROLLED_WRITE,
        approval_granted=approval_granted,
        director_authorized=director_authorized,
        allowed=decision.allowed,
        required_permission=decision.required_permission,
        confirmation_policy=definition.confirmation_policy,
        risk_level=str(definition.risk_level),
        reason=decision.reason,
    )


def _report_stem(timestamp: str) -> str:
    safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("+", "Z")
    return f"{safe_timestamp}-rev2-approval-exercise"
