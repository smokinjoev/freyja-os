import json
from pathlib import Path

from certification import freyja5_preflight_status as preflight


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-preflight-status.py"


def _write_report(path: Path, *, passed: bool, source_ready: bool, live_blocked: bool, checks: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "freyja5-readiness-bundle",
                "passed": passed,
                "source_ready": source_ready,
                "live_blocked": live_blocked,
                "checks": checks,
            }
        ),
        encoding="utf-8",
    )


def test_freyja5_preflight_reports_complete_for_passing_bundle(tmp_path: Path) -> None:
    report = tmp_path / "passing-freyja5-readiness-bundle.json"
    _write_report(report, passed=True, source_ready=True, live_blocked=False, checks=[])

    summary = preflight.summarize_report(report)

    assert summary.status == "complete"
    assert summary.exit_code == 0
    assert "Status: complete" in preflight.render_summary(summary)


def test_freyja5_preflight_reports_source_ready_live_blocked(tmp_path: Path) -> None:
    report = tmp_path / "live-blocked-freyja5-readiness-bundle.json"
    _write_report(
        report,
        passed=False,
        source_ready=True,
        live_blocked=True,
        checks=[
            {"name": "freyja5-certification-report", "ok": True, "status": "passed"},
            {"name": "freyja5-smoke-report", "ok": True, "status": "passed"},
            {
                "name": "freyja5-live-blockers",
                "ok": False,
                "status": "blocked",
                "remaining": ["vulcan_nexus_presets", "iris_apple_session"],
                "blockers": [
                    {
                        "id": "vulcan_nexus_presets",
                        "component": "vulcan",
                        "requires": ["local_only_fast_preset", "local_only_private_preset"],
                        "next_actions": ["Confirm Nexus presets on Vulcan."],
                    },
                    {
                        "id": "iris_apple_session",
                        "component": "iris",
                        "requires": ["live_apple_calendar_mcp_or_macagent_session"],
                        "next_actions": ["Run target C on Iris."],
                    },
                ],
            },
        ],
    )

    summary = preflight.summarize_report(report)
    payload = json.loads(preflight.render_summary_json(summary))

    assert summary.status == "source-ready-live-blocked"
    assert summary.exit_code == 2
    assert summary.failed_checks == ("freyja5-live-blockers",)
    assert payload["remaining"] == [
        "Resolve Joe-required blocker `vulcan_nexus_presets` (vulcan): local_only_fast_preset, local_only_private_preset. Next actions: Confirm Nexus presets on Vulcan.",
        "Resolve Joe-required blocker `iris_apple_session` (iris): live_apple_calendar_mcp_or_macagent_session. Next actions: Run target C on Iris.",
    ]


def test_freyja5_preflight_keeps_older_id_only_blocker_reports(tmp_path: Path) -> None:
    report = tmp_path / "id-only-freyja5-readiness-bundle.json"
    _write_report(
        report,
        passed=False,
        source_ready=True,
        live_blocked=True,
        checks=[
            {
                "name": "freyja5-live-blockers",
                "ok": False,
                "status": "blocked",
                "remaining": ["vulcan_nexus_presets"],
            },
        ],
    )

    summary = preflight.summarize_report(report)

    assert summary.remaining == (
        "Resolve Joe-required blocker `vulcan_nexus_presets` in FREYJA-5.0-BLOCKERS.md.",
    )


def test_freyja5_preflight_reports_not_ready_for_missing_artifacts(tmp_path: Path) -> None:
    report = tmp_path / "not-ready-freyja5-readiness-bundle.json"
    _write_report(
        report,
        passed=False,
        source_ready=False,
        live_blocked=True,
        checks=[
            {"name": "freyja5-certification-report", "ok": False, "status": "not supplied"},
            {"name": "freyja5-smoke-report", "ok": False, "status": "not supplied"},
        ],
    )

    summary = preflight.summarize_report(report)

    assert summary.status == "not-ready"
    assert summary.exit_code == 1
    assert summary.remaining == (
        "Resolve freyja5-certification-report: not supplied.",
        "Resolve freyja5-smoke-report: not supplied.",
    )


def test_latest_freyja5_readiness_bundle_uses_mtime(tmp_path: Path) -> None:
    older = tmp_path / "older-freyja5-readiness-bundle.json"
    newer = tmp_path / "newer-freyja5-readiness-bundle.json"
    _write_report(older, passed=True, source_ready=True, live_blocked=False, checks=[])
    _write_report(newer, passed=True, source_ready=True, live_blocked=False, checks=[])
    older.touch()
    newer.touch()

    assert preflight.latest_readiness_bundle(tmp_path) == newer


def test_freyja5_preflight_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111
