from __future__ import annotations

from fastapi.testclient import TestClient

import freyja.freyja3_app as freyja3_app
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.freyja3_audit import Freyja3AuditStore
from freyja.freyja3_machines import Freyja3MachineStatusStore
from freyja.freyja3_memory import Freyja3MemoryStore
from freyja.freyja3_scheduler import Freyja3SchedulerStore
from freyja.freyja3_workers import Freyja3WorkerJobStore
from freyja.semantic_events import SemanticEventStore


def test_freyja3_app_canonical_route_uses_gateway_runtime(monkeypatch, tmp_path) -> None:
    memory_store = Freyja3MemoryStore(tmp_path / "memory.db")
    monkeypatch.setattr(freyja3_app, "audit_store", Freyja3AuditStore(tmp_path / "audit.db"))
    monkeypatch.setattr(freyja3_app, "agent_runtime", AgentRuntimeV3(memory_store=memory_store))
    client = TestClient(freyja3_app.app)

    response = client.post(
        "/canonical/route",
        json={
            "trace_id": "trace-f3-app",
            "message_id": "msg-f3-app",
            "channel": "imessage",
            "conversation_id": "conv-f3-app",
            "sender": {"channel_id": "sender", "address": "+1555"},
            "resolved_user_id": "joe",
            "text": "Inspect git status and search the web.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["resolved_agent_id"] == "cloyd-gibbler"
    assert data["channel_metadata"]["freyja3"] is True
    assert data["channel_metadata"]["inference_machine_id"] == "vulcan"
    assert data["channel_metadata"]["written_memories"]
    audit = client.get("/freyja3/audit?conversation_id=conv-f3-app", headers={"x-freyja-security-domain": "household"})
    denied = client.get("/freyja3/audit?conversation_id=conv-f3-app", headers={"x-freyja-security-domain": "person.beth"})
    assert audit.json()["count"] >= 3
    assert denied.status_code == 403


def test_freyja3_app_semantic_events_are_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "semantic_event_store", SemanticEventStore(tmp_path / "events.db"))
    client = TestClient(freyja3_app.app)

    created = client.post(
        "/events/semantic",
        headers={"x-freyja-security-domain": "system"},
        json={
            "source_machine_id": "hera",
            "event_type": "person_present",
            "room": "kitchen",
            "subject": "beth",
            "confidence": 0.9,
        },
    )
    listed = client.get("/events/semantic?event_type=person_present")

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_freyja3_app_memory_enforces_domain_headers(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "memory_store", Freyja3MemoryStore(tmp_path / "memory.db"))
    client = TestClient(freyja3_app.app)

    created = client.post(
        "/freyja3/memory",
        headers={"x-freyja-security-domain": "person.joe"},
        json={
            "owner_domain_id": "person.joe",
            "scope": "personal",
            "source_agent_id": "cloyd-gibbler",
            "content": "Private Joe memory.",
            "provenance": "unit-test",
            "classification": "private",
        },
    )
    joe_read = client.get("/freyja3/memory", headers={"x-freyja-security-domain": "person.joe"})
    beth_read = client.get("/freyja3/memory", headers={"x-freyja-security-domain": "person.beth"})

    assert created.status_code == 200
    assert joe_read.json()["count"] == 1
    assert beth_read.json()["count"] == 0


def test_freyja3_app_memory_candidate_review_writes_memory_and_audit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "memory_store", Freyja3MemoryStore(tmp_path / "memory.db"))
    monkeypatch.setattr(freyja3_app, "audit_store", Freyja3AuditStore(tmp_path / "audit.db"))
    client = TestClient(freyja3_app.app)

    proposed = client.post(
        "/freyja3/memory/candidates",
        headers={"x-freyja-security-domain": "person.joe", "x-freyja-trace-id": "trace-candidate"},
        json={
            "owner_domain_id": "person.joe",
            "scope": "personal",
            "source_agent_id": "cloyd-gibbler",
            "content": "Joe prefers five-point readiness checks.",
            "provenance": "model-assisted-candidate",
            "classification": "private",
            "metadata": {"conversation_id": "conv-candidate-app"},
        },
    )
    assert proposed.status_code == 200
    candidate_id = proposed.json()["candidate"]["candidate_id"]
    assert client.get("/freyja3/memory", headers={"x-freyja-security-domain": "person.joe"}).json()["count"] == 0

    reviewed = client.post(
        f"/freyja3/memory/candidates/{candidate_id}/review",
        headers={"x-freyja-security-domain": "person.joe", "x-freyja-trace-id": "trace-candidate-review"},
        json={"decision": "approve", "reason": "Joe confirmed."},
    )
    memories = client.get("/freyja3/memory", headers={"x-freyja-security-domain": "person.joe"})
    audit = client.get("/freyja3/audit?conversation_id=conv-candidate-app", headers={"x-freyja-security-domain": "household"})

    assert reviewed.status_code == 200
    assert reviewed.json()["candidate"]["status"] == "approved"
    assert reviewed.json()["memory"]["content"] == "Joe prefers five-point readiness checks."
    assert memories.json()["count"] == 1
    assert {event["event_type"] for event in audit.json()["events"]} == {
        "agent_memory_candidate_proposed",
        "agent_memory_candidate_reviewed",
    }


