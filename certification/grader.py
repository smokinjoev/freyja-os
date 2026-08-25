from __future__ import annotations

import re
import unicodedata
from typing import Any

from certification.models import CaseResult, CertificationCase


def grade_response(
    case: CertificationCase,
    response: str,
    error: str | None = None,
    runtime_context: dict[str, Any] | None = None,
    verifier_results: tuple[dict[str, Any], ...] = (),
) -> CaseResult:
    """Grade a single response with simple, deterministic keyword checks."""
    runtime_context = runtime_context or {}
    if error:
        return CaseResult(
            name=case.name,
            prompt=case.prompt,
            response=response,
            score=0.0,
            max_score=case.max_score,
            passed=False,
            category=case.category,
            difficulty=case.difficulty,
            suite_name=case.suite_name,
            runtime_context=runtime_context,
            verifier_results=verifier_results,
            error=error,
        )

    normalized_response = _normalize_for_match(response)
    missing = tuple(keyword for keyword in case.expected_keywords if _normalize_for_match(keyword) not in normalized_response)
    forbidden = tuple(keyword for keyword in case.forbidden_keywords if _normalize_for_match(keyword) in normalized_response)
    verifier_failed = any(not result.get("passed", False) for result in verifier_results)
    passed = not missing and not forbidden and not verifier_failed
    score = case.max_score if passed else 0.0

    return CaseResult(
        name=case.name,
        prompt=case.prompt,
        response=response,
        score=score,
        max_score=case.max_score,
        passed=passed,
        category=case.category,
        difficulty=case.difficulty,
        suite_name=case.suite_name,
        runtime_context=runtime_context,
        verifier_results=verifier_results,
        missing_keywords=missing,
        forbidden_matches=forbidden,
    )


def _normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized
