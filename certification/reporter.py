from __future__ import annotations

import json
from pathlib import Path

from certification.models import CaseResult, CertificationReport

DEFAULT_REPORT_DIR = Path("certification/reports")


def report_stem(timestamp: str, suite_name: str) -> str:
    safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("+", "Z")
    safe_suite = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in suite_name)
    return f"{safe_timestamp}-{safe_suite}"


def write_reports(report: CertificationReport, output_dir: Path = DEFAULT_REPORT_DIR) -> CertificationReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = report_stem(report.metadata.timestamp, report.metadata.suite_name)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    return CertificationReport(
        metadata=report.metadata,
        suite_description=report.suite_description,
        cases=report.cases,
        category_scores=report.category_scores,
        report_paths={"json": str(json_path), "markdown": str(md_path)},
        schema_version=report.schema_version,
    )


def render_markdown(report: CertificationReport) -> str:
    metadata = report.metadata
    lines = [
        f"# Certification Report: {metadata.suite_name}",
        "",
        "## Summary",
        "",
        f"- Timestamp: {metadata.timestamp}",
        f"- Git SHA: {metadata.git_sha}",
        f"- Branch: {metadata.branch}",
        f"- Working tree: {metadata.working_tree}",
        f"- Hostname: {metadata.hostname}",
        f"- Provider: {metadata.provider}",
        f"- Model: {metadata.model}",
        f"- Router mode: {metadata.router_mode}",
        f"- Suite: {metadata.suite_name}",
        f"- Overall score: {metadata.overall_score:.3f}",
        f"- Execution time: {metadata.execution_time:.3f}s",
        f"- Certification CLI version: {metadata.certification_cli_version}",
        "",
        "## Category Scores",
        "",
    ]
    for category, score in sorted(report.category_scores.items()):
        lines.append(f"- {category.title()}: {score * 100:.1f}%")
    lines.extend(
        [
            "",
            f"- Overall: {metadata.overall_score * 100:.1f}%",
            "",
            "## Failed Cases",
            "",
        ]
    )
    failed_cases = [case for case in report.cases if not case.passed]
    if failed_cases:
        for case in failed_cases:
            lines.extend(_case_lines(case))
    else:
        lines.append("No failed cases.")
        lines.append("")
    lines.extend(["## Cases", ""])
    for case in report.cases:
        lines.extend(_case_lines(case))
    return "\n".join(lines)


def _case_lines(case: CaseResult) -> list[str]:
    lines = [
        f"### {case.category}/{case.suite_name}: {case.name}",
        "",
        f"- Difficulty: {case.difficulty}",
        f"- Passed: {case.passed}",
        f"- Score: {case.score:.3f} / {case.max_score:.3f}",
    ]
    if case.missing_keywords:
        lines.append(f"- Missing keywords: {', '.join(case.missing_keywords)}")
    if case.forbidden_matches:
        lines.append(f"- Forbidden matches: {', '.join(case.forbidden_matches)}")
    if case.error:
        lines.append(f"- Error: {case.error}")
    lines.extend(["", "Prompt:", "", "```", case.prompt, "```", "", "Response:", "", "```", case.response, "```", ""])
    return lines
