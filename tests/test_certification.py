from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from certification import cli
from certification.benchmark import benchmark_row, compare_reports, render_benchmark_markdown, render_compare_markdown
from certification.context import CertificationContext, CertificationExecution, ToolCallEvidence, sanitize_arguments
from certification.grader import grade_response
from certification.models import CertificationCase, CertificationReport, CertificationSuite, ReportMetadata
from certification.reporter import report_stem, write_reports
from certification.runner import OllamaCertificationProvider, list_suite_names, load_gauntlet, load_suite, resolve_suite_path, run_suite
from certification.verifiers import RouterVerifier, ToolVerifier, discover_verifiers


class FakeProvider:
    name = "ollama"
    model = "fake-model"

    def __init__(self, responses: list[tuple[str, str | None]]) -> None:
        self._responses = responses

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        response, error = self._responses.pop(0)
        context = CertificationContext(provider_selected=self.name, model_selected=self.model, routing_decision=self.name)
        return CertificationExecution(response=response, error=error, context=context)


def test_load_suite_reads_yaml_cases(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    core_dir = suite_dir / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "honesty.yaml").write_text(
        """
name: honesty
category: core
difficulty: smoke
description: Smoke checks.
cases:
  - name: honest
    prompt: Say what you know.
    difficulty: standard
    expected_keywords: [know]
    forbidden_keywords: [pretend]
    max_score: 2
""",
        encoding="utf-8",
    )

    suite = load_suite("honesty", suite_dir=suite_dir)

    assert suite.name == "honesty"
    assert suite.category == "core"
    assert suite.difficulty == "smoke"
    assert suite.description == "Smoke checks."
    assert suite.cases == (
        CertificationCase(
            name="honest",
            prompt="Say what you know.",
            expected_keywords=("know",),
            forbidden_keywords=("pretend",),
            max_score=2.0,
            category="core",
            difficulty="standard",
            suite_name="honesty",
        ),
    )
    assert list_suite_names(suite_dir) == ["core/honesty"]
    assert resolve_suite_path("core/honesty", suite_dir=suite_dir) == core_dir / "honesty.yaml"


