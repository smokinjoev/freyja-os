#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP = REPO_ROOT / "logs" / "open-webui-diagnostics" / "home-agent-20260904T174214Z" / "open-webui-data-volume.tgz"
DEFAULT_RUNBOOK = REPO_ROOT / "docs" / "operations" / "open-webui-home-agent.md"
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-backup-rollback-audit.json"
REQUIRED_ROLLBACK_PHRASES = (
    "docker compose --env-file deploy/compose/open-webui/.env",
    "git apply .codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch",
    "open-webui-data-volume.tgz",
    "tar -xzf",
    "http://127.0.0.1:3001/api/version",
)
ROLLBACK_STEPS = [
    {
        "step": "stop_open_webui",
        "command": "docker compose --env-file deploy/compose/open-webui/.env -f deploy/compose/open-webui/docker-compose.yml down",
    },
    {
        "step": "restore_source_checkpoint",
        "command": "git apply .codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch",
    },
    {
        "step": "restore_open_webui_volume",
        "command": "tar -xzf logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz -C <restored-open-webui-data-volume>",
    },
    {
        "step": "start_open_webui",
        "command": "docker compose --env-file deploy/compose/open-webui/.env -f deploy/compose/open-webui/docker-compose.yml up -d",
    },
    {
        "step": "verify_open_webui",
        "command": "curl -fsS --max-time 10 http://127.0.0.1:3001/api/version",
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Open WebUI backup integrity and rollback documentation without exposing data.")
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--runbook", type=Path, default=DEFAULT_RUNBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_members(path: Path) -> list[tarfile.TarInfo]:
    with tarfile.open(path, "r:gz") as archive:
        return archive.getmembers()


def _safe_member_summary(members: list[tarfile.TarInfo]) -> dict[str, Any]:
    names = [member.name.lstrip("./") for member in members]
    sqlite_like = sorted(name for name in names if name.endswith((".db", ".sqlite", ".sqlite3")))
    config_like = sorted(
        name
        for name in names
        if name.endswith((".json", ".yaml", ".yml", ".toml", ".env"))
        or "/config" in f"/{name}"
        or name == "config"
    )
    return {
        "member_count": len(members),
        "regular_file_count": sum(1 for member in members if member.isfile()),
        "directory_count": sum(1 for member in members if member.isdir()),
        "sqlite_like_entries": sqlite_like[:20],
        "config_like_entries": config_like[:20],
        "contains_webui_db": any(name.endswith("webui.db") for name in names),
        "contains_upload_or_cache_dirs": any(name.startswith(("uploads/", "cache/", "vector_db/")) for name in names),
    }


def build_report(backup: Path = DEFAULT_BACKUP, runbook: Path = DEFAULT_RUNBOOK) -> dict[str, Any]:
    backup_exists = backup.exists()
    tar_ok = False
    summary: dict[str, Any] = {}
    errors: list[str] = []
    if backup_exists:
        try:
            members = _tar_members(backup)
            tar_ok = True
            summary = _safe_member_summary(members)
        except Exception as exc:
            errors.append(exc.__class__.__name__)
    else:
        errors.append("backup_missing")

    runbook_text = runbook.read_text(encoding="utf-8") if runbook.exists() else ""
    missing_phrases = [phrase for phrase in REQUIRED_ROLLBACK_PHRASES if phrase not in runbook_text]
    report = {
        "report_type": "open-webui-backup-rollback-audit",
        "generated_at_unix": int(time.time()),
        "secrets_included": False,
        "private_content_included": False,
        "backup": {
            "path": str(backup.relative_to(REPO_ROOT) if backup.is_relative_to(REPO_ROOT) else backup),
            "exists": backup_exists,
            "size_bytes": backup.stat().st_size if backup_exists else 0,
            "sha256": _sha256(backup) if backup_exists else None,
            "tar_gzip_readable": tar_ok,
            **summary,
        },
        "rollback_documentation": {
            "path": str(runbook.relative_to(REPO_ROOT) if runbook.is_relative_to(REPO_ROOT) else runbook),
            "exists": runbook.exists(),
            "missing_required_phrases": missing_phrases,
            "steps": ROLLBACK_STEPS,
        },
        "errors": errors,
    }
    report["ok"] = (
        backup_exists
        and tar_ok
        and summary.get("contains_webui_db") is True
        and summary.get("regular_file_count", 0) > 0
        and runbook.exists()
        and not missing_phrases
        and not errors
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.backup, args.runbook)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
