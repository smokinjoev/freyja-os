"""Benedict private agent entry point."""

from __future__ import annotations

from typing import Iterable

from freyja.agents.hierarchy import PersonName
from freyja.agents.process import AgentProcess, agent_cli, create_agent_process
from freyja.memory.store import MemoryStore


AGENT_PERSON = PersonName.BETH


def create(*, store: MemoryStore | None = None) -> AgentProcess:
    return create_agent_process(AGENT_PERSON, store=store)


def main(argv: Iterable[str] | None = None) -> int:
    return agent_cli(create(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