def test_freyja3_app_memory_candidate_review_denies_other_private_domain(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "memory_store", Freyja3MemoryStore(tmp_path / "memory.db"))
    client = TestClient(freyja3_app.app)

    proposed = client.post(
        "/freyja3/memory/candidates",
        headers={"x-freyja-security-domain": "person.joe"},
        json={
            "owner_domain_id": "person.joe",
            "scope": "personal",
            "source_agent_id": "cloyd-gibbler",
            "content": "Private candidate.",
            "provenance": "model-assisted-candidate",
            "classification": "private",
        },
    )
    candidate_id = proposed.json()["candidate"]["candidate_id"]

    reviewed = client.post(
        f"/freyja3/memory/candidates/{candidate_id}/review",
        headers={"x-freyja-security-domain": "person.beth"},
        json={"decision": "approve"},
    )

    assert reviewed.status_code == 403


def test_freyja3_app_machine_heartbeat_is_household_readable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "machine_status_store", Freyja3MachineStatusStore(tmp_path / "machines.db"))
    client = TestClient(freyja3_app.app)

    heartbeat = client.post(
        "/freyja3/machines/heartbeat",
        headers={"x-freyja-security-domain": "system"},
        json={
            "machine_id": "mars",
            "role": "worker-ingestion-monitoring",
            "status": "ok",
            "commit_sha": "abc123",
            "service": "freyja3-agent-gateway",
        },
    )
    listed = client.get("/freyja3/machines", headers={"x-freyja-security-domain": "household"})

    assert heartbeat.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["machines"][0]["machine_id"] == "mars"


