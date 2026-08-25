from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from freyja.memory.models import MemoryProvenance
from freyja.memory.store import PROVENANCE_METADATA_KEY


@dataclass(frozen=True)
class MemoryProvenanceAudit:
    timestamp: str
    database_path: str
    shared_memory_count: int
    missing_provenance_count: int
    malformed_metadata_count: int
    malformed_provenance_count: int
    untrusted_authoritative_count: int
    normalized_default_count: int
    schema_version: str = "1.0"
    report_paths: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            self.malformed_metadata_count == 0
            and self.malformed_provenance_count == 0
            and self.untrusted_authoritative_count == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "database_path": self.database_path,
            "shared_memory_count": self.shared_memory_count,
            "missing_provenance_count": self.missing_provenance_count,
            "malformed_metadata_count": self.malformed_metadata_count,
            "malformed_provenance_count": self.malformed_provenance_count,
            "untrusted_authoritative_count": self.untrusted_authoritative_count,
            "normalized_default_count": self.normalized_default_count,
            "passed": self.passed,
            "report_paths": dict(self.report_paths),
        }


def audit_memory_provenance(database_path: Path) -> MemoryProvenanceAudit:
    shared_memory_count = 0
    missing_provenance_count = 0
    malformed_metadata_count = 0
    malformed_provenance_count = 0
    untrusted_authoritative_count = 0
    normalized_default_count = 0

    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "shared_memories"):
            raise ValueError("memory database does not contain shared_memories")
        rows = conn.execute("SELECT source, metadata FROM shared_memories").fetchall()
    finally:
        conn.close()

    shared_memory_count = len(rows)
    for row in rows:
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except Exception:
            malformed_metadata_count += 1
            continue
        if not isinstance(metadata, dict):
            malformed_metadata_count += 1
            continue
        raw_provenance = metadata.get(PROVENANCE_METADATA_KEY)
        if raw_provenance is None:
            missing_provenance_count += 1
            normalized_default_count += 1
            continue
        if not isinstance(raw_provenance, dict):
            malformed_provenance_count += 1
            continue
        try:
            provenance = MemoryProvenance.model_validate(raw_provenance)
        except Exception:
            malformed_provenance_count += 1
            continue
        if provenance.trust_level == "untrusted_external_content" and provenance.authoritative:
            untrusted_authoritative_count += 1

    return MemoryProvenanceAudit(
        timestamp=datetime.now(UTC).isoformat(),
        database_path=str(database_path),
        shared_memory_count=shared_memory_count,
        missing_provenance_count=missing_provenance_count,
        malformed_metadata_count=malformed_metadata_count,
        malformed_provenance_count=malformed_provenance_count,
        untrusted_authoritative_count=untrusted_authoritative_count,
        normalized_default_count=normalized_default_count,
    )


def write_memory_audit_report(report: MemoryProvenanceAudit, output_dir: Path) -> MemoryProvenanceAudit:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _report_stem(report.timestamp)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    with_paths = MemoryProvenanceAudit(
        timestamp=report.timestamp,
        database_path=report.database_path,
        shared_memory_count=report.shared_memory_count,
        missing_provenance_count=report.missing_provenance_count,
        malformed_metadata_count=report.malformed_metadata_count,
        malformed_provenance_count=report.malformed_provenance_count,
        untrusted_authoritative_count=report.untrusted_authoritative_count,
        normalized_default_count=report.normalized_default_count,
        schema_version=report.schema_version,
        report_paths={"json": str(json_path), "markdown": str(md_path)},
    )
    json_path.write_text(json.dumps(with_paths.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_memory_audit_markdown(with_paths), encoding="utf-8")
    return with_paths


def render_memory_audit_markdown(report: MemoryProvenanceAudit) -> str:
    return "\n".join(
        [
            "# Rev 2 Memory Provenance Audit",
            "",
            f"- Timestamp: {report.timestamp}",
            f"- Database path: {report.database_path}",
            f"- Shared memory rows: {report.shared_memory_count}",
            f"- Missing provenance rows: {report.missing_provenance_count}",
            f"- Normalized default rows: {report.normalized_default_count}",
            f"- Malformed metadata rows: {report.malformed_metadata_count}",
            f"- Malformed provenance rows: {report.malformed_provenance_count}",
            f"- Untrusted authoritative rows: {report.untrusted_authoritative_count}",
            f"- Passed: {report.passed}",
            "",
        ]
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _report_stem(timestamp: str) -> str:
    safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("+", "Z")
    return f"{safe_timestamp}-rev2-memory-provenance"
