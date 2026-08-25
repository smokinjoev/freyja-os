from __future__ import annotations

from certification.context import CertificationContext
from certification.models import CertificationCase
from certification.verifiers import PythonBehaviorVerifier


def test_python_behavior_verifier_accepts_stable_dict_deduplication() -> None:
    case = CertificationCase(
        name="dedupe",
        prompt="fix it",
        expects={
            "python_behavior": [
                '_freyja_assert(unique_stable(["b", "a", "b"]) == ["b", "a"], "keeps order")',
                "_freyja_assert(unique_stable([1, 1, 2, 1]) == [1, 2], \"deduplicates\")",
            ]
        },
    )
    response = """
```python
def unique_stable(seq):
    return list(dict.fromkeys(seq))
```
"""

    results = PythonBehaviorVerifier().verify(case, CertificationContext(), response)

    assert len(results) == 1
    assert results[0].passed is True


def test_python_behavior_verifier_accepts_branch_based_clamp() -> None:
    case = CertificationCase(
        name="clamp",
        prompt="fix it",
        expects={
            "python_behavior": [
                '_freyja_assert(clamp(11, 0, 10) == 10, "high")',
                '_freyja_assert(clamp(-1, 0, 10) == 0, "low")',
                '_freyja_assert(clamp(5, 0, 10) == 5, "middle")',
            ]
        },
    )
    response = """
def clamp(value, minimum, maximum):
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
"""

    results = PythonBehaviorVerifier().verify(case, CertificationContext(), response)

    assert len(results) == 1
    assert results[0].passed is True


def test_python_behavior_verifier_reports_failed_behavior() -> None:
    case = CertificationCase(
        name="clamp",
        prompt="fix it",
        expects={"python_behavior": '_freyja_assert(clamp(11, 0, 10) == 10, "high")'},
    )

    results = PythonBehaviorVerifier().verify(
        case,
        CertificationContext(),
        "def clamp(value, minimum, maximum):\n    return value",
    )

    assert len(results) == 1
    assert results[0].passed is False
    assert "AssertionError" in results[0].evidence
