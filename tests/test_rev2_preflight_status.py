import json
import tomllib
from pathlib import Path

from certification import rev2_preflight_status as preflight

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rev2-preflight-status.py"


def _write_report(path: Path, *, passed: bool, checks: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "passed": passed,
                "director_url": "http://127.0.0.1:8000",
                "smoke_report": None,
                "vulcan_report": None,
                "latency_winner_target": "director:health",
                "checks": checks,
            }
        ),
        encoding="utf-8",
    )


def test_preflight_status_reports_complete_for_passing_report(tmp_path: Path) -> None:
    report = tmp_path / "passing-rev2-readiness.json"
    _write_report(report, passed=True, checks=[{"name": "provider-health", "passed": True, "status": "ok"}])

    summary = preflight.summarize_report(report)

    assert summary.status == "complete"
    assert summary.exit_code == 0
    assert "Status: complete" in preflight.render_summary(summary)


def test_preflight_status_reports_ready_for_final_smoke(tmp_path: Path) -> None:
    report = tmp_path / "smoke-rev2-readiness.json"
    _write_report(
        report,
        passed=False,
        checks=[
            {"name": "provider-health", "passed": True, "status": "ok"},
            {
                "name": "imessage-live-smoke-report",
                "passed": False,
                "status": "missing required --smoke-report",
            },
        ],
    )

    summary = preflight.summarize_report(report)
    rendered = preflight.render_summary(summary)

    assert summary.status == "ready-for-final-smoke"
    assert summary.exit_code == 2
    assert summary.failed_checks == ("imessage-live-smoke-report",)
    assert "scripts/rev2-readiness-bundle.py --imessage-live-smoke --yes" in rendered


def test_preflight_status_renders_json_for_automation(tmp_path: Path) -> None:
    report = tmp_path / "smoke-rev2-readiness.json"
    _write_report(
        report,
        passed=False,
        checks=[
            {
                "name": "imessage-live-smoke-report",
                "passed": False,
                "status": "missing required --smoke-report",
            },
        ],
    )

    summary = preflight.summarize_report(report)
    payload = json.loads(preflight.render_summary_json(summary))

    assert payload == {
        "director_url": "http://127.0.0.1:8000",
        "dry_run_command": None,
        "exit_code": 2,
        "failed_checks": ["imessage-live-smoke-report"],
        "final_command": None,
        "latency_winner_target": "director:health",
        "passed": False,
        "remaining": ["Run scripts/rev2-readiness-bundle.py --imessage-live-smoke --yes after approval."],
        "report_path": str(report),
        "signal_readiness_report": None,
        "signal_smoke_report": None,
        "smoke_report": None,
        "status": "ready-for-final-smoke",
        "vulcan_report": None,
    }


def test_preflight_status_builds_full_final_command_from_readiness_evidence(tmp_path: Path) -> None:
    report = tmp_path / "smoke-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "certification_report": "certification/reports/rev2.json",
                "benchmark_report": "certification/benchmarks/bench.json",
                "connector_reports": ["certification/reports/imessage.json"],
                "memory_report": "certification/reports/memory.json",
                "approval_report": "certification/reports/approval report.json",
                "vulcan_report": "certification/reports/vulcan.json",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "imessage-live-smoke-report",
                        "passed": False,
                        "status": "missing required --smoke-report",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)
    payload = json.loads(preflight.render_summary_json(summary))

    assert summary.final_command == (
        "scripts/rev2-readiness-bundle.py --director-url http://127.0.0.1:8000 "
        "--certification-report certification/reports/rev2.json "
        "--benchmark-report certification/benchmarks/bench.json "
        "--connector-report certification/reports/imessage.json "
        "--memory-report certification/reports/memory.json "
        "--approval-report 'certification/reports/approval report.json' "
        "--vulcan-report certification/reports/vulcan.json "
        "--imessage-live-smoke --yes --require-smoke-report --require-signal-smoke-report "
        "--require-vulcan-report "
        "--latency-winner-target director:health"
    )
    assert summary.dry_run_command == (
        "scripts/rev2-readiness-bundle.py --director-url http://127.0.0.1:8000 "
        "--certification-report certification/reports/rev2.json "
        "--benchmark-report certification/benchmarks/bench.json "
        "--connector-report certification/reports/imessage.json "
        "--memory-report certification/reports/memory.json "
        "--approval-report 'certification/reports/approval report.json' "
        "--vulcan-report certification/reports/vulcan.json "
        "--imessage-live-smoke --require-smoke-report --require-signal-smoke-report "
        "--require-vulcan-report "
        "--latency-winner-target director:health"
    )
    assert payload["final_command"] == summary.final_command
    assert payload["dry_run_command"] == summary.dry_run_command
    assert payload["remaining"] == [
        f"Review dry-run first: {summary.dry_run_command}",
        f"After approval, run: {summary.final_command}",
    ]


