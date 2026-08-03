from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CertificationCase:
    name: str
    prompt: str
    expected_keywords: tuple[str, ...] = ()
    forbidden_keywords: tuple[str, ...] = ()
    max_score: float = 1.0
    category: str = "core"
    difficulty: str = "standard"
    suite_name: str = ""


@dataclass(frozen=True)
class CertificationSuite:
    name: str
    description: str
    cases: tuple[CertificationCase, ...]
    category: str = "core"
    difficulty: str = "standard"
    path: str | None = None


@dataclass(frozen=True)
class CaseResult:
    name: str
    prompt: str
    response: str
    score: float
    max_score: float
    passed: bool
    category: str = "core"
    difficulty: str = "standard"
    suite_name: str = ""
    missing_keywords: tuple[str, ...] = ()
    forbidden_matches: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class ReportMetadata:
    timestamp: str
    git_sha: str
    branch: str
    working_tree: str
    hostname: str
    provider: str
    model: str
    router_mode: str
    suite_name: str
    overall_score: float
    execution_time: float
    certification_cli_version: str


@dataclass(frozen=True)
class CertificationReport:
    metadata: ReportMetadata
    suite_description: str
    cases: tuple[CaseResult, ...]
    category_scores: dict[str, float] = field(default_factory=dict)
    report_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.__dict__,
            "suite_description": self.suite_description,
            "cases": [
                {
                    "name": case.name,
                    "prompt": case.prompt,
                    "response": case.response,
                    "score": case.score,
                    "max_score": case.max_score,
                    "passed": case.passed,
                    "category": case.category,
                    "difficulty": case.difficulty,
                    "suite_name": case.suite_name,
                    "missing_keywords": list(case.missing_keywords),
                    "forbidden_matches": list(case.forbidden_matches),
                    "error": case.error,
                }
                for case in self.cases
            ],
            "category_scores": dict(self.category_scores),
            "report_paths": dict(self.report_paths),
        }
