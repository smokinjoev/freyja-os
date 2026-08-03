from __future__ import annotations

import asyncio
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import yaml

from certification import __version__
from certification.grader import grade_response
from certification.models import CaseResult, CertificationCase, CertificationReport, CertificationSuite, ReportMetadata

DEFAULT_SUITE_DIR = Path(__file__).resolve().parent / "suites"
DIFFICULTIES = ("smoke", "standard", "stress", "chaos")


class CertificationProvider(Protocol):
    name: str
    model: str

    async def complete(self, prompt: str) -> tuple[str, str | None]:
        ...


class OllamaCertificationProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, client: object | None = None) -> None:
        from freyja.config import settings
        from freyja.ollama_client import OllamaClient

        self.model = model or settings.ollama_chat_model or settings.ollama_model
        self._client = client or OllamaClient(model=self.model)

    async def complete(self, prompt: str) -> tuple[str, str | None]:
        response = await self._client.chat(prompt=prompt, model=self.model)
        if error := response.get("error"):
            return "", str(error)
        return str(response.get("response", "")), None


def load_suite(name: str, suite_dir: Path = DEFAULT_SUITE_DIR) -> CertificationSuite:
    if name in DIFFICULTIES:
        return load_gauntlet(difficulty=name, suite_dir=suite_dir)
    if name == "all":
        return load_gauntlet(difficulty=None, suite_dir=suite_dir)

    suite_path = resolve_suite_path(name, suite_dir=suite_dir)
    if not suite_path.exists():
        available = ", ".join(list_suite_names(suite_dir)) or "none"
        raise ValueError(f"Unknown certification suite '{name}'. Available suites: {available}")

    return _load_suite_file(suite_path, suite_dir=suite_dir)


def load_gauntlet(difficulty: str | None = "smoke", suite_dir: Path = DEFAULT_SUITE_DIR) -> CertificationSuite:
    suites = [_load_suite_file(path, suite_dir=suite_dir) for path in sorted(suite_dir.rglob("*.yaml"))]
    cases = tuple(
        case
        for suite in suites
        for case in suite.cases
        if difficulty is None or case.difficulty == difficulty
    )
    if not cases:
        label = difficulty or "all"
        raise ValueError(f"No certification cases found for difficulty '{label}'")
    label = difficulty or "all"
    return CertificationSuite(
        name=label,
        description=f"Freyja Certification Gauntlet ({label})",
        cases=cases,
        category="gauntlet",
        difficulty=label,
    )


def resolve_suite_path(name: str, suite_dir: Path = DEFAULT_SUITE_DIR) -> Path:
    normalized = name[:-5] if name.endswith(".yaml") else name
    direct = suite_dir / f"{normalized}.yaml"
    if direct.exists():
        return direct

    matches = [path for path in suite_dir.rglob("*.yaml") if path.stem == normalized or str(path.relative_to(suite_dir).with_suffix("")) == normalized]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(path.relative_to(suite_dir).with_suffix("")) for path in matches)
        raise ValueError(f"Ambiguous certification suite '{name}'. Use one of: {choices}")
    return direct


def _load_suite_file(suite_path: Path, suite_dir: Path = DEFAULT_SUITE_DIR) -> CertificationSuite:
    data = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    category = str(data.get("category") or suite_path.parent.name)
    difficulty = str(data.get("difficulty") or "standard")
    suite_name = str(data.get("name") or suite_path.stem)
    cases = tuple(
        CertificationCase(
            name=str(case["name"]),
            prompt=str(case["prompt"]),
            expected_keywords=tuple(case.get("expected_keywords", ())),
            forbidden_keywords=tuple(case.get("forbidden_keywords", ())),
            max_score=float(case.get("max_score", 1.0)),
            category=str(case.get("category") or category),
            difficulty=str(case.get("difficulty") or difficulty),
            suite_name=suite_name,
        )
        for case in data.get("cases", ())
    )
    if not cases:
        suite_id = str(suite_path.relative_to(suite_dir).with_suffix(""))
        raise ValueError(f"Certification suite '{suite_id}' has no cases")
    return CertificationSuite(
        name=suite_name,
        description=str(data.get("description") or ""),
        cases=cases,
        category=category,
        difficulty=difficulty,
        path=str(suite_path),
    )


def list_suite_names(suite_dir: Path = DEFAULT_SUITE_DIR) -> list[str]:
    return sorted(str(path.relative_to(suite_dir).with_suffix("")) for path in suite_dir.rglob("*.yaml"))


async def run_suite(
    suite: CertificationSuite,
    provider: CertificationProvider,
    router_mode: str = "default",
) -> CertificationReport:
    started = time.monotonic()
    case_results = []
    for case in suite.cases:
        response, error = await provider.complete(case.prompt)
        case_results.append(grade_response(case, response, error=error))

    execution_time = time.monotonic() - started
    max_score = sum(case.max_score for case in case_results)
    earned = sum(case.score for case in case_results)
    overall_score = earned / max_score if max_score else 0.0
    category_scores = _category_scores(case_results)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")

    return CertificationReport(
        metadata=ReportMetadata(
            timestamp=timestamp,
            git_sha=_git(["rev-parse", "HEAD"]),
            branch=_git(["branch", "--show-current"]),
            working_tree="dirty" if _git(["status", "--porcelain"]) else "clean",
            hostname=socket.gethostname(),
            provider=provider.name,
            model=provider.model,
            router_mode=router_mode,
            suite_name=suite.name,
            overall_score=overall_score,
            execution_time=execution_time,
            certification_cli_version=__version__,
        ),
        suite_description=suite.description,
        cases=tuple(case_results),
        category_scores=category_scores,
    )


def run_suite_sync(
    suite: CertificationSuite,
    provider: CertificationProvider,
    router_mode: str = "default",
) -> CertificationReport:
    return asyncio.run(run_suite(suite=suite, provider=provider, router_mode=router_mode))


def _git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _category_scores(case_results: list[CaseResult]) -> dict[str, float]:
    scores: dict[str, tuple[float, float]] = {}
    for case in case_results:
        earned, max_score = scores.get(case.category, (0.0, 0.0))
        scores[case.category] = (earned + case.score, max_score + case.max_score)
    return {
        category: (earned / max_score if max_score else 0.0)
        for category, (earned, max_score) in sorted(scores.items())
    }
