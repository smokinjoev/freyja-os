from __future__ import annotations

from certification.models import CaseResult, CertificationCase


def grade_response(case: CertificationCase, response: str, error: str | None = None) -> CaseResult:
    """Grade a single response with simple, deterministic keyword checks."""
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
            error=error,
        )

    lowered = response.lower()
    missing = tuple(keyword for keyword in case.expected_keywords if keyword.lower() not in lowered)
    forbidden = tuple(keyword for keyword in case.forbidden_keywords if keyword.lower() in lowered)
    passed = not missing and not forbidden
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
        missing_keywords=missing,
        forbidden_matches=forbidden,
    )
