from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja-live-evidence-bundle.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("freyja_live_evidence_bundle", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_script_is_executable() -> None:
    assert os.access(SCRIPT_PATH, os.X_OK)


def test_bundle_defaults_to_repo_venv_python_when_present() -> None:
    module = _load_script()
    args = module.build_parser().parse_args([])

    assert args.python == str(REPO_ROOT / ".venv" / "bin" / "python")


def test_bundle_reexecs_under_repo_venv_for_direct_execution() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "os.execv" in source
    assert ".venv" in source


def test_bundle_builds_messaging_and_inference_commands(tmp_path: Path) -> None:
    module = _load_script()
    args = module.build_parser().parse_args(
        [
            "--python",
            "python",
            "--output-dir",
            str(tmp_path / "reports"),
            "--vulcan-url",
            "http://vulcan:11434",
            "--vulcan-model",
            "gpt-oss-freyja:20b-analysis-prefill",
            "--route-smoke-person-id",
            "beth",
            "--route-smoke-agent-id",
            "benedict",
        ]
    )

    messaging = module.build_messaging_command(args)
    inference = module.build_inference_command(args)
    coding = module.build_coding_command(args)
    env = module.inference_env(args)

    assert module.build_sync_command(args) == []
    assert messaging[:3] == ["python", "scripts/messaging-production-check.py", "--connector"]
    assert "--check-imessage-route-smoke" in messaging
    assert "--check-inprocess-route-smoke" in messaging
    assert messaging[messaging.index("--route-smoke-person-id") + 1] == "beth"
    assert messaging[messaging.index("--route-smoke-agent-id") + 1] == "benedict"
    assert messaging[messaging.index("--output") + 1].endswith("freyja-live-imessage-route-evidence.json")
    assert inference == [
        "python",
        "-m",
        "certification.cli",
        "inference/freyja_qa_100",
        "--provider",
        "local_reasoning",
        "--model",
        "gpt-oss-freyja:20b-analysis-prefill",
        "--output-dir",
        str(tmp_path / "reports"),
    ]
    assert coding == [
        "python",
        "-m",
        "certification.cli",
        "inference/freyja_iterative_coding",
        "--provider",
        "local_reasoning",
        "--model",
        "gpt-oss-freyja:20b-analysis-prefill",
        "--output-dir",
        str(tmp_path / "reports"),
    ]
    assert env["OLLAMA_REASONING_BASE_URL"] == "http://vulcan:11434"
    assert env["OLLAMA_REASONING_MODEL"] == "gpt-oss-freyja:20b-analysis-prefill"


def test_bundle_can_force_inference_after_failed_preflight() -> None:
    module = _load_script()
    args = module.build_parser().parse_args(["--run-inference-with-failed-preflight"])

    assert args.run_inference_with_failed_preflight is True


def test_bundle_builds_optional_imessage_runtime_sync_command() -> None:
    module = _load_script()
    args = module.build_parser().parse_args(["--sync-imessage-runtime"])

    assert module.build_sync_command(args) == ["scripts/sync-imessage-runtime.sh"]


@pytest.mark.asyncio
async def test_bundle_vulcan_preflight_checks_model_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script()
    captured = {}

    class FakeOllamaClient:
        def __init__(self, base_url: str, model: str) -> None:
            captured["base_url"] = base_url
            captured["model"] = model

        async def tags(self) -> dict:
            return {"models": [{"name": "gpt-oss-freyja:20b-analysis-prefill"}]}

    monkeypatch.setattr("freyja.ollama_client.OllamaClient", FakeOllamaClient)
    args = module.build_parser().parse_args(
        [
            "--vulcan-url",
            "http://vulcan:11434",
            "--vulcan-model",
            "gpt-oss-freyja:20b-analysis-prefill",
        ]
    )

    status = await module.vulcan_preflight(args)

    assert captured == {
        "base_url": "http://vulcan:11434",
        "model": "gpt-oss-freyja:20b-analysis-prefill",
    }
    assert status["ok"] is True
    assert status["host_reachable"] is True
    assert status["model_available"] is True
    assert status["model_count"] == 1


@pytest.mark.asyncio
async def test_bundle_vulcan_preflight_reports_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script()

    class FakeOllamaClient:
        def __init__(self, base_url: str, model: str) -> None:
            pass

        async def tags(self) -> dict:
            return {"models": [{"name": "other-model:latest"}]}

    monkeypatch.setattr("freyja.ollama_client.OllamaClient", FakeOllamaClient)
    args = module.build_parser().parse_args(["--vulcan-model", "target-model"])

    status = await module.vulcan_preflight(args)

    assert status["ok"] is False
    assert status["host_reachable"] is True
    assert status["model_available"] is False
    assert status["error"] == "model_not_listed"


def test_bundle_writes_summary_from_reports(tmp_path: Path) -> None:
    module = _load_script()
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    connector_report = output_dir / "connector.json"
    inference_report = output_dir / "inference.json"
    coding_report = output_dir / "coding.json"
    connector_report.write_text(
        """
        {
          "imessage": {
            "ready_for_live_smoke": true,
            "runtime_source_drift": {"ok": true, "drift_count": 0},
            "runtime_import_check": {"ok": true},
            "director_health": {"ok": true},
            "synthetic_route_smoke": {"ok": true, "terminal_equivalent": true},
            "inprocess_route_smoke": {"ok": true, "prompt_context_equivalent": true}
          }
        }
        """,
        encoding="utf-8",
    )
    inference_report.write_text(
        """
        {
          "passed": true,
          "overall_score": 0.97,
          "passing_score": 0.95,
          "cases": [
            {"name": "case-1", "passed": true}
          ],
          "speed_metrics": {
            "mean_generation_tokens_per_second": 42.5,
            "measured_cases": 100
          }
        }
        """,
        encoding="utf-8",
    )
    coding_report.write_text(
        """
        {
          "passed": true,
          "overall_score": 1.0,
          "passing_score": 0.90,
          "cases": [
            {"name": "coding-1", "passed": true}
          ],
          "speed_metrics": {
            "mean_generation_tokens_per_second": 31.2,
            "measured_cases": 10
          }
        }
        """,
        encoding="utf-8",
    )
    args = module.build_parser().parse_args(
        [
            "--python",
            "python",
            "--sync-imessage-runtime",
            "--output-dir",
            str(output_dir),
            "--connector-report",
            str(connector_report),
        ]
    )

    summary_path = module.write_summary(
        args,
        sync_command=["scripts/sync-imessage-runtime.sh"],
        sync_returncode=0,
        messaging_command=["msg"],
        messaging_returncode=0,
        inference_command=["qa"],
        inference_returncode=0,
        inference_report=inference_report,
        coding_command=["coding"],
        coding_returncode=0,
        coding_report=coding_report,
        vulcan_preflight={"ok": True, "host_reachable": True, "model_available": True},
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert '"ok": true' in summary
    assert '"completion_gates"' in summary
    assert '"all_gates_passed": true' in summary
    assert '"imessage_terminal_equivalent": true' in summary
    assert '"vulcan_inference_accuracy": true' in summary
    assert '"vulcan_preflight": true' in summary
    assert '"vulcan_speed_measured": true' in summary
    assert '"vulcan_iterative_coding": true' in summary
    assert '"action_items": []' in summary
    assert '"skipped": false' in summary
    assert '"runtime_sync"' in summary
    assert '"requested": true' in summary
    assert '"returncode": 0' in summary
    assert '"runtime_source_drift_ok": true' in summary
    assert '"runtime_source_drift_count": 0' in summary
    assert '"runtime_import_ok": true' in summary
    assert '"live_route_smoke_ok": true' in summary
    assert '"inprocess_route_smoke_ok": true' in summary
    assert '"overall_score": 0.97' in summary
    assert '"mean_generation_tokens_per_second": 42.5' in summary
    assert '"total_cases": 1' in summary
    assert '"failed_cases": 0' in summary
    assert '"coding"' in summary


def test_bundle_summary_fails_when_runtime_sync_fails(tmp_path: Path) -> None:
    module = _load_script()
    output_dir = tmp_path / "reports"
    args = module.build_parser().parse_args(
        [
            "--python",
            "python",
            "--sync-imessage-runtime",
            "--output-dir",
            str(output_dir),
        ]
    )

    summary_path = module.write_summary(
        args,
        sync_command=["scripts/sync-imessage-runtime.sh"],
        sync_returncode=1,
        messaging_command=["msg"],
        messaging_returncode=0,
        inference_command=["qa"],
        inference_returncode=0,
        inference_report=None,
        coding_command=["coding"],
        coding_returncode=1,
        coding_report=None,
        vulcan_preflight={"ok": False, "host_reachable": False, "model_available": False},
        inference_skipped=True,
        inference_skip_reason="runtime_sync_failed",
        coding_skipped=True,
        coding_skip_reason="runtime_sync_failed",
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert '"ok": false' in summary
    assert '"runtime_sync"' in summary
    assert '"returncode": 1' in summary
    assert '"skip_reason": "runtime_sync_failed"' in summary
    assert '"coding"' in summary
    assert "Fix scripts/sync-imessage-runtime.sh failure" in summary


def test_bundle_summary_reports_action_items_for_runtime_and_vulcan_failures(tmp_path: Path) -> None:
    module = _load_script()
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    connector_report = output_dir / "connector.json"
    inference_report = output_dir / "inference.json"
    coding_report = output_dir / "coding.json"
    connector_report.write_text(
        """
        {
          "imessage": {
            "ready_for_live_smoke": false,
            "runtime_source_drift": {"ok": false, "drift_count": 2},
            "runtime_import_check": {"ok": false, "stderr": "ModuleNotFoundError: No module named freyja.inference"},
            "director_health": {"ok": false},
            "synthetic_route_smoke": {"ok": false, "terminal_equivalent": false},
            "inprocess_route_smoke": {"ok": true, "terminal_equivalent": true, "prompt_context_equivalent": true}
          }
        }
        """,
        encoding="utf-8",
    )
    inference_report.write_text(
        """
        {
          "passed": false,
          "overall_score": 0.0,
          "passing_score": 0.95,
          "cases": [
            {"name": "arithmetic-001", "passed": false, "error": "All connection attempts failed"},
            {"name": "logic-001", "passed": false, "error": "All connection attempts failed"}
          ],
          "speed_metrics": {
            "mean_generation_tokens_per_second": null,
            "measured_cases": 0
          }
        }
        """,
        encoding="utf-8",
    )
    coding_report.write_text(
        """
        {
          "passed": false,
          "overall_score": 0.8,
          "passing_score": 0.90,
          "cases": [
            {"name": "python-fix-off-by-one", "passed": false, "error": "verification_failed"}
          ],
          "speed_metrics": {
            "mean_generation_tokens_per_second": 20.0,
            "measured_cases": 1
          }
        }
        """,
        encoding="utf-8",
    )
    args = module.build_parser().parse_args(
        [
            "--python",
            "python",
            "--output-dir",
            str(output_dir),
            "--connector-report",
            str(connector_report),
        ]
    )

    summary_path = module.write_summary(
        args,
        sync_command=[],
        sync_returncode=None,
        messaging_command=["msg"],
        messaging_returncode=1,
        inference_command=["qa"],
        inference_returncode=1,
        inference_report=inference_report,
        coding_command=["coding"],
        coding_returncode=1,
        coding_report=coding_report,
        vulcan_preflight={"ok": False, "host_reachable": False, "model_available": False, "error": "connection refused"},
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert '"ok": false' in summary
    assert '"imessage_runtime_synced": false' in summary
    assert '"imessage_terminal_equivalent": true' in summary
    assert '"live_imessage_route_smoke": false' in summary
    assert '"vulcan_inference_accuracy": false' in summary
    assert '"vulcan_preflight": false' in summary
    assert '"vulcan_speed_measured": false' in summary
    assert '"vulcan_iterative_coding": false' in summary
    assert '"runtime_import_ok": false' in summary
    assert "ModuleNotFoundError" in summary
    assert "Fix iMessage runtime import failure before restarting live messaging" in summary
    assert "No module named freyja.inference" in summary
    assert '"skipped": false' in summary
    assert "Run scripts/freyja-live-evidence-bundle.py --sync-imessage-runtime" in summary
    assert '"all_failures_are_connection_errors": true' in summary
    assert '"first_error": "All connection attempts failed"' in summary
    assert '"category": "arithmetic"' in summary
    assert '"category": "logic"' in summary
    assert "Fix connectivity to Vulcan before running the 100-question inference and iterative coding gates" in summary


def test_bundle_inference_failure_summary_distinguishes_quality_failures(tmp_path: Path) -> None:
    module = _load_script()
    inference_report = tmp_path / "inference.json"
    inference_report.write_text(
        """
        {
          "passed": false,
          "overall_score": 0.94,
          "passing_score": 0.95,
          "cases": [
            {
              "name": "instruction-001",
              "passed": false,
              "error": "verification_failed",
              "missing_keywords": ["ALPHA-17"],
              "forbidden_matches": ["cannot"]
            },
            {"name": "case-2", "passed": true}
          ],
          "speed_metrics": {
            "mean_generation_tokens_per_second": 38.2,
            "measured_cases": 2
          }
        }
        """,
        encoding="utf-8",
    )

    summary = module._summarize_inference(inference_report)

    assert summary["total_cases"] == 2
    assert summary["failed_cases"] == 1
    assert summary["failure_summary"]["all_failures_are_connection_errors"] is False
    assert summary["failure_summary"]["first_error"] == "verification_failed"
    assert summary["failure_summary"]["top_categories"] == [{"category": "instruction", "count": 1}]
    assert summary["failure_summary"]["top_missing_keywords"] == [{"keyword": "ALPHA-17", "count": 1}]
    assert summary["failure_summary"]["top_forbidden_matches"] == [{"keyword": "cannot", "count": 1}]


def test_bundle_main_skips_inference_when_vulcan_preflight_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_script()
    calls: list[list[str]] = []

    async def fake_preflight(args):
        return {
            "ok": False,
            "host_reachable": False,
            "model_available": False,
            "error": "connection refused",
        }

    class Completed:
        returncode = 1
        stdout = "{}\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(module, "vulcan_preflight", fake_preflight)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    summary = tmp_path / "summary.json"

    result = module.main(["--output-dir", str(tmp_path), "--summary-report", str(summary)])

    assert result == 1
    assert len(calls) == 1
    assert any(part.endswith("messaging-production-check.py") for part in calls[0])
    body = summary.read_text(encoding="utf-8")
    assert '"skipped": true' in body
    assert '"skip_reason": "vulcan_preflight_failed"' in body
    assert '"coding"' in body


def test_bundle_main_force_runs_inference_after_failed_preflight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_script()
    calls: list[list[str]] = []

    async def fake_preflight(args):
        return {
            "ok": False,
            "host_reachable": False,
            "model_available": False,
            "error": "connection refused",
        }

    class Completed:
        returncode = 1
        stdout = "{}\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(module, "vulcan_preflight", fake_preflight)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    summary = tmp_path / "summary.json"

    result = module.main(
        [
            "--output-dir",
            str(tmp_path),
            "--summary-report",
            str(summary),
            "--run-inference-with-failed-preflight",
        ]
    )

    assert result == 1
    assert len(calls) == 3
    assert any(part.endswith("messaging-production-check.py") for part in calls[0])
    assert "certification.cli" in calls[1]
    assert "inference/freyja_iterative_coding" in calls[2]
    body = summary.read_text(encoding="utf-8")
    assert '"skipped": false' in body
