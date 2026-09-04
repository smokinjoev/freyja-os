from __future__ import annotations

import dataclasses
import time
import json
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = REPO_ROOT / "config" / "freyja-proactive.yaml"


class ProactivePolicyError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ProactiveScheduleCandidate:
    job_id: str
    recipient: str
    destination: str
    status: str
    required_tools: tuple[str, ...]
    requires_approval: bool
    dry_run_required: bool


@dataclasses.dataclass(frozen=True)
class ProactiveDryRunDispatch:
    schedule_id: str
    job_id: str
    recipient: str
    destination: str
    required_tools: tuple[str, ...]
    status: str
    would_send: bool
    delivery_result: str


class ProactivePlanner:
    def __init__(self, policy_path: Path = DEFAULT_POLICY) -> None:
        self.policy = self._load_policy(policy_path)

    def candidates(self) -> list[ProactiveScheduleCandidate]:
        gate = self.policy.get("enablement_gate") or {}
        candidates: list[ProactiveScheduleCandidate] = []
        for job_id, job in sorted((self.policy.get("allowed_jobs") or {}).items()):
            for recipient in job.get("allowed_recipients") or []:
                for destination in job.get("allowed_destinations") or []:
                    candidates.append(
                        ProactiveScheduleCandidate(
                            job_id=job_id,
                            recipient=str(recipient),
                            destination=str(destination),
                            status=str(job.get("status") or "disabled"),
                            required_tools=tuple(str(tool) for tool in job.get("required_tools") or []),
                            requires_approval=gate.get("per_schedule_approval") == "required",
                            dry_run_required=gate.get("dry_run_first") == "required",
                        )
                    )
        return candidates

    def readiness(self, *, chat_stable: bool, recipients_verified: set[str], destinations_verified: set[str], approved_schedule_ids: set[str]) -> dict[str, Any]:
        ready: list[str] = []
        blocked: list[dict[str, Any]] = []
        for candidate in self.candidates():
            schedule_id = self.schedule_id(candidate)
            reasons = []
            if candidate.status != "enabled":
                reasons.append("job_disabled")
            if not chat_stable:
                reasons.append("chat_not_stable")
            if candidate.recipient not in recipients_verified:
                reasons.append("recipient_not_verified")
            if candidate.destination not in destinations_verified:
                reasons.append("destination_not_verified")
            if candidate.requires_approval and schedule_id not in approved_schedule_ids:
                reasons.append("schedule_not_approved")
            if candidate.dry_run_required:
                reasons.append("dry_run_required")
            if reasons:
                blocked.append({"schedule_id": schedule_id, "job_id": candidate.job_id, "recipient": candidate.recipient, "destination": candidate.destination, "reasons": reasons})
            else:
                ready.append(schedule_id)
        return {
            "report_type": "freyja-proactive-readiness",
            "generated_at_unix": int(time.time()),
            "secrets_included": False,
            "private_content_included": False,
            "candidate_count": len(ready) + len(blocked),
            "ready_schedule_ids": ready,
            "blocked": blocked,
            "all_disabled_by_default": all(candidate.status == "disabled" for candidate in self.candidates()),
            "ok": not ready,
        }

    def audit_event(self, candidate: ProactiveScheduleCandidate, *, delivery_result: str = "not_sent") -> dict[str, Any]:
        audit = self.policy.get("audit") or {}
        event = {
            "event": "freyja_proactive_schedule_candidate",
            "schedule_id": self.schedule_id(candidate),
            "job_id": candidate.job_id,
            "delivery_result": delivery_result,
            "message_body_logged": False,
        }
        if audit.get("record_recipient") is True:
            event["recipient"] = candidate.recipient
        if audit.get("record_destination") is True:
            event["destination"] = candidate.destination
        return event

    def dry_run_dispatches(self) -> list[ProactiveDryRunDispatch]:
        dispatches: list[ProactiveDryRunDispatch] = []
        for candidate in self.candidates():
            dispatches.append(
                ProactiveDryRunDispatch(
                    schedule_id=self.schedule_id(candidate),
                    job_id=candidate.job_id,
                    recipient=candidate.recipient,
                    destination=candidate.destination,
                    required_tools=candidate.required_tools,
                    status=candidate.status,
                    would_send=False,
                    delivery_result="dry_run_only",
                )
            )
        return dispatches

    def dry_run_report(self) -> dict[str, Any]:
        dispatches = self.dry_run_dispatches()
        generated_at = int(time.time())
        return {
            "report_type": "freyja-proactive-dry-run",
            "generated_at_unix": generated_at,
            "timestamp_unix": generated_at,
            "secrets_included": False,
            "private_content_included": False,
            "dispatch_count": len(dispatches),
            "would_send_count": sum(1 for item in dispatches if item.would_send),
            "all_sends_suppressed": all(not item.would_send for item in dispatches),
            "dispatches": [dataclasses.asdict(item) for item in dispatches],
        }

    @staticmethod
    def schedule_id(candidate: ProactiveScheduleCandidate) -> str:
        return f"{candidate.job_id}:{candidate.recipient}:{candidate.destination}"

    def _load_policy(self, path: Path) -> dict[str, Any]:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ProactivePolicyError("proactive policy must be a mapping")
        if payload.get("secrets_included") is not False:
            raise ProactivePolicyError("proactive policy must not contain secrets")
        if payload.get("default_status") != "disabled":
            raise ProactivePolicyError("proactive policy must default to disabled")
        gate = payload.get("enablement_gate") or {}
        required = {"chat_stable", "recipients_verified", "destinations_verified", "per_schedule_approval", "dry_run_first"}
        if {key for key in required if gate.get(key) == "required"} != required:
            raise ProactivePolicyError("proactive enablement gates are incomplete")
        prohibitions = payload.get("prohibitions") or {}
        if prohibitions.get("run_destructive_tools") is not True:
            raise ProactivePolicyError("proactive policy must prohibit destructive tools")
        return payload


def render_candidates(candidates: list[ProactiveScheduleCandidate]) -> str:
    return json.dumps([dataclasses.asdict(candidate) for candidate in candidates], indent=2, sort_keys=True)
