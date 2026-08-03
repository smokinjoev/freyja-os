from __future__ import annotations

import json
from pathlib import Path

import pytest

from certification import cli
from certification.grader import grade_response
from certification.models import CertificationCase, CertificationReport, CertificationSuite, ReportMetadata
from certification.reporter import report_stem, write_reports
from certification.runner import list_suite_names, load_gauntlet, load_suite, resolve_suite_path, run_suite


class FakeProvider:
    name = "ollama"
    model = "fake-model"

    def __init__(self, responses: list[tuple[str, str | None]]) -> None:
        self._responses = responses

    async def complete(self, prompt: str) -> tuple[str, str | None]:
        return self._responses.pop(0)


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
