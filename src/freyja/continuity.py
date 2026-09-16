from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from freyja.home_memory import (
    HomeMemoryRecord,
    HomeMemorySearchResponse,
    HomeMemoryWriteRequest,
    _authorize,
    _records_for_scope,
    _write_record,
)
from freyja.memory.principal import require_memory_principal
from freyja.memory.models import MemoryPrincipal


ContinuitySurface = Literal["openwebui", "opencode", "msty-go", "messaging", "core"]

_AGENT_IDENTITIES: dict[str, dict[str, Any]] = {
    "freyja": {
        "display_name": "Freyja",
        "principal": "agent:freyja",
        "role": "Household assistant and Atlas/Freyja authority surface.",
        "scopes": ["household", "project:freyja-os"],
    },
    "cloyd": {
        "display_name": "Cloyd",
        "principal": "agent:cloyd",
        "role": "Joe's technical triage and continuity agent.",
        "scopes": ["personal:joe", "household", "project:freyja-os"],
    },
    "smith": {
        "display_name": "Agent Smith",
        "principal": "agent:smith",
        "role": "Joe's constrained coding runtime through OpenCode.",
        "scopes": ["personal:joe", "project:freyja-os"],
    },
    "benedict": {
        "display_name": "Benedict",
        "principal": "agent:benedict",
        "role": "Beth's restricted local-only document agent.",
        "scopes": ["personal:beth", "restricted:benedict"],
    },
}


class ContinuityContext(BaseModel):
    active_user: str | None = None
    active_agent: str | None = None
    surface: ContinuitySurface = "core"
    principal: str
    readable_scopes: list[str]
    writable_scopes: list[str]
    authoritative_host: str = "atlas/freyja-core"
    policy: dict[str, Any] = Field(
        default_factory=lambda: {
            "identity_authority": "atlas/freyja-core",
            "memory_policy_authority": "atlas/freyja-core",
            "tool_grants_authority": "atlas/freyja-core",
            "approvals_authority": "atlas/freyja-core",
            "audit_authority": "atlas/freyja-core",
            "local_first_inference": True,
            "user_private_scopes_isolated": True,
            "benedict_restricted_local_only": True,
        }
    )


class ContinuityWriteRequest(HomeMemoryWriteRequest):
    surface: ContinuitySurface = "core"
    active_user: str | None = Field(default=None, max_length=128)
    active_agent: str | None = Field(default=None, max_length=128)


class ContinuityIdentityResponse(BaseModel):
    agents: dict[str, dict[str, Any]]
    authority: dict[str, str]
    public_surfaces: list[str]


class ContinuityCurrentWorkResponse(BaseModel):
    active: list[dict[str, Any]]
    recent_terminal: list[dict[str, Any]]


continuity_router = APIRouter(prefix="/freyja-core/continuity", tags=["freyja-core-continuity"])


@continuity_router.get("/identity", response_model=ContinuityIdentityResponse)
async def identity() -> ContinuityIdentityResponse:
    return ContinuityIdentityResponse(
        agents=_AGENT_IDENTITIES,
        authority={
            "identity": "atlas/freyja-core",
            "memory_policy": "atlas/freyja-core",
            "tool_grants": "atlas/freyja-core",
            "approvals": "atlas/freyja-core",
            "audit": "atlas/freyja-core",
        },
        public_surfaces=["openwebui", "opencode", "msty-go", "messaging"],
    )


@continuity_router.get("/context", response_model=ContinuityContext)
async def context(
    surface: ContinuitySurface = Query(default="core"),
    active_user: str | None = Query(default=None, max_length=128),
    active_agent: str | None = Query(default=None, max_length=128),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> ContinuityContext:
    from freyja.home_memory import _SCOPE_READS, _SCOPE_WRITES

    return ContinuityContext(
        active_user=active_user,
        active_agent=active_agent,
        surface=surface,
        principal=principal.client_subject,
        readable_scopes=sorted(_SCOPE_READS.get(principal.client_subject, set())),
        writable_scopes=sorted(_SCOPE_WRITES.get(principal.client_subject, set())),
    )


@continuity_router.get("/memory/search", response_model=HomeMemorySearchResponse)
async def search_memory(
    scope: str = Query(..., min_length=1, max_length=128),
    q: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=20, ge=1, le=100),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemorySearchResponse:
    _authorize(principal, scope, write=False)
    return HomeMemorySearchResponse(records=_records_for_scope(principal, scope, q=q, limit=limit))


@continuity_router.get("/memory/recent", response_model=HomeMemorySearchResponse)
async def recent_memory(
    scope: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemorySearchResponse:
    _authorize(principal, scope, write=False)
    return HomeMemorySearchResponse(records=_records_for_scope(principal, scope, q=None, limit=limit))


@continuity_router.post("/memory/remember", response_model=HomeMemoryRecord)
async def remember_memory(
    request: ContinuityWriteRequest,
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemoryRecord:
    return _write_record(principal, _continuity_request(request), operation="remember")


@continuity_router.post("/memory/record-decision", response_model=HomeMemoryRecord)
async def record_decision(
    request: ContinuityWriteRequest,
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> HomeMemoryRecord:
    return _write_record(principal, _continuity_request(request), operation="record-decision")


@continuity_router.get("/current-work", response_model=ContinuityCurrentWorkResponse)
async def current_work(
    limit: int = Query(default=20, ge=1, le=100),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> ContinuityCurrentWorkResponse:
    _authorize(principal, "project:freyja-os", write=False)
    from freyja.cloyd_smith_loop import CloydSmithJobStore, job_status_summary

    store = CloydSmithJobStore()
    active = [job_status_summary(job, heartbeat=store.get_heartbeat(job.job_id)) for job in store.list_active(limit=limit)]
    recent = [job_status_summary(job, heartbeat=store.get_heartbeat(job.job_id)) for job in store.list_recent_terminal(limit=limit)]
    return ContinuityCurrentWorkResponse(active=active, recent_terminal=recent)


def _continuity_request(request: ContinuityWriteRequest) -> HomeMemoryWriteRequest:
    metadata = dict(request.metadata or {})
    metadata.update(
        {
            "continuity_surface": request.surface,
            "continuity_active_user": request.active_user,
            "continuity_active_agent": request.active_agent,
        }
    )
    return HomeMemoryWriteRequest(
        scope=request.scope,
        owner=request.owner,
        content=request.content,
        provenance=request.provenance,
        sensitivity=request.sensitivity,
        record_id=request.record_id,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )
