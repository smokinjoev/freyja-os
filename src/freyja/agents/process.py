"""Runnable agent-process contract with private and shared memory lanes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Iterable

from freyja.agents.hierarchy import AgentHierarchy, AgentName, AgentProfile, PersonName
from freyja.memory.models import MemoryKind, MemoryPrincipal, PutSharedMemoryRequest, SharedMemory
from freyja.memory.principal import build_memory_principal
from freyja.memory.store import MemoryStore, get_store


@dataclass(frozen=True)
class AgentMemorySnapshot:
    agent: str
    owner: str
    private: tuple[SharedMemory, ...]
    shared: tuple[SharedMemory, ...]


class AgentProcess:
    """One concrete agent identity backed by the shared Freyja memory store."""

    def __init__(
        self,
        *,
        profile: AgentProfile,
        store: MemoryStore | None = None,
        hierarchy: AgentHierarchy | None = None,
    ) -> None:
        self.profile = profile
        self._store = store
        self._hierarchy = hierarchy or AgentHierarchy()
        self.private_principal = build_memory_principal(
            client_type="agent",
            client_subject=profile.client_subject,
            account_owner=profile.account_owner,
            conversation_id=f"agent-private:{profile.agent_id.value}",
        )
        family = self._hierarchy.profile_for_person(PersonName.FAMILY)
        self.shared_principal = build_memory_principal(
            client_type="agent",
            client_subject=family.client_subject,
            account_owner=family.account_owner,
        )

    @property
    def agent_id(self) -> AgentName:
        return self.profile.agent_id

    @property
    def owner(self) -> PersonName:
        return self.profile.owner

    @property
    def store(self) -> MemoryStore:
        return self._store or get_store()

    def remember_private(
        self,
        *,
        memory_id: str,
        kind: MemoryKind,
        content: str,
        confidence: float = 1.0,
    ) -> SharedMemory:
        return self._remember(
            principal=self.private_principal,
            visibility="private",
            memory_id=memory_id,
            kind=kind,
            content=content,
            confidence=confidence,
        )

    def remember_shared(
        self,
        *,
        memory_id: str,
        kind: MemoryKind,
        content: str,
        confidence: float = 1.0,
    ) -> SharedMemory:
        return self._remember(
            principal=self.shared_principal,
            visibility="household_shared",
            memory_id=memory_id,
            kind=kind,
            content=content,
            confidence=confidence,
        )

    def recall_private(
        self,
        *,
        kinds: list[str] | None = None,
        limit: int = 50,
    ) -> tuple[SharedMemory, ...]:
        return tuple(
            self.store.list_shared_memories(
                self.private_principal,
                kinds=kinds,
                limit=limit,
            ).memories
        )

    def recall_shared(
        self,
        *,
        kinds: list[str] | None = None,
        limit: int = 50,
    ) -> tuple[SharedMemory, ...]:
        return tuple(
            self.store.list_shared_memories(
                self.shared_principal,
                kinds=kinds,
                limit=limit,
            ).memories
        )

    def snapshot(self, *, limit: int = 50) -> AgentMemorySnapshot:
        return AgentMemorySnapshot(
            agent=self.agent_id.value,
            owner=self.owner.value,
            private=self.recall_private(limit=limit),
            shared=self.recall_shared(limit=limit),
        )

    def remember(
        self,
        *,
        memory_id: str,
        kind: MemoryKind,
        content: str,
        shared: bool,
        confidence: float = 1.0,
    ) -> SharedMemory:
        if shared:
            return self.remember_shared(
                memory_id=memory_id,
                kind=kind,
                content=content,
                confidence=confidence,
            )
        return self.remember_private(
            memory_id=memory_id,
            kind=kind,
            content=content,
            confidence=confidence,
        )

    def _remember(
        self,
        *,
        principal: MemoryPrincipal,
        visibility: str,
        memory_id: str,
        kind: MemoryKind,
        content: str,
        confidence: float,
    ) -> SharedMemory:
        return self.store.put_shared_memory(
            principal,
            PutSharedMemoryRequest(
                memory_id=memory_id,
                kind=kind,
                content=content,
                confidence=confidence,
                metadata={
                    "agent_id": self.agent_id.value,
                    "owner": self.owner.value,
                    "visibility": visibility,
                },
            ),
        )


def create_agent_process(
    person: PersonName,
    *,
    store: MemoryStore | None = None,
    hierarchy: AgentHierarchy | None = None,
) -> AgentProcess:
    resolved_hierarchy = hierarchy or AgentHierarchy()
    return AgentProcess(
        profile=resolved_hierarchy.profile_for_person(person),
        store=store,
        hierarchy=resolved_hierarchy,
    )


def agent_cli(agent: AgentProcess, argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=f"{agent.agent_id.value}.agent")
    parser.add_argument("command", choices=("whoami", "recall-private", "recall-shared"))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "whoami":
        print(f"{agent.profile.display_name} ({agent.agent_id.value}) owner={agent.owner.value}")
        print(f"private={agent.private_principal.scope_key}")
        print(f"shared={agent.shared_principal.scope_key}")
        return 0

    memories = (
        agent.recall_private(limit=args.limit)
        if args.command == "recall-private"
        else agent.recall_shared(limit=args.limit)
    )
    for memory in memories:
        print(f"{memory.memory_id}\t{memory.kind}\t{memory.content}")
    return 0
