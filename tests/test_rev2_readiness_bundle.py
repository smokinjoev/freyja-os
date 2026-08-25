from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rev2-readiness-bundle.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("rev2_readiness_bundle", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_script_is_executable() -> None:
    assert os.access(SCRIPT_PATH, os.X_OK)


def test_bundle_builds_strict_readiness_command_with_all_artifacts(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--connector-report",
            str(tmp_path / "imessage.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--vulcan-report",
            str(tmp_path / "vulcan.json"),
            "--signal-readiness-report",
            str(tmp_path / "signal-readiness.json"),
            "--smoke-report",
            str(tmp_path / "smoke.json"),
            "--signal-smoke-report",
            str(tmp_path / "signal-smoke.json"),
            "--require-smoke-report",
            "--require-signal-smoke-report",
            "--require-vulcan-report",
            "--latency-winner-target",
            "ollama:qwen2.5:7b",
            "--required-provider-profile",
            "heavy_local",
            "--output-dir",
            str(tmp_path / "reports"),
            "--python",
            "python",
        ]
    )

    commands = module.build_commands(args)

    assert len(commands) == 1
    command = commands[0]
    assert command[:4] == ["python", "-m", "certification.cli", "rev2-readiness"]
    assert "--certification-report" in command
    assert "--benchmark-report" in command
    assert command.count("--connector-report") == 2
    assert "--memory-report" in command
    assert "--approval-report" in command
    assert "--vulcan-report" in command
    assert "--signal-readiness-report" in command
    assert "--smoke-report" in command
    assert "--signal-smoke-report" in command
    assert "--require-smoke-report" in command
    assert "--require-signal-smoke-report" in command
    assert "--require-vulcan-report" in command
    assert "--latency-winner-target" in command
    assert command[command.index("--required-provider-profile") + 1] == "heavy_local"


def test_bundle_builds_imessage_smoke_dry_run_command(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "imessage.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--imessage-live-smoke",
            "--imessage-smoke-recipient",
            "+15550000001",
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    command = module.build_smoke_command(args)

    assert command == [
        "python",
        "scripts/imessage-operator.py",
        "live-smoke",
        "--text",
        "Freyja 2.0 live smoke test.",
        "--output",
        "certification/reports/imessage-live-smoke-dry-run.json",
        "--recipient",
        "+15550000001",
        "--dry-run",
    ]


def test_bundle_yes_imessage_smoke_report_feeds_final_readiness(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "imessage.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--imessage-live-smoke",
            "--yes",
            "--require-smoke-report",
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    commands = module.build_commands(args)
    readiness = commands[-1]

    assert "--smoke-report" in readiness
    assert readiness[readiness.index("--smoke-report") + 1] == "certification/reports/imessage-live-smoke-sent.json"
    assert "--require-smoke-report" in readiness


def test_bundle_builds_signal_smoke_dry_run_command(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--signal-live-smoke",
            "--signal-smoke-recipient",
            "+15550000001",
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    command = module.build_signal_smoke_command(args)

    assert command == [
        "python",
        "scripts/signal-operator.py",
        "--env-file",
        "deploy/compose/signal/.env",
        "live-smoke",
        "--text",
        "Freyja 2.0 Signal live smoke test.",
        "--output",
        "certification/reports/signal-live-smoke-dry-run.json",
        "--recipient",
        "+15550000001",
        "--dry-run",
    ]


def test_bundle_signal_smoke_allows_custom_env_file(tmp_path: Path) -> None:
    module = _load_script()
    env_file = tmp_path / "signal.env"
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--signal-live-smoke",
            "--signal-env-file",
            str(env_file),
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    command = module.build_signal_smoke_command(args)

    assert command is not None
    assert command[command.index("--env-file") + 1] == str(env_file)


def test_bundle_yes_signal_smoke_report_feeds_final_readiness(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--signal-live-smoke",
            "--signal-yes",
            "--require-signal-smoke-report",
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    commands = module.build_commands(args)
    readiness = commands[-1]

    assert "--signal-smoke-report" in readiness
    assert readiness[readiness.index("--signal-smoke-report") + 1] == "certification/reports/signal-live-smoke-sent.json"
    assert "--require-signal-smoke-report" in readiness


def test_bundle_requires_memory_source_when_report_missing(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--latency-winner-target",
            "ollama:qwen2.5:7b",
        ]
    )

    try:
        module.build_commands(args)
    except ValueError as exc:
        assert "Provide --memory-report or --memory-db" in str(exc)
    else:
        raise AssertionError("expected missing memory source to fail")


def test_bundle_requires_benchmark_source_when_report_missing(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--latency-winner-target",
            "director:health",
        ]
    )

    try:
        module.build_commands(args)
    except ValueError as exc:
        assert "Provide --benchmark-report or --benchmark-probe" in str(exc)
    else:
        raise AssertionError("expected missing benchmark source to fail")


def test_bundle_can_stage_latency_probe_when_benchmark_report_missing(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-probe",
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    commands = module.build_commands(args)

    assert len(commands) == 2
    assert commands[0][:4] == ["python", "-m", "certification.cli", "rev2-latency-probe"]
    assert commands[1][:4] == ["python", "-m", "certification.cli", "rev2-readiness"]


def test_bundle_can_stage_memory_audit_command_from_database(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-db",
            str(tmp_path / "freyja.db"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--latency-winner-target",
            "ollama:qwen2.5:7b",
            "--output-dir",
            str(tmp_path / "reports"),
            "--python",
            "python",
        ]
    )

    commands = module.build_commands(args)

    assert len(commands) == 2
    assert commands[0][:4] == ["python", "-m", "certification.cli", "rev2-memory-audit"]
    assert commands[1][:4] == ["python", "-m", "certification.cli", "rev2-readiness"]


def test_extracts_json_report_path_from_command_output() -> None:
    module = _load_script()

    path = module._extract_json_report(
        "Memory database: data/freyja.db\n"
        "Markdown report: certification/reports/example.md\n"
        "JSON report: certification/reports/example.json\n"
    )

    assert path == "certification/reports/example.json"


def test_print_command_shell_quotes_spaced_arguments(capsys) -> None:
    module = _load_script()

    module._print_command(
        [
            "python",
            "scripts/rev2-readiness-bundle.py",
            "--approval-report",
            "certification/reports/approval report.json",
        ]
    )

    output = capsys.readouterr().out.strip()
    assert output == (
        "python scripts/rev2-readiness-bundle.py --approval-report "
        "'certification/reports/approval report.json'"
    )


def test_bundle_continues_to_readiness_when_latency_probe_reports_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_script()
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "rev2-latency-probe" in command:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=(
                    "Failed targets: {'macagent:health': 1}\n"
                    "Benchmark JSON report: certification/benchmarks/live.json\n"
                ),
                stderr="",
            )
        if "rev2-readiness" in command:
            assert "certification/benchmarks/live.json" in command
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="JSON report: certification/reports/memory.json\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.main(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-probe",
            "--connector-report",
            str(tmp_path / "signal.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    assert result == 1
    assert any("rev2-latency-probe" in command for command in calls)
    assert any("rev2-readiness" in command for command in calls)


def test_bundle_imessage_smoke_dry_run_stops_before_readiness(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.main(
        [
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "bench.json"),
            "--connector-report",
            str(tmp_path / "imessage.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approval.json"),
            "--imessage-live-smoke",
            "--imessage-smoke-output",
            str(tmp_path / "smoke.json"),
            "--require-smoke-report",
            "--latency-winner-target",
            "director:health",
            "--python",
            "python",
        ]
    )

    assert result == 2
    assert len(calls) == 1
    assert calls[0][-1] == "--dry-run"
    assert "rev2-readiness" not in calls[0]