def test_freyja3_app_worker_job_lifecycle_is_audited(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "worker_job_store", Freyja3WorkerJobStore(tmp_path / "workers.db"))
    monkeypatch.setattr(freyja3_app, "audit_store", Freyja3AuditStore(tmp_path / "audit.db"))
    client = TestClient(freyja3_app.app)

    created = client.post(
        "/freyja3/workers/jobs",
        headers={"x-freyja-security-domain": "household", "x-freyja-trace-id": "trace-worker"},
        json={
            "job_id": "job-mars-test",
            "worker_class": "monitoring",
            "target_machine_id": "mars",
            "objective": "Check Mars worker health.",
            "payload": {"check": "health"},
        },
    )
    claim_wrong = client.post(
        "/freyja3/workers/jobs/claim?machine_id=atlas&worker_class=monitoring",
        headers={"x-freyja-security-domain": "system", "x-freyja-trace-id": "trace-worker-claim"},
    )
    claimed = client.post(
        "/freyja3/workers/jobs/claim?machine_id=mars&worker_class=monitoring",
        headers={"x-freyja-security-domain": "system", "x-freyja-trace-id": "trace-worker-claim"},
    )
    completed = client.post(
        "/freyja3/workers/jobs/job-mars-test/complete?machine_id=mars",
        headers={"x-freyja-security-domain": "system", "x-freyja-trace-id": "trace-worker-complete"},
        json={"status": "completed", "result": {"ok": True}},
    )
    listed = client.get("/freyja3/workers/jobs?include_completed=true", headers={"x-freyja-security-domain": "household"})
    audit = client.get("/freyja3/audit?conversation_id=job-mars-test", headers={"x-freyja-security-domain": "household"})

    assert created.status_code == 200
    assert claim_wrong.json()["job"] is None
    assert claimed.json()["job"]["claimed_by_machine_id"] == "mars"
    assert completed.json()["job"]["status"] == "completed"
    assert listed.json()["jobs"][0]["job_id"] == "job-mars-test"
    assert {event["event_type"] for event in audit.json()["events"]} == {
        "worker_job_created",
        "worker_job_claimed",
        "worker_job_completed",
    }


def test_freyja3_app_scheduler_dispatches_due_agent_envelopes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "scheduler_store", Freyja3SchedulerStore(tmp_path / "scheduler.db"))
    monkeypatch.setattr(freyja3_app, "memory_store", Freyja3MemoryStore(tmp_path / "memory.db"))
    monkeypatch.setattr(freyja3_app, "agent_runtime", AgentRuntimeV3(memory_store=freyja3_app.memory_store))
    client = TestClient(freyja3_app.app)

    created = client.post(
        "/freyja3/schedules",
        headers={"x-freyja-security-domain": "household"},
        json={
            "schedule_id": "sched-test",
            "due_at": "2026-08-26T10:00:00Z",
            "target_agent_id": "cloyd-gibbler",
            "resolved_user_id": "joe",
            "conversation_id": "conv-sched",
            "text": "Inspect git status.",
        },
    )
    dispatched = client.post(
        "/freyja3/schedules/dispatch-due?due_before=2026-08-26T10:01:00Z",
        headers={"x-freyja-security-domain": "system"},
    )
    listed = client.get("/freyja3/schedules", headers={"x-freyja-security-domain": "system"})

    assert created.status_code == 200
    assert dispatched.status_code == 200
    assert dispatched.json()["count"] == 1
    response = dispatched.json()["dispatched"][0]["response"]
    assert response["resolved_agent_id"] == "cloyd-gibbler"
    assert response["channel_metadata"]["agent_steps"][0]["kind"] == "objective_received"
    assert listed.json()["count"] == 0


async def test_freyja3_inference_health_does_not_fallback_unconfigured_endpoint() -> None:
    reachable, models = await freyja3_app._inference_endpoint_health("ollama", "", "")

    assert reachable is False
    assert models == []


def test_freyja3_app_follow_up_does_not_fabricate_tool_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "memory_store", Freyja3MemoryStore(tmp_path / "memory.db"))
    monkeypatch.setattr(freyja3_app, "agent_runtime", AgentRuntimeV3(memory_store=freyja3_app.memory_store))
    client = TestClient(freyja3_app.app)

    response = client.post(
        "/canonical/route",
        json={
            "message_id": "msg-follow-up-app",
            "channel": "imessage",
            "conversation_id": "conv-follow-up-app",
            "sender": {"channel_id": "sender", "address": "+1555"},
            "resolved_user_id": "joe",
            "resolved_agent_id": "cloyd-gibbler",
            "text": "Send an iMessage.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_results"] == []
    assert data["channel_metadata"]["follow_up_questions"] == ["Who should I send the message to, and what should it say?"]