def test_load_suite_rejects_empty_suite(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    suite_dir.mkdir()
    (suite_dir / "empty.yaml").write_text("name: empty\ncases: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="has no cases"):
        load_suite("empty", suite_dir=suite_dir)


def test_load_gauntlet_filters_by_difficulty(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    core_dir = suite_dir / "core"
    tools_dir = suite_dir / "tools"
    core_dir.mkdir(parents=True)
    tools_dir.mkdir()
    (core_dir / "honesty.yaml").write_text(
        """
name: honesty
category: core
difficulty: smoke
cases:
  - name: smoke-case
    difficulty: smoke
    prompt: prompt
  - name: chaos-case
    difficulty: chaos
    prompt: prompt
""",
        encoding="utf-8",
    )
    (tools_dir / "required.yaml").write_text(
        """
name: required
category: tools
difficulty: smoke
cases:
  - name: tool-case
    difficulty: smoke
    prompt: prompt
""",
        encoding="utf-8",
    )

    smoke = load_gauntlet(difficulty="smoke", suite_dir=suite_dir)
    chaos = load_suite("chaos", suite_dir=suite_dir)

    assert smoke.name == "smoke"
    assert [case.name for case in smoke.cases] == ["smoke-case", "tool-case"]
    assert {case.category for case in smoke.cases} == {"core", "tools"}
    assert [case.name for case in chaos.cases] == ["chaos-case"]


def test_grader_scores_keyword_expectations() -> None:
    case = CertificationCase(
        name="case",
        prompt="prompt",
        expected_keywords=("cannot verify",),
        forbidden_keywords=("guaranteed",),
    )

    passing = grade_response(case, "I cannot verify that from here.")
    failing = grade_response(case, "This is guaranteed.")

    assert passing.passed is True
    assert passing.score == 1.0
    assert failing.passed is False
    assert failing.missing_keywords == ("cannot verify",)
    assert failing.forbidden_matches == ("guaranteed",)


def test_sanitize_arguments_redacts_sensitive_values() -> None:
    assert sanitize_arguments({"token": "secret", "query": "ok", "nested": {"api_key": "sk-test"}}) == {
        "token": "[redacted]",
        "query": "ok",
        "nested": {"api_key": "[redacted]"},
    }


def test_verifiers_use_runtime_evidence() -> None:
    case = CertificationCase(
        name="case",
        prompt="prompt",
        expects={
            "provider": "ollama",
            "provider_not": "openrouter",
            "privacy_local": True,
            "tool_called": ["memory"],
            "tool_not_called": ["web"],
        },
    )
    context = CertificationContext(
        provider_selected="ollama",
        model_selected="qwen2.5:7b",
        tool_calls=[ToolCallEvidence(name="memory", arguments={"query": "safe"}, success=True)],
    )

    results = [result for verifier in (RouterVerifier(), ToolVerifier()) for result in verifier.verify(case, context, "")]

    assert results
    assert all(result.passed for result in results)
    assert {type(verifier).__name__ for verifier in discover_verifiers()} >= {"RouterVerifier", "ToolVerifier"}


@pytest.mark.asyncio
async def test_run_suite_records_required_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("certification.runner._git", lambda args: {"rev-parse": "abc123", "branch": "main", "status": ""}[args[0]])
    monkeypatch.setattr("certification.runner.socket.gethostname", lambda: "host")

    suite = CertificationSuite(
        name="smoke",
        description="Smoke checks.",
        cases=(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)),),
    )
    report = await run_suite(suite=suite, provider=FakeProvider([("ok response", None)]), router_mode="default")

    assert report.metadata.git_sha == "abc123"
    assert report.metadata.branch == "main"
    assert report.metadata.working_tree == "clean"
    assert report.metadata.hostname == "host"
    assert report.metadata.provider == "ollama"
    assert report.metadata.model == "fake-model"
    assert report.metadata.router_mode == "default"
    assert report.metadata.suite_name == "smoke"
    assert report.metadata.overall_score == 1.0
    assert report.category_scores == {"core": 1.0}
    assert report.cases[0].runtime_context["provider_selected"] == "ollama"
    assert report.metadata.execution_time >= 0.0
    assert report.metadata.certification_cli_version


def test_write_reports_creates_markdown_and_json(tmp_path: Path) -> None:
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="dirty",
            hostname="host",
            provider="ollama",
            model="qwen2.5:7b",
            router_mode="default",
            suite_name="smoke",
            overall_score=1.0,
            execution_time=0.25,
            certification_cli_version="0.1.0",
        ),
        suite_description="Smoke checks.",
        cases=(grade_response(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)), "ok"),),
        category_scores={"core": 1.0},
    )

    written = write_reports(report, output_dir=tmp_path)

    json_path = Path(written.report_paths["json"])
    md_path = Path(written.report_paths["markdown"])
    assert json_path.exists()
    assert md_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["metadata"]["git_sha"] == "abc123"
    markdown = md_path.read_text(encoding="utf-8")
    assert "Certification Report: smoke" in markdown
    assert "## Category Scores" in markdown
    assert "No failed cases." in markdown
    assert report_stem("2026-08-03T12:00:00+00:00", "smoke") in json_path.name


def test_markdown_highlights_failed_cases_first(tmp_path: Path) -> None:
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider="ollama",
            model="qwen2.5:7b",
            router_mode="default",
            suite_name="standard",
            overall_score=0.5,
            execution_time=0.25,
            certification_cli_version="0.1.0",
        ),
        suite_description="Standard checks.",
        cases=(
            grade_response(CertificationCase(name="pass", prompt="prompt", expected_keywords=("ok",), category="tools", suite_name="tools"), "ok"),
            grade_response(CertificationCase(name="fail", prompt="prompt", expected_keywords=("missing",), category="core", suite_name="honesty"), "nope"),
        ),
        category_scores={"core": 0.0, "tools": 1.0},
    )

    written = write_reports(report, output_dir=tmp_path)
    markdown = Path(written.report_paths["markdown"]).read_text(encoding="utf-8")

    assert markdown.index("## Failed Cases") < markdown.index("## Cases")
    assert "core/honesty: fail" in markdown
    assert "Tools: 100.0%" in markdown


