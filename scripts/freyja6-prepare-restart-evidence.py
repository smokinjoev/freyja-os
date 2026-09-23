#!/usr/bin/env python3
"""Seed Freyja 6 persistence artifacts before restart validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_HERMES_DATA = Path(os.environ.get("FREYJA6_HERMES_DATA", "/srv/freyja6/hermes"))
AGENT_ID = "freyja-test"
DEFAULT_FACT_LABEL = "freyja6-validation-basement-cleanup"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Freyja 6 restart/session/memory validation artifacts.")
    parser.add_argument("--hermes-data", type=Path, default=DEFAULT_HERMES_DATA)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--stored-fact-label", default=DEFAULT_FACT_LABEL)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing validation session or fact marker.")
    return parser


def prepare(*, hermes_data: Path, session_id: str = "", stored_fact_label: str = DEFAULT_FACT_LABEL, force: bool = False) -> dict[str, Any]:
    agent_root = hermes_data / "agents" / AGENT_ID
    identity_file = agent_root / "identity.md"
    sessions_dir = agent_root / "sessions"
    memory_dir = agent_root / "memory" / "private"
    fact_file = memory_dir / "freyja6-validation-fact.json"
    session_name = session_id or f"freyja6-validation-{uuid.uuid4().hex[:12]}"
    input_failures = _input_failures(session_name=session_name, stored_fact_label=stored_fact_label)
    if input_failures:
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-prepare-restart-evidence",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": AGENT_ID,
            "identity_file_redacted": f"hermes/agents/{AGENT_ID}/identity.md",
            "identity_sha256_before": _sha256_file(identity_file),
            "session_id": session_name,
            "session_file_redacted": f"hermes/agents/{AGENT_ID}/sessions/{Path(session_name).name}",
            "stored_fact_label": stored_fact_label,
            "memory_fact_file_redacted": f"hermes/agents/{AGENT_ID}/memory/private/{fact_file.name}",
            "writes": [],
            "input_failures": input_failures,
            "next_restart_command": "",
        }
    session_file = sessions_dir / session_name

    sessions_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    marker_failures = _marker_target_failures(
        [
            {"label": "session_marker", "path": session_file},
            {"label": "memory_fact", "path": fact_file},
        ]
    )
    if marker_failures:
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-prepare-restart-evidence",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": AGENT_ID,
            "identity_file_redacted": f"hermes/agents/{AGENT_ID}/identity.md",
            "identity_sha256_before": _sha256_file(identity_file),
            "session_id": session_name,
            "session_file_redacted": f"hermes/agents/{AGENT_ID}/sessions/{Path(session_name).name}",
            "stored_fact_label": stored_fact_label,
            "memory_fact_file_redacted": f"hermes/agents/{AGENT_ID}/memory/private/{fact_file.name}",
            "writes": [],
            "input_failures": ["Restart marker targets must be regular files and must not be symlinks."],
            "marker_failures": marker_failures,
            "next_restart_command": "",
        }

    writes = [
        _write_json(
            session_file,
            {
                "schema_version": "1.0",
                "type": "freyja6-validation-session-marker",
                "agent_id": AGENT_ID,
                "session_id": session_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "purpose": "restart/session persistence validation",
            },
            force=force,
            label="session_marker",
        ),
        _write_json(
            fact_file,
            {
                "schema_version": "1.0",
                "type": "freyja6-validation-memory-fact",
                "agent_id": AGENT_ID,
                "label": stored_fact_label,
                "fact": "The Freyja 6 validation memory fact is stored before restart and must be recalled after restart.",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            force=force,
            label="memory_fact",
        ),
    ]

    return {
        "schema_version": "1.0",
        "report_type": "freyja6-prepare-restart-evidence",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": AGENT_ID,
        "identity_file_redacted": f"hermes/agents/{AGENT_ID}/identity.md",
        "identity_sha256_before": _sha256_file(identity_file),
        "session_id": session_name,
        "session_file_redacted": f"hermes/agents/{AGENT_ID}/sessions/{session_name}",
        "stored_fact_label": stored_fact_label,
        "memory_fact_file_redacted": f"hermes/agents/{AGENT_ID}/memory/private/{fact_file.name}",
        "writes": writes,
        "next_restart_command": _next_restart_command(session_name, stored_fact_label),
    }


def update_evidence(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    payload = _load_evidence(path)
    _acceptance_map(payload)
    payload["restart_validation_prepared"] = {
        "agent_id": AGENT_ID,
        "identity_before": "sha256:" + report["identity_sha256_before"] if report.get("identity_sha256_before") else "",
        "session_id": report["session_id"],
        "stored_fact_label": report["stored_fact_label"],
        "memory_fact_file_redacted": report["memory_fact_file_redacted"],
        "prepared_at": report["timestamp"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _prepare_report_ok(report: dict[str, Any]) -> bool:
    writes = report.get("writes")
    if not (
        not report.get("input_failures")
        and report.get("identity_sha256_before")
        and report.get("session_id")
        and report.get("stored_fact_label")
        and isinstance(writes, list)
    ):
        return False
    expected_labels = {"session_marker", "memory_fact"}
    allowed_actions = {"created", "overwritten", "preserved"}
    labels = {str(item.get("label") or "") for item in writes if isinstance(item, dict)}
    if labels != expected_labels:
        return False
    return all(isinstance(item, dict) and item.get("action") in allowed_actions for item in writes)


def _input_failures(*, session_name: str, stored_fact_label: str) -> list[str]:
    failures: list[str] = []
    if not _safe_identifier(session_name):
        failures.append("session_id must be a non-empty local identifier using only letters, numbers, dot, underscore, and hyphen.")
    if not _safe_identifier(stored_fact_label):
        failures.append("stored_fact_label must be a non-empty local identifier using only letters, numbers, dot, underscore, and hyphen.")
    return failures


def _safe_identifier(value: str) -> bool:
    text = str(value).strip()
    if not text or text in {".", ".."}:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return all(character in allowed for character in text)


def _write_json(path: Path, payload: dict[str, Any], *, force: bool, label: str) -> dict[str, str]:
    if path.exists() and not force:
        return {"label": label, "path_redacted": _redact_path(path), "action": "preserved"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"label": label, "path_redacted": _redact_path(path), "action": "overwritten" if force else "created"}


def _marker_target_failures(targets: list[dict[str, Path | str]]) -> list[dict[str, str]]:
    failures = []
    for target in targets:
        label = str(target["label"])
        path = target["path"]
        if not isinstance(path, Path):
            path = Path(path)
        if path.is_symlink():
            failures.append({"label": label, "path_redacted": _redact_path(path), "reason": "must not be a symlink"})
        elif path.exists() and not path.is_file():
            failures.append({"label": label, "path_redacted": _redact_path(path), "reason": "must be a regular file"})
    return failures


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _next_restart_command(session_id: str, stored_fact_label: str) -> str:
    return (
        ".venv/bin/python scripts/freyja6-restart-evidence.py "
        "--before-identity-sha256 \"$FREYJA6_IDENTITY_SHA256_BEFORE\" "
        f"--session-id {session_id} "
        f"--stored-fact-label {stored_fact_label}"
    )


def _redact_path(path: Path) -> str:
    parts = list(path.parts)
    if "hermes" in parts:
        index = parts.index("hermes")
        return str(Path(*parts[index:]))
    return path.name


def _load_evidence(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("Live evidence file must not be a symlink.")
    if path.exists() and not path.is_file():
        raise ValueError("Live evidence file must be a regular file.")
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("schema_version", "1.0")
            payload.setdefault("report_type", "freyja6-live-evidence")
            payload.setdefault("acceptance", {})
            return payload
    return {"schema_version": "1.0", "report_type": "freyja6-live-evidence", "acceptance": {}}


def _acceptance_map(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "1.0" or payload.get("report_type") != "freyja6-live-evidence":
        raise ValueError("Live evidence file must be a freyja6-live-evidence schema_version 1.0 artifact.")
    acceptance = payload.setdefault("acceptance", {})
    if not isinstance(acceptance, dict):
        raise ValueError("Live evidence acceptance must be an object before smoke helpers can update it.")
    return acceptance


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _acceptance_map(_load_evidence(args.evidence))
    except ValueError as exc:
        print(
            json.dumps(
                {"ok": False, "evidence": str(args.evidence), "evidence_updated": False, "error": str(exc)},
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    report = prepare(
        hermes_data=args.hermes_data,
        session_id=args.session_id,
        stored_fact_label=args.stored_fact_label,
        force=args.force,
    )
    ok = _prepare_report_ok(report)
    if ok:
        try:
            update_evidence(args.evidence, report)
        except ValueError as exc:
            print(
                json.dumps(
                    {"ok": False, "evidence": str(args.evidence), "evidence_updated": False, "error": str(exc), "report": report},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 2
    print(
        json.dumps(
            {"ok": ok, "evidence": str(args.evidence), "evidence_updated": ok, "report": report},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