def test_preflight_status_builds_signal_final_command_from_readiness_evidence(tmp_path: Path) -> None:
    report = tmp_path / "signal-smoke-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "certification_report": "certification/reports/rev2.json",
                "benchmark_report": "certification/benchmarks/bench.json",
                "connector_reports": ["certification/reports/signal.json"],
                "memory_report": "certification/reports/memory.json",
                "approval_report": "certification/reports/approval.json",
                "vulcan_report": "certification/reports/vulcan.json",
                "smoke_report": "certification/reports/imessage-live-smoke-sent.json",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "signal-live-smoke-report",
                        "passed": False,
                        "status": "missing required --signal-smoke-report",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)

    assert summary.status == "ready-for-final-smoke"
    assert summary.failed_checks == ("signal-live-smoke-report",)
    assert summary.final_command == (
        "scripts/rev2-readiness-bundle.py --director-url http://127.0.0.1:8000 "
        "--certification-report certification/reports/rev2.json "
        "--benchmark-report certification/benchmarks/bench.json "
        "--connector-report certification/reports/signal.json "
        "--memory-report certification/reports/memory.json "
        "--approval-report certification/reports/approval.json "
        "--vulcan-report certification/reports/vulcan.json "
        "--smoke-report certification/reports/imessage-live-smoke-sent.json "
        "--signal-live-smoke --signal-yes --require-smoke-report --require-signal-smoke-report "
        "--require-vulcan-report "
        "--latency-winner-target director:health"
    )


def test_preflight_status_builds_combined_smoke_command(tmp_path: Path) -> None:
    report = tmp_path / "both-smoke-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "certification_report": "certification/reports/rev2.json",
                "benchmark_report": "certification/benchmarks/bench.json",
                "connector_reports": ["certification/reports/messaging.json"],
                "memory_report": "certification/reports/memory.json",
                "approval_report": "certification/reports/approval.json",
                "vulcan_report": "certification/reports/vulcan.json",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "imessage-live-smoke-report",
                        "passed": False,
                        "status": "missing required --smoke-report",
                    },
                    {
                        "name": "signal-live-smoke-report",
                        "passed": False,
                        "status": "missing required --signal-smoke-report",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)

    assert summary.status == "ready-for-final-smoke"
    assert summary.final_command == (
        "scripts/rev2-readiness-bundle.py --director-url http://127.0.0.1:8000 "
        "--certification-report certification/reports/rev2.json "
        "--benchmark-report certification/benchmarks/bench.json "
        "--connector-report certification/reports/messaging.json "
        "--memory-report certification/reports/memory.json "
        "--approval-report certification/reports/approval.json "
        "--vulcan-report certification/reports/vulcan.json "
        "--imessage-live-smoke --yes --signal-live-smoke --signal-yes "
        "--require-smoke-report --require-signal-smoke-report --require-vulcan-report "
        "--latency-winner-target director:health"
    )


def test_preflight_status_requires_vulcan_evidence_for_handoff(tmp_path: Path) -> None:
    report = tmp_path / "smoke-no-vulcan-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "certification_report": "certification/reports/rev2.json",
                "benchmark_report": "certification/benchmarks/bench.json",
                "connector_reports": ["certification/reports/imessage.json"],
                "memory_report": "certification/reports/memory.json",
                "approval_report": "certification/reports/approval.json",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "imessage-live-smoke-report",
                        "passed": False,
                        "status": "missing required --smoke-report",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)

    assert summary.status == "ready-for-final-smoke"
    assert summary.final_command is None
    assert summary.dry_run_command is None
    assert summary.remaining == ("Run scripts/rev2-readiness-bundle.py --imessage-live-smoke --yes after approval.",)


