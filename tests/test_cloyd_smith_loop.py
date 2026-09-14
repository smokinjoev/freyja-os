from __future__ import annotations

import asyncio

from freyja.cloyd_smith_loop import CloydSmithJobCreate, CloydSmithJobStatus, CloydSmithJobStore, CloydSmithJobUpdate
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.cloyd_smith_loop import _cloyd_smith_status, _cloyd_smith_submit
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


def test_cloyd_smith_job_lifecycle_records_status_and_events(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Update Cloyd runtime contract.",
            smith_alias="freyja-code",
            acceptance_criteria=["diff reviewed", "tests pass"],
            current_prompt="Edit docs/operations/cloyd-runtime-contract.md.",
        )
    )

    assert job.job_id.startswith("pratt52-")
    assert job.status == CloydSmithJobStatus.QUEUED
    assert store.list_active()[0].job_id == job.job_id

    store.add_event(job.job_id, "smith_output", {"tests": "pass"})
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_REVIEW,
            next_action="cloyd_review_evidence",
            last_evidence={"tests": "pass"},
        ),
    )

    assert updated.status == CloydSmithJobStatus.NEEDS_REVIEW
    assert updated.last_evidence == {"tests": "pass"}
    assert store.events(job.job_id)[0]["event_type"] == "smith_output"

    done = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE))
    assert done.completed_at is not None
    assert store.list_active() == []


def test_builtin_registry_includes_cloyd_smith_loop_tools() -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry)

    expected = {
        "cloyd_smith_submit": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_status": ToolRiskLevel.READ_ONLY,
        "cloyd_smith_record": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_stop": ToolRiskLevel.CONTROLLED_WRITE,
    }
    for name, risk in expected.items():
        definition = registry.get_tool(name)
        assert definition is not None
        assert definition.risk_level == risk
        assert definition.host_service == "cloyd-smith-loop"


def test_cloyd_smith_submit_returns_receipt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))

    result = asyncio.run(
        _cloyd_smith_submit(
            ToolExecutionRequest(
                tool_name="cloyd_smith_submit",
                arguments={
                    "objective": "Do durable work.",
                    "prompt": "Ask Smith to do one bounded step.",
                    "smith_alias": "freyja-code",
                    "acceptance_criteria": ["evidence recorded"],
                },
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert result["receipt"]["job_id"].startswith("pratt52-")
    assert result["receipt"]["status"] == "queued"
    assert result["receipt"]["status_prompt"].startswith("Ask Cloyd: status")

    status = asyncio.run(
        _cloyd_smith_status(
            ToolExecutionRequest(
                tool_name="cloyd_smith_status",
                arguments={"job_id": result["receipt"]["job_id"]},
                actor="test",
            )
        )
    )
    assert status["job"]["objective"] == "Do durable work."
