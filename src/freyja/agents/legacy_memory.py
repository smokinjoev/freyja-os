"""Import legacy Raspberry Pi/OpenClaw markdown memories into agent memory lanes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from freyja.agents.process import AgentProcess
from freyja.memory.models import MemoryKind, SharedMemory


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class LegacyMemoryBlock:
    title: str
    content: str
    kind: MemoryKind
    memory_id: str


@dataclass(frozen=True)
class LegacyMemoryImportResult:
    source_path: str
    agent: str
    shared: bool
    dry_run: bool
    blocks: tuple[LegacyMemoryBlock, ...]
    imported: tuple[SharedMemory, ...]


def parse_legacy_memory_markdown(
    text: str,
    *,
    source_name: str,
) -> tuple[LegacyMemoryBlock, ...]:
    """Split old MEMORY.md files into durable, reviewable memory blocks."""
    blocks: list[LegacyMemoryBlock] = []
    current_title = "summary"
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        match = _HEADING_RE.match(raw_line)
        if match:
            _append_block(
                blocks,
                source_name=source_name,
                title=current_title,
                lines=current_lines,
            )
            current_title = _clean_heading(match.group(2))
            current_lines = []
            continue
        current_lines.append(raw_line)

    _append_block(
        blocks,
        source_name=source_name,
        title=current_title,
        lines=current_lines,
    )
    return tuple(blocks)


def import_legacy_memory_file(
    agent: AgentProcess,
    path: str | Path,
    *,
    shared: bool,
    dry_run: bool = True,
) -> LegacyMemoryImportResult:
    source = Path(path).expanduser()
    text = source.read_text(encoding="utf-8")
    blocks = parse_legacy_memory_markdown(text, source_name=source.name)
    imported: list[SharedMemory] = []

    if not dry_run:
        for block in blocks:
            imported.append(
                agent.remember(
                    memory_id=block.memory_id,
                    kind=block.kind,
                    content=block.content,
                    shared=shared,
                    confidence=0.75,
                )
            )

    return LegacyMemoryImportResult(
        source_path=str(source),
        agent=agent.agent_id.value,
        shared=shared,
        dry_run=dry_run,
        blocks=blocks,
        imported=tuple(imported),
    )


def _append_block(
    blocks: list[LegacyMemoryBlock],
    *,
    source_name: str,
    title: str,
    lines: list[str],
) -> None:
    content = "\n".join(lines).strip()
    if not content:
        return
    clean_title = _clean_heading(title)
    blocks.append(
        LegacyMemoryBlock(
            title=clean_title,
            content=content,
            kind=_classify_kind(clean_title, content),
            memory_id=f"legacy:{_slug(source_name)}:{_slug(clean_title)}",
        )
    )


def _classify_kind(title: str, content: str) -> MemoryKind:
    haystack = f"{title}\n{content}".lower()
    if any(term in haystack for term in ("preference", "communication", "how i should behave")):
        return "preference"
    if any(term in haystack for term in ("active", "status", "project", "setup", "infrastructure", "goals")):
        return "project_state"
    if "summary" in title.lower():
        return "summary"
    return "fact"


def _clean_heading(value: str) -> str:
    return value.strip().strip("#").strip(" -")


def _slug(value: str) -> str:
    lowered = value.lower().strip()
    slug = _SLUG_RE.sub("-", lowered).strip("-")
    return slug[:80] or "memory"
