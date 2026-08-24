from __future__ import annotations

from freyja.agents.hierarchy import AgentName
from freyja.agents.instances.benedict import agent as benedict_agent
from freyja.agents.instances.cloyd_gibbler import agent as cloyd_agent
from freyja.agents.instances.freyja import agent as freyja_agent
from freyja.agents.legacy_memory import import_legacy_memory_file, parse_legacy_memory_markdown
from freyja.memory.store import MemoryStore


def _store(tmp_path) -> MemoryStore:
    store = MemoryStore(database_path=str(tmp_path / "agent-memory.db"))
    store.initialize()
    return store


def test_individual_agent_entrypoints_share_one_memory_backend(tmp_path) -> None:
    store = _store(tmp_path)
    freyja = freyja_agent.create(store=store)
    cloyd = cloyd_agent.create(store=store)
    benedict = benedict_agent.create(store=store)

    assert freyja.agent_id is AgentName.FREYJA
    assert cloyd.agent_id is AgentName.CLOYD_GIBBLER
    assert benedict.agent_id is AgentName.BENEDICT
    assert freyja.store.database_path == cloyd.store.database_path == benedict.store.database_path

    cloyd.remember_private(
        memory_id="joe-style",
        kind="preference",
        content="Joe wants direct answers.",
    )
    benedict.remember_private(
        memory_id="beth-style",
        kind="preference",
        content="Beth wants warm concise reminders.",
    )
    cloyd.remember_shared(
        memory_id="house-status",
        kind="project_state",
        content="Atlas is the shared control plane.",
    )

    assert [memory.memory_id for memory in cloyd.recall_private()] == ["joe-style"]
    assert [memory.memory_id for memory in benedict.recall_private()] == ["beth-style"]
    assert freyja.recall_private() == ()
    assert [memory.memory_id for memory in freyja.recall_shared()] == ["house-status"]
    assert [memory.memory_id for memory in benedict.recall_shared()] == ["house-status"]


def test_legacy_memory_markdown_parser_uses_pi_memory_shape() -> None:
    blocks = parse_legacy_memory_markdown(
        """
# Joe's Memory - Personal Agent Context

**Agent:** Cloyd

## Preferences

- Devil's advocate mode enabled
- Concise responses preferred

## Current Projects

- Multi-agent AI setup
""",
        source_name="MEMORY.md",
    )

    assert [block.title for block in blocks] == [
        "Joe's Memory - Personal Agent Context",
        "Preferences",
        "Current Projects",
    ]
    assert blocks[1].kind == "preference"
    assert blocks[2].kind == "project_state"
    assert blocks[1].memory_id == "legacy:memory-md:preferences"


def test_legacy_memory_import_can_stage_or_activate_private_and_shared_lanes(tmp_path) -> None:
    store = _store(tmp_path)
    cloyd = cloyd_agent.create(store=store)
    benedict = benedict_agent.create(store=store)
    source = tmp_path / "MEMORY.md"
    source.write_text(
        """
# Family Shared Memory

Cross-agent knowledge.

## AI Infrastructure

- Iris serves Apple-native actions.
""",
        encoding="utf-8",
    )

    dry_run = import_legacy_memory_file(cloyd, source, shared=True, dry_run=True)

    assert dry_run.imported == ()
    assert len(dry_run.blocks) == 2
    assert cloyd.recall_shared() == ()

    result = import_legacy_memory_file(cloyd, source, shared=True, dry_run=False)

    assert len(result.imported) == 2
    assert [memory.memory_id for memory in benedict.recall_shared()] == [
        "legacy:memory-md:ai-infrastructure",
        "legacy:memory-md:family-shared-memory",
    ]
    assert benedict.recall_private() == ()

    personal = tmp_path / "JOE_MEMORY.md"
    personal.write_text(
        """
# Joe's Memory

## Communication

- Challenge weak assumptions.
""",
        encoding="utf-8",
    )
    import_legacy_memory_file(cloyd, personal, shared=False, dry_run=False)

    assert [memory.memory_id for memory in cloyd.recall_private()] == [
        "legacy:joe-memory-md:communication"
    ]
    assert benedict.recall_private() == ()