def test_preflight_status_reports_vulcan_missing_vision(tmp_path: Path) -> None:
    report = tmp_path / "vulcan-missing-vision-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "vulcan_report": "certification/reports/vulcan.json",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "vulcan-readiness-report",
                        "passed": False,
                        "status": "Vulcan readiness report does not support cutover",
                        "details": {"not_ready_model_profiles": ["vision"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)
    rendered = preflight.render_summary(summary)

    assert summary.status == "not-ready"
    assert summary.exit_code == 1
    assert summary.failed_checks == ("vulcan-readiness-report",)
    assert summary.remaining == (
        "Install the configured Vulcan vision profile model, rerun scripts/vulcan-operator.py readiness, and attach it with --vulcan-report.",
    )
    assert "Vulcan readiness report: certification/reports/vulcan.json" in rendered


def test_preflight_status_reports_connector_readiness_details(tmp_path: Path) -> None:
    report = tmp_path / "signal-connector-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "connector-production-report",
                        "passed": True,
                        "status": "Connector production report supports cutover",
                        "details": {
                            "not_ready": [],
                            "readiness_details": {},
                        },
                    },
                    {
                        "name": "connector-production-report",
                        "passed": False,
                        "status": "Connector production report does not support cutover",
                        "details": {
                            "not_ready": ["signal"],
                            "readiness_details": {
                                "signal": [
                                    "enabled=false",
                                    "allowed sender allowlist empty",
                                ]
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)

    assert summary.status == "not-ready"
    assert summary.remaining == (
        "Resolve connector-production-report for signal: enabled=false, allowed sender allowlist empty.",
    )


def test_preflight_status_reports_signal_readiness_missing_items(tmp_path: Path) -> None:
    report = tmp_path / "signal-readiness-rev2-readiness.json"
    report.write_text(
        json.dumps(
            {
                "passed": False,
                "director_url": "http://127.0.0.1:8000",
                "signal_readiness_report": "certification/reports/signal-readiness-latest.json",
                "latency_winner_target": "director:health",
                "checks": [
                    {
                        "name": "signal-readiness-report",
                        "passed": False,
                        "status": "Signal readiness report does not support cutover",
                        "details": {
                            "account_registered": False,
                            "allowed_recipient_count": 0,
                            "signal_enabled": False,
                            "signal_rest_ok": True,
                            "missing": [
                                "Set SIGNAL_ALLOWED_SENDERS to at least one reviewed E.164 sender.",
                                "Register or link SIGNAL_ACCOUNT_NUMBER in signal-cli-rest-api.",
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = preflight.summarize_report(report)
    rendered = preflight.render_summary(summary)

    assert summary.status == "not-ready"
    assert summary.signal_readiness_report == "certification/reports/signal-readiness-latest.json"
    assert summary.remaining == (
        "Resolve signal-readiness-report: Set SIGNAL_ALLOWED_SENDERS to at least one reviewed E.164 sender.",
        "Resolve signal-readiness-report: Register or link SIGNAL_ACCOUNT_NUMBER in signal-cli-rest-api.",
        "Signal account action: complete captcha-backed registration with "
        "`scripts/signal-operator.py --env-file deploy/compose/signal/.env register --captcha 'signalcaptcha://...' --yes` "
        "using a token from https://signalcaptchas.org/registration/generate.html, then verify with "
        "`scripts/signal-operator.py --env-file deploy/compose/signal/.env verify --code <code> --yes`; "
        "or link an existing mobile account with "
        "`scripts/signal-operator.py --env-file deploy/compose/signal/.env link-device --device-name freyja-atlas --yes`.",
        "Signal allowlist action: set reviewed E.164 senders in SIGNAL_ALLOWED_SENDERS inside deploy/compose/signal/.env.",
        "Signal enablement action: set SIGNAL_ENABLED=true in deploy/compose/signal/.env only after registration/linking and allowlist review.",
    )
    assert "Signal readiness report: certification/reports/signal-readiness-latest.json" in rendered
    assert "signalcaptcha://..." in rendered


def test_preflight_status_reports_not_ready_for_other_failures(tmp_path: Path) -> None:
    report = tmp_path / "failed-rev2-readiness.json"
    _write_report(
        report,
        passed=False,
        checks=[
            {"name": "provider-health", "passed": False, "status": "HTTP 500"},
            {
                "name": "imessage-live-smoke-report",
                "passed": False,
                "status": "missing required --smoke-report",
            },
        ],
    )

    summary = preflight.summarize_report(report)

    assert summary.status == "not-ready"
    assert summary.exit_code == 1
    assert "provider-health" in summary.failed_checks


def test_latest_readiness_report_uses_mtime(tmp_path: Path) -> None:
    older = tmp_path / "older-rev2-readiness.json"
    newer = tmp_path / "newer-rev2-readiness.json"
    _write_report(older, passed=True, checks=[])
    _write_report(newer, passed=True, checks=[])
    older.touch()
    newer.touch()

    assert preflight.latest_readiness_report(tmp_path) == newer


def test_preflight_script_and_console_entrypoint_exist() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert SCRIPT_PATH.stat().st_mode & 0o111
    assert "sys.path.insert(0, str(REPO_ROOT))" in script
    assert "from certification.rev2_preflight_status import main" in script
    assert pyproject["project"]["scripts"]["freyja-rev2-preflight-status"] == (
        "certification.rev2_preflight_status:main"
    )
