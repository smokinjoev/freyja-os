#!/usr/bin/env python3
"""Validate Joe-supplied Freyja 5 live blocker evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from freyja.freyja5_config import freyja5_live_blocker_evidence  # noqa: E402


DEFAULT_EVIDENCE = Path("certification/reports/freyja5-live-evidence.json")
DEFAULT_OUTPUT = Path("certification/reports/freyja5-live-evidence-status.json")
SECRET_MARKERS = ("api_key", "apikey", "authorization", "bearer ", "password", "secret", "token")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Freyja 5 live blocker evidence without exposing secrets.")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def validate_live_evidence(path: Path) -> dict[str, Any]:
    blocker_config = freyja5_live_blocker_evidence()
    configured_blockers = {
        str(blocker["id"]): blocker
        for blocker in blocker_config["joe_required"]
        if isinstance(blocker, dict) and blocker.get("id")
    }
    payload = _read_json(path)
    submitted = _submitted_by_id(payload)
    blocker_statuses = [
        _validate_blocker(blocker_id, configured, submitted.get(blocker_id))
        for blocker_id, configured in configured_blockers.items()
    ]
    unknown_ids = sorted(set(submitted) - set(configured_blockers))
    closeable = [status["id"] for status in blocker_statuses if status["status"] == "complete"]
    remaining = [status["id"] for status in blocker_statuses if status["status"] != "complete"]
    secrets_detected = bool(_contains_secret_marker(payload))
    complete = bool(blocker_statuses) and not remaining and not unknown_ids and not secrets_detected
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-live-evidence-status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "config/freyja-5.0-live-blockers.yaml",
        "evidence": str(path),
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        "secrets_detected": secrets_detected,
        "closeable_blockers": closeable,
        "remaining_blockers": remaining,
        "unknown_blockers": unknown_ids,
        "blockers": blocker_statuses,
    }


def _validate_blocker(blocker_id: str, configured: dict[str, Any], submitted: dict[str, Any] | None) -> dict[str, Any]:
    required = [str(item) for item in configured.get("requires") or []]
    evidence = submitted.get("evidence") if isinstance(submitted, dict) and isinstance(submitted.get("evidence"), dict) else {}
    missing = [field for field in required if not _evidence_present(evidence.get(field))]
    explicit_status = str(submitted.get("status") or "") if isinstance(submitted, dict) else ""
    trace_ids = submitted.get("trace_ids") if isinstance(submitted, dict) and isinstance(submitted.get("trace_ids"), list) else []
    host = submitted.get("host") if isinstance(submitted, dict) else None
    status = "complete" if submitted and not missing and explicit_status not in {"failed", "blocked"} else "missing"
    if submitted and missing:
        status = "partial"
    return {
        "id": blocker_id,
        "component": configured.get("component"),
        "status": status,
        "required": required,
        "present": [field for field in required if field not in missing],
        "missing": missing,
        "host": host,
        "trace_ids": [str(trace_id) for trace_id in trace_ids],
        "next_actions": configured.get("next_actions") or [],
    }


def _submitted_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_blockers = payload.get("blockers")
    if isinstance(raw_blockers, list):
        return {
            str(entry["id"]): entry
            for entry in raw_blockers
            if isinstance(entry, dict) and entry.get("id")
        }
    if isinstance(raw_blockers, dict):
        return {
            str(blocker_id): {"id": str(blocker_id), **entry}
            for blocker_id, entry in raw_blockers.items()
            if isinstance(entry, dict)
        }
    return {}


def _evidence_present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _contains_secret_marker(value: Any, *, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if path == () and lowered_key in {"notes", "description"}:
                continue
            if any(marker.strip() in lowered_key for marker in SECRET_MARKERS):
                return True
            if _contains_secret_marker(item, path=(*path, lowered_key)):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_marker(item, path=path) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in SECRET_MARKERS)
    return False


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_live_evidence(args.evidence)
    except FileNotFoundError:
        report = {
            "schema_version": "1.0",
            "report_type": "freyja5-live-evidence-status",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": str(args.evidence),
            "status": "missing",
            "complete": False,
            "secrets_detected": False,
            "closeable_blockers": [],
            "remaining_blockers": [blocker["id"] for blocker in freyja5_live_blocker_evidence()["joe_required"]],
            "unknown_blockers": [],
            "blockers": [],
        }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("complete") is True else 2 if report.get("status") in {"incomplete", "missing"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
