#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

from freyja.cloyd_smith_loop import CloydSmithJobStatus, CloydSmithJobStore, CloydSmithJobUpdate
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.opencode_runtime import _opencode_output, _opencode_send, _opencode_status, _opencode_stop


async def _run_once(store: CloydSmithJobStore) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for job in store.list_active(limit=20):
        if job.status == CloydSmithJobStatus.QUEUED:
            prompt = _smith_prompt(job)
            output = await _opencode_send(
                ToolExecutionRequest(
                    tool_name="opencode_send",
                    arguments={"alias": job.smith_alias, "prompt": prompt},
                    actor="cloyd-smith-loop-5.2",
                )
            )
            store.add_event(job.job_id, "smith_send", _bounded(output))
            next_status = CloydSmithJobStatus.RUNNING if output.get("ok") else CloydSmithJobStatus.BLOCKED
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=next_status,
                    next_action="check_smith_output" if output.get("ok") else "needs_user_or_operator_review",
                    last_evidence=_bounded(output),
                    error=None if output.get("ok") else str(output.get("error") or "Smith send failed"),
                ),
            )
            results.append({"job_id": job.job_id, "status": updated.status.value, "action": "sent_to_smith"})
            continue

        if job.status == CloydSmithJobStatus.RUNNING:
            status = await _opencode_status(
                ToolExecutionRequest(
                    tool_name="opencode_status",
                    arguments={"alias": job.smith_alias},
                    actor="cloyd-smith-loop-5.2",
                )
            )
            store.add_event(job.job_id, "smith_status", _bounded(status))
            if not status.get("ok"):
                updated = store.update(
                    job.job_id,
                    CloydSmithJobUpdate(
                        status=CloydSmithJobStatus.BLOCKED,
                        next_action="fix_runtime_or_retry",
                        last_evidence=_bounded(status),
                        error=str(status.get("error") or "Smith status failed"),
                    ),
                )
                results.append({"job_id": job.job_id, "status": updated.status.value, "action": "blocked"})
                continue
            if status.get("state") != "idle":
                store.update(job.job_id, CloydSmithJobUpdate(last_evidence=_bounded(status)))
                results.append({"job_id": job.job_id, "status": "running", "action": "still_running"})
                continue
            output = await _opencode_output(
                ToolExecutionRequest(
                    tool_name="opencode_output",
                    arguments={"alias": job.smith_alias, "limit": 3},
                    actor="cloyd-smith-loop-5.2",
                )
            )
            store.add_event(job.job_id, "smith_output", _bounded(output))
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.NEEDS_REVIEW,
                    next_action="cloyd_review_evidence",
                    last_evidence=_bounded(output),
                ),
            )
            results.append({"job_id": job.job_id, "status": updated.status.value, "action": "ready_for_review"})
    return results


async def _stop_job(store: CloydSmithJobStore, job_id: str) -> dict[str, Any]:
    job = store.get(job_id)
    stopped = await _opencode_stop(
        ToolExecutionRequest(
            tool_name="opencode_stop",
            arguments={"alias": job.smith_alias},
            actor="cloyd-smith-loop-5.2",
        )
    )
    store.add_event(job.job_id, "smith_stop", _bounded(stopped))
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            next_action="stopped_by_supervisor",
            last_evidence=_bounded(stopped),
        ),
    )
    return {"job_id": job_id, "status": updated.status.value, "smith_stop": stopped}


def _smith_prompt(job) -> str:
    criteria = "\n".join(f"- {item}" for item in job.acceptance_criteria) or "- Report evidence clearly."
    return f"""Freyja 5.2 Smith worker task.

Original Cloyd objective:
{job.objective}

Current Smith task:
{job.current_prompt}

Acceptance criteria:
{criteria}

Rules:
- Do not use subagents or task delegation.
- Use direct commands only.
- Keep work bounded and report commands, diffs, tests, blockers, and evidence.
- Stop after reporting. Cloyd owns the master plan.
"""


def _bounded(payload: Any, *, limit: int = 20000) -> dict[str, Any]:
    text = json.dumps(payload, default=str)
    if len(text) <= limit:
        return payload if isinstance(payload, dict) else {"value": payload}
    return {"truncated": True, "text": text[-limit:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Freyja 5.2 durable Cloyd-Smith supervisor loop.")
    parser.add_argument("--database")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--stop-job")
    args = parser.parse_args()

    store = CloydSmithJobStore(args.database)
    if args.stop_job:
        print(json.dumps(asyncio.run(_stop_job(store, args.stop_job)), indent=2))
        return 0
    if args.once:
        print(json.dumps(asyncio.run(_run_once(store)), indent=2))
        return 0
    while True:
        try:
            results = asyncio.run(_run_once(store))
            if results:
                print(json.dumps({"results": results}, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"error": str(exc)}, sort_keys=True), flush=True)
        time.sleep(max(args.interval, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