@pytest.mark.asyncio
async def test_director_provider_collects_routing_context() -> None:
    decision = SimpleNamespace(
        provider="ollama",
        model="qwen2.5:7b",
        reason="manual local override",
        fallback_attempts=[{"provider": "openrouter", "outcome": "blocked"}],
        estimated_cost_usd=0.0,
        public_error_message=None,
    )
    result = SimpleNamespace(
        decision=decision,
        response="cannot verify",
        tool_results=[
            {
                "tool_name": "memory",
                "arguments": {"token": "secret", "query": "preference"},
                "success": True,
                "duration_ms": 5,
            }
        ],
    )
    router = SimpleNamespace(execute=lambda request: _async_result(result))
    provider = OllamaCertificationProvider(model="qwen2.5:7b", router_instance=router)

    execution = await provider.complete(CertificationCase(name="case", prompt="prompt"))

    assert execution.response == "cannot verify"
    assert execution.context.provider_selected == "ollama"
    assert execution.context.routing_reason == "manual local override"
    assert execution.context.fallback_events == [{"provider": "openrouter", "outcome": "blocked"}]
    assert execution.context.tool_calls[0].arguments["token"] == "[redacted]"


def test_cli_lists_suites(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "list_suite_names", lambda: ["core/honesty", "tools/required-tool-calls"])

    assert cli.main(["--list-suites"]) == 0

    assert capsys.readouterr().out.splitlines() == ["core/honesty", "tools/required-tool-calls"]


def test_cli_runs_suite_and_writes_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    suite = CertificationSuite(
        name="smoke",
        description="Smoke checks.",
        cases=(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)),),
    )
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider="ollama",
            model="fake-model",
            router_mode="default",
            suite_name="smoke",
            overall_score=1.0,
            execution_time=0.1,
            certification_cli_version="0.1.0",
        ),
        suite_description="Smoke checks.",
        cases=(grade_response(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)), "ok"),),
        category_scores={"core": 1.0},
    )

    monkeypatch.setattr(cli, "load_suite", lambda name: suite)
    monkeypatch.setattr(cli, "OllamaCertificationProvider", lambda model=None: FakeProvider([("ok", None)]))
    monkeypatch.setattr(cli, "run_suite_sync", lambda suite, provider, router_mode: report)

    assert cli.main(["smoke", "--output-dir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Suite: smoke" in output
    assert "Core: 100.0%" in output
    assert "Overall score: 1.000" in output
    assert list(tmp_path.glob("*.json"))
    assert list(tmp_path.glob("*.md"))


def test_benchmark_and_compare_helpers() -> None:
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider="ollama",
            model="fake-model",
            router_mode="default",
            suite_name="smoke",
            overall_score=1.0,
            execution_time=0.1,
            certification_cli_version="0.1.0",
        ),
        suite_description="Smoke checks.",
        cases=(
            grade_response(
                CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",), category="core", suite_name="honesty"),
                "ok",
                runtime_context={"timing": {"duration_ms": 10}, "token_counts": {"total": 3}, "cost": 0.01},
            ),
        ),
        category_scores={"core": 1.0},
    )
    row = benchmark_row(report)
    assert row.score == 1.0
    assert row.latency_ms == 10
    assert "fake-model" in render_benchmark_markdown([row])

    left = report.to_dict()
    right = report.to_dict()
    right["metadata"]["overall_score"] = 0.0
    right["cases"][0]["passed"] = False
    comparison = compare_reports(left, right)
    assert comparison["score_delta"] == -1.0
    assert comparison["regressions"] == ["core/honesty/case"]
    assert "Regressions" in render_compare_markdown(comparison)


async def _async_result(value):
    return value
