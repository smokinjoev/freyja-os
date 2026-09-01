from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-live-evidence-status.py"
EXAMPLE_PATH = REPO_ROOT / "docs" / "examples" / "freyja5-live-evidence.example.json"


def load_status_module():
    spec = importlib.util.spec_from_file_location("freyja5_live_evidence_status", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_live_evidence_status_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111


def test_freyja5_live_evidence_status_reports_partial_blockers(tmp_path: Path) -> None:
    module = load_status_module()
    evidence = tmp_path / "live-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "iris_apple_session",
                        "host": "iris",
                        "evidence": {"live_apple_calendar_mcp_or_macagent_session": True},
                        "trace_ids": ["trace-iris-c"],
                    },
                    {
                        "id": "vulcan_nexus_presets",
                        "host": "vulcan",
                        "evidence": {"local_only_fast_preset": "fast-local"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = module.validate_live_evidence(evidence)
    blockers = {blocker["id"]: blocker for blocker in report["blockers"]}

    assert report["complete"] is False
    assert "iris_apple_session" in report["closeable_blockers"]
    assert blockers["iris_apple_session"]["status"] == "complete"
    assert blockers["iris_apple_session"]["trace_ids"] == ["trace-iris-c"]
    assert blockers["vulcan_nexus_presets"]["status"] == "partial"
    assert "local_only_general_preset" in blockers["vulcan_nexus_presets"]["missing"]


def test_freyja5_live_evidence_status_rejects_secret_markers(tmp_path: Path) -> None:
    module = load_status_module()
    evidence = tmp_path / "live-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "iris_apple_session",
                        "evidence": {"live_apple_calendar_mcp_or_macagent_session": True},
                        "token": "do-not-store-this",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = module.validate_live_evidence(evidence)

    assert report["secrets_detected"] is True
    assert report["complete"] is False


def test_freyja5_live_evidence_status_allows_top_level_operator_notes(tmp_path: Path) -> None:
    module = load_status_module()
    evidence = tmp_path / "live-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "notes": [
                    "Operator guidance may mention tokens and secrets as things not to include."
                ],
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    report = module.validate_live_evidence(evidence)

    assert report["secrets_detected"] is False


def test_freyja5_live_evidence_status_cli_writes_report(tmp_path: Path, capsys) -> None:
    module = load_status_module()
    evidence = tmp_path / "missing.json"
    output = tmp_path / "status.json"

    assert module.main(["--evidence", str(evidence), "--output", str(output)]) == 2

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert printed["status"] == "missing"
    assert written["report_type"] == "freyja5-live-evidence-status"
    assert "vulcan_nexus_presets" in written["remaining_blockers"]


def test_freyja5_live_evidence_example_is_complete_and_secret_free() -> None:
    module = load_status_module()

    report = module.validate_live_evidence(EXAMPLE_PATH)

    assert report["complete"] is True
    assert report["secrets_detected"] is False
    assert report["remaining_blockers"] == []
    assert report["unknown_blockers"] == []
    assert set(report["closeable_blockers"]) == {
        "msty_go_always_on_linux_validation",
        "vulcan_nexus_presets",
        "iris_apple_session",
        "hera_voice_avatar_hardware",
        "live_tool_sessions",
        "vulcan_nexus_private_preset",
    }
