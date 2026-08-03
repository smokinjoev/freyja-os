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
from certification.models import CertificationCase, CertificationReport, CertificationSuite, ReportMetadata

DEFAULT_SUITE_DIR = Path(__file__).resolve().parent / "suites"


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
    suite_path = suite_dir / f"{name}.yaml"
    if not suite_path.exists():
        available = ", ".join(list_suite_names(suite_dir)) or "none"
        raise ValueError(f"Unknown certification suite '{name}'. Available suites: {available}")

    data = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    cases = tuple(
        CertificationCase(
            name=str(case["name"]),
            prompt=str(case["prompt"]),
            expected_keywords=tuple(case.get("expected_keywords", ())),
            forbidden_keywords=tuple(case.get("forbidden_keywords", ())),
            max_score=float(case.get("max_score", 1.0)),
        )
        for case in data.get("cases", ())
    )
    if not cases:
        raise ValueError(f"Certification suite '{name}' has no cases")
    return CertificationSuite(
        name=str(data.get("name") or name),
        description=str(data.get("description") or ""),
        cases=cases,
        path=str(suite_path),
    )


def list_suite_names(suite_dir: Path = DEFAULT_SUITE_DIR) -> list[str]:
    return sorted(path.stem for path in suite_dir.glob("*.yaml"))


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
