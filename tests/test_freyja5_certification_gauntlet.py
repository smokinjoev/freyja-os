from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-certification-gauntlet.py"


def load_gauntlet_module():
    spec = importlib.util.spec_from_file_location("freyja5_certification_gauntlet", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**overrides):
    values = {
        "base_url": "http://atlas.test:8500",
        "token": "secret-token",
        "timeout": 1.5,
        "output_dir": Path("certification/reports"),
        "agent_export": None,
        "smoke_report": None,
        "bundle_output": None,
        "summary_output": None,
        "python": ".venv/bin/python",
        "skip_smoke": False,
        "skip_media": False,
        "print_only": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_freyja5_gauntlet_builds_operator_command_plan() -> None:
    gauntlet = load_gauntlet_module()
    args = _args()
    paths = gauntlet.resolved_paths(args)

    assert paths == {
        "agent_export": Path("certification/reports/freyja5-agent-definitions.json"),
        "smoke_report": Path("certification/reports/freyja5-smoke.json"),
        "bundle_output": Path("certification/reports/freyja5-readiness-bundle.json"),
        "summary_output": Path("certification/reports/freyja5-gauntlet-summary.json"),
    }
    assert gauntlet.build_export_command(args, paths) == [
        ".venv/bin/python",
        "scripts/freyja5-export-agent-definitions.py",
        "--output",
        "certification/reports/freyja5-agent-definitions.json",
    ]
    assert gauntlet.build_certification_command(args) == [
        ".venv/bin/python",
        "-m",
        "certification.cli",
        "routing/freyja5_architecture",
        "--provider",
        "freyja5",
        "--output-dir",
        "certification/reports",
    ]
    assert gauntlet.build_smoke_command(args, paths) == [
        ".venv/bin/python",
        "scripts/freyja5-smoke.py",
        "--base-url",
        "http://atlas.test:8500",
        "--timeout",
        "1.5",
        "--output",
        "certification/reports/freyja5-smoke.json",
        "--token",
        "secret-token",
    ]


def test_freyja5_gauntlet_summary_preserves_source_ready_live_blocked() -> None:
    gauntlet = load_gauntlet_module()
    paths = gauntlet.resolved_paths(_args())
    preflight = {"status": "source-ready-live-blocked", "source_ready": True, "live_blocked": True}

    summary = gauntlet._summary(paths=paths, steps=[], preflight=preflight)

    assert summary["passed"] is False
    assert summary["source_ready"] is True
    assert summary["live_blocked"] is True
    assert summary["preflight_status"] == "source-ready-live-blocked"


def test_freyja5_gauntlet_skip_smoke_requires_existing_report(tmp_path: Path) -> None:
    gauntlet = load_gauntlet_module()
    args = _args(skip_smoke=True, smoke_report=tmp_path / "missing-smoke.json")
    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(name, command, *, expected_codes):
        calls.append((name, command))
        if name == "certification":
            return {"name": name, "command": command, "exit_code": 0, "ok": True, "stdout": "JSON report: cert.json\n", "stderr": ""}
        return {"name": name, "command": command, "exit_code": 0, "ok": True, "stdout": "", "stderr": ""}

    gauntlet._run_step = fake_run_step

    report = gauntlet.run_gauntlet(args)

    assert [name for name, _command in calls] == ["agent_export", "certification"]
    assert report["steps"][-1]["name"] == "smoke"
    assert report["steps"][-1]["status"] == "missing_existing_report"
    assert report["source_ready"] is False


def test_freyja5_gauntlet_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111
