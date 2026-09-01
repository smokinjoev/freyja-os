from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-readiness-bundle.py"


def load_bundle_module():
    spec = importlib.util.spec_from_file_location("freyja5_readiness_bundle", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_readiness_bundle_builds_expected_commands(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    args = bundle.build_parser().parse_args(
        [
            "--base-url",
            "http://atlas.test:8500",
            "--token",
            "secret-token",
            "--output-dir",
            str(tmp_path),
            "--python",
            "python",
            "--timeout",
            "2.5",
            "--run-certification",
            "--run-smoke",
            "--skip-media",
        ]
    )

    assert bundle.build_certification_command(args) == [
        "python",
        "-m",
        "certification.cli",
        "routing/freyja5_architecture",
        "--provider",
        "freyja5",
        "--output-dir",
        str(tmp_path),
    ]
    assert bundle.build_smoke_command(args) == [
        "python",
        "scripts/freyja5-smoke.py",
        "--base-url",
        "http://atlas.test:8500",
        "--timeout",
        "2.5",
        "--output",
        str(tmp_path / "freyja5-smoke.json"),
        "--token",
        "secret-token",
        "--skip-media",
    ]


def test_freyja5_readiness_bundle_reports_source_ready_but_live_blocked(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    certification = tmp_path / "cert.json"
    certification.write_text(
        """
{
  "metadata": {"suite_name": "freyja5-architecture", "overall_score": 1.0},
  "passed": true
}
""".strip(),
        encoding="utf-8",
    )
    smoke = tmp_path / "smoke.json"
    smoke.write_text(
        """
{
  "report_type": "freyja5-smoke",
  "passed": true,
  "token_configured": true,
  "checks": [{"name": "health"}, {"name": "readiness"}, {"name": "chat_text"}]
}
""".strip(),
        encoding="utf-8",
    )

    report = bundle.build_report(certification_report=certification, smoke_report=smoke)

    assert report["passed"] is False
    assert report["source_ready"] is True
    assert report["live_blocked"] is True
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["freyja5-certification-report"]["ok"] is True
    assert checks["freyja5-smoke-report"]["ok"] is True
    assert checks["freyja5-live-blockers"]["status"] == "blocked"
    assert checks["freyja5-live-blockers"]["remaining"] == [
        "msty_go_always_on_linux_validation",
        "vulcan_nexus_presets",
        "iris_apple_session",
        "hera_voice_avatar_hardware",
        "live_tool_sessions",
        "vulcan_nexus_private_preset",
    ]


def test_freyja5_readiness_bundle_fails_missing_artifacts() -> None:
    bundle = load_bundle_module()

    report = bundle.build_report(certification_report=None, smoke_report=None)

    assert report["passed"] is False
    assert report["source_ready"] is False
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["freyja5-certification-report"]["status"] == "not supplied"
    assert checks["freyja5-smoke-report"]["status"] == "not supplied"
