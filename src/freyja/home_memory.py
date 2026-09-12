from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from freyja.memory.models import MemoryPrincipal, PutSharedMemoryRequest, SharedMemory
from freyja.memory.principal import require_memory_principal
from freyja.memory.store import (
    MemoryStorageError,
    get_active_store,
)


HomeMemoryOperation = Literal["search", "remember", "update", "forget", "record-decision", "recent-events"]
HomeMemorySensitivity = Literal["routine", "private", "sensitive"]

_SCOPE_READS: dict[str, set[str]] = {
    "person:joe": {"personal:joe", "household", "project:freyja-os"},
    "person:beth": {"personal:beth", "household", "project:freyja-os", "restricted:benedict"},
    "person:liam": {"personal:liam", "household"},
    "person:jenna": {"personal:jenna", "household"},
    "agent:freyja": {"household", "project:freyja-os"},
    "agent:cloyd": {"personal:joe", "household", "project:freyja-os"},
    "agent:smith": {"personal:joe", "project:freyja-os"},
    "agent:benedict": {"personal:beth", "restricted:benedict"},
    "agent:agent-44": {"personal:liam", "household"},
    "agent:jenna": {"personal:jenna", "household"},
}

_SCOPE_WRITES: dict[str, set[str]] = {
    key: set(value) for key, value in _SCOPE_READS.items()
}
_SCOPE_WRITES["agent:freyja"] = {"household", "project:freyja-os"}
_SCOPE_WRITES["agent:smith"] = {"project:freyja-os"}
_SCOPE_WRITES["agent:benedict"] = {"restricted:benedict"}
_SCOPE_WRITES["agent:agent-44"] = set()
_SCOPE_WRITES["agent:jenna"] = set()


class HomeMemoryRecord(BaseModel):
    id: str
    scope: str
    owner: str
    content: str
    operation: HomeMemoryOperation
    provenance: str
    created_at: datetime
    updated_at: datetime
    sensitivity: HomeMemorySensitivity
    metadata: dict = Field(default_factory=dict)


class HomeMemoryWriteRequest(BaseModel):
    scope: str = Field(min_length=1, max_length=128)
    owner: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    provenance: str = Field(min_length=1, max_length=128)
    sensitivity: HomeMemorySensitivity = "private"
    record_id: str | None = Field(default=None, max_length=128)
    metadata: dict | None = None


class HomeMemorySearchResponse(BaseModel):
    records: list[HomeMemoryRecord]


home_memory_router = APIRouter(prefix="/freyja-home-memory", tags=["freyja-home-memory"])


@home_memory_router.get("/operations")
async def operations() -> dict[str, list[HomeMemoryOperation]]:
    return {"operations": ["search", "remember", "update", "forget", "record-decision", "recent-events"]}


@home_memory_router.get("/search", response_model=HomeMemorySearchResponse)
async def search(
    scope: str = Query(..., min_length=1, max_length=128),
    q: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=20, ge=1, le=100),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemorySearchResponse:
    _authorize(principal, scope, write=False)
    return HomeMemorySearchResponse(records=_records_for_scope(principal, scope, q=q, limit=limit))


@home_memory_router.get("/recent-events", response_model=HomeMemorySearchResponse)
async def recent_events(
    scope: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemorySearchResponse:
    _authorize(principal, scope, write=False)
    return HomeMemorySearchResponse(records=_records_for_scope(principal, scope, q=None, limit=limit))


@home_memory_router.post("/remember", response_model=HomeMemoryRecord)
async def remember(
    request: HomeMemoryWriteRequest,
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemoryRecord:
    return _write_record(principal, request, operation="remember")


@home_memory_router.post("/update", response_model=HomeMemoryRecord)
async def update(
    request: HomeMemoryWriteRequest,
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemoryRecord:
    if not request.record_id:
        raise HTTPException(status_code=400, detail="record_id is required for update")
    return _write_record(principal, request, operation="update")


@home_memory_router.post("/record-decision", response_model=HomeMemoryRecord)
async def record_decision(
    request: HomeMemoryWriteRequest,
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemoryRecord:
    return _write_record(principal, request, operation="record-decision")


@home_memory_router.delete("/forget/{scope}/{record_id}")
async def forget(
    scope: str,
    record_id: str,
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> dict[str, bool]:
    _authorize(principal, scope, write=True)
    try:
        deleted = get_active_store().delete_shared_memory(_scope_principal(scope), record_id)
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return {"deleted": True}


def _write_record(
    principal: MemoryPrincipal,
    request: HomeMemoryWriteRequest,
    *,
    operation: HomeMemoryOperation,
) -> HomeMemoryRecord:
    _authorize(principal, request.scope, write=True)
    record_id = request.record_id or f"{operation}-{uuid.uuid4()}"
    metadata = dict(request.metadata or {})
    metadata.update(
        {
            "home_memory_scope": request.scope,
            "home_memory_owner": request.owner,
            "home_memory_operation": operation,
            "home_memory_provenance": request.provenance,
        }
    )
    try:
        memory = get_active_store().put_shared_memory(
            _scope_principal(request.scope),
            PutSharedMemoryRequest(
                memory_id=record_id,
                kind="project_state" if operation in {"record-decision", "recent-events"} else "fact",
                content=request.content,
                source=request.provenance,
                sensitivity=request.sensitivity,
                metadata=metadata,
            ),
        )
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None
    return _record_from_memory(memory)


def _records_for_scope(
    principal: MemoryPrincipal,
    scope: str,
    *,
    q: str | None,
    limit: int,
    operation: HomeMemoryOperation | None = None,
) -> list[HomeMemoryRecord]:
    store = get_active_store()
    try:
        memories = store.list_shared_memories(_scope_principal(scope), limit=limit).memories
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Memory storage unavailable") from None
    records = [_record_from_memory(memory) for memory in memories]
    if q:
        needle = q.casefold()
        records = [record for record in records if needle in record.content.casefold()]
    if operation:
        records = [record for record in records if record.operation == operation]
    return records[:limit]


def _record_from_memory(memory: SharedMemory) -> HomeMemoryRecord:
    metadata = dict(memory.metadata or {})
    return HomeMemoryRecord(
        id=memory.memory_id,
        scope=str(metadata.get("home_memory_scope") or memory.client_subject),
        owner=str(metadata.get("home_memory_owner") or memory.account_owner or memory.client_subject),
        content=memory.content,
        operation=metadata.get("home_memory_operation") or "remember",
        provenance=str(metadata.get("home_memory_provenance") or memory.source),
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        sensitivity=memory.sensitivity,
        metadata=metadata,
    )


def _scope_principal(scope: str) -> MemoryPrincipal:
    return MemoryPrincipal(
        client_type="freyja-home-memory",
        client_subject=f"scope:{scope}",
        account_owner=scope.split(":", 1)[-1] if ":" in scope else scope,
    )


def _authorize(principal: MemoryPrincipal, scope: str, *, write: bool) -> None:
    subject = principal.client_subject
    allowed = (_SCOPE_WRITES if write else _SCOPE_READS).get(subject, set())
    if scope not in allowed:
        raise HTTPException(status_code=403, detail="Scope is not authorized for this principal")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
