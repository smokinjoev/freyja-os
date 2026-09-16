from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from freyja.cloyd_smith_loop import CloydSmithJobCreate, CloydSmithJobStore
from freyja.continuity import continuity_router
from freyja.memory import store as memory_store
from freyja.memory.store import MemoryStore
from freyja.tools.cloyd_smith_loop import _cloyd_smith_record
from freyja.tools.models import ToolExecutionRequest


def _client(tmp_path) -> TestClient:
    test_store = MemoryStore(database_path=str(tmp_path / "continuity-memory.db"))
    test_store.initialize(force=True)
    memory_store.set_store(test_store)
    app = FastAPI()
    app.include_router(continuity_router)
    return TestClient(app)


def _headers(subject: str) -> dict[str, str]:
    return {
        "x-freyja-client-type": "open-webui",
        "x-freyja-client-subject": subject,
    }


def test_continuity_remember_recall_and_private_scope_isolation(tmp_path) -> None:
    client = _client(tmp_path)

    write = client.post(
        "/freyja-core/continuity/memory/remember",
        headers=_headers("agent:cloyd"),
        json={
            "scope": "personal:joe",
            "owner": "joe",
            "content": "Joe wants Cloyd to prefer concise operator notes.",
            "provenance": "unit-test",
            "surface": "openwebui",
            "active_user": "joe",
            "active_agent": "cloyd",
        },
    )

    assert write.status_code == 200
    record = write.json()
    assert record["scope"] == "personal:joe"
    assert record["metadata"]["continuity_surface"] == "openwebui"
    assert record["metadata"]["continuity_active_agent"] == "cloyd"
    assert record["metadata"]["home_memory_provenance"] == "unit-test"

    recall = client.get(
        "/freyja-core/continuity/memory/search?scope=personal:joe&q=operator",
        headers=_headers("agent:cloyd"),
    )
    assert recall.status_code == 200
    assert recall.json()["records"][0]["content"] == "Joe wants Cloyd to prefer concise operator notes."

    beth_read = client.get(
        "/freyja-core/continuity/memory/search?scope=personal:joe&q=operator",
        headers=_headers("person:beth"),
    )
    assert beth_read.status_code == 403


def test_continuity_context_exposes_authoritative_core_policy(tmp_path) -> None:
    client = _client(tmp_path)

    context = client.get(
        "/freyja-core/continuity/context?surface=msty-go&active_user=joe&active_agent=cloyd",
        headers=_headers("agent:cloyd"),
    )

    assert context.status_code == 200
    payload = context.json()
    assert payload["principal"] == "agent:cloyd"
    assert payload["surface"] == "msty-go"
    assert "personal:joe" in payload["readable_scopes"]
    assert payload["policy"]["identity_authority"] == "atlas/freyja-core"
    assert payload["policy"]["user_private_scopes_isolated"] is True
    assert payload["policy"]["benedict_restricted_local_only"] is True


def test_cloyd_smith_record_can_write_job_summary_to_continuity_store(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr("freyja.config.settings.cloyd_smith_loop_database_path", str(database))
    test_store = MemoryStore(database_path=str(tmp_path / "continuity-memory.db"))
    test_store.initialize(force=True)
    memory_store.set_store(test_store)

    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Prove continuity recording.",
            current_prompt="Run a focused smoke.",
        )
    )

    result = asyncio.run(
        _cloyd_smith_record(
            ToolExecutionRequest(
                tool_name="cloyd_smith_record",
                actor="joe",
                arguments={
                    "job_id": job.job_id,
                    "event_type": "summary",
                    "payload": {"tests": "pass"},
                    "continuity_summary": "Cloyd-Smith proved the continuity smoke path.",
                    "continuity_scope": "project:freyja-os",
                    "continuity_owner": "freyja-os",
                },
            )
        )
    )

    assert result["ok"] is True
    assert result["continuity"]["content"] == "Cloyd-Smith proved the continuity smoke path."
    assert result["continuity"]["metadata"]["continuity_surface"] == "opencode"
    assert result["continuity"]["metadata"]["cloyd_smith_job_id"] == job.job_id

    recall = test_store.list_shared_memories(
        principal=result_principal("project:freyja-os"),
        limit=5,
    )
    assert recall.memories[0].content == "Cloyd-Smith proved the continuity smoke path."


def result_principal(scope: str):
    from freyja.home_memory import _scope_principal

    return _scope_principal(scope)
