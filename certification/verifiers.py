from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from certification.context import CertificationContext
from certification.models import CertificationCase


@dataclass(frozen=True)
class VerificationResult:
    verifier: str
    passed: bool
    assertion: str
    expected: Any = None
    actual: Any = None
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier": self.verifier,
            "passed": self.passed,
            "assertion": self.assertion,
            "expected": self.expected,
            "actual": self.actual,
            "evidence": self.evidence,
        }


class Verifier:
    name = "verifier"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        return []


class RouterVerifier(Verifier):
    name = "router"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expects = case.expects
        results: list[VerificationResult] = []
        if "provider" in expects:
            results.append(_result(self.name, "provider", expects["provider"], context.provider_selected))
        if "provider_not" in expects:
            results.append(_not_result(self.name, "provider_not", expects["provider_not"], context.provider_selected))
        if "privacy_local" in expects:
            actual = context.provider_selected in {"ollama", "local_reasoning"}
            results.append(_result(self.name, "privacy_local", bool(expects["privacy_local"]), actual))
        return results


class ToolVerifier(Verifier):
    name = "tool"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expects = case.expects
        called = {call.name for call in context.tool_calls}
        results: list[VerificationResult] = []
        for tool in _as_list(expects.get("tool_called")):
            results.append(_contains_result(self.name, "tool_called", tool, called))
        for tool in _as_list(expects.get("tool_not_called")):
            results.append(_not_contains_result(self.name, "tool_not_called", tool, called))
        return results


class CapabilityVerifier(Verifier):
    name = "capability"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expects = case.expects
        results: list[VerificationResult] = []
        authorized = {
            str(item.get("capability")): bool(item.get("allowed"))
            for item in context.capability_authorizations
            if isinstance(item, dict)
        }
        for capability in _as_list(expects.get("capability_authorized")):
            results.append(_result(self.name, "capability_authorized", True, authorized.get(str(capability))))
        for capability in _as_list(expects.get("capability_denied")):
            results.append(_result(self.name, "capability_denied", False, authorized.get(str(capability))))
        return results


class MemoryVerifier(Verifier):
    name = "memory"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        if "memory_lookup" not in case.expects:
            return []
        return [_result(self.name, "memory_lookup", bool(case.expects["memory_lookup"]), bool(context.memory_lookups))]


class VisionVerifier(Verifier):
    name = "vision"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        if "vision_used" not in case.expects:
            return []
        return [_result(self.name, "vision_used", bool(case.expects["vision_used"]), bool(context.vision_executions))]


class ConnectorVerifier(Verifier):
    name = "connector"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expected = case.expects.get("connector_called")
        if expected is None:
            return []
        called = {operation.get("connector") for operation in context.connector_operations}
        return [_contains_result(self.name, "connector_called", expected, called)]


class ResponseVerifier(Verifier):
    name = "response"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expects = case.expects
        lowered = response.lower()
        results: list[VerificationResult] = []
        for text in _as_list(expects.get("response_contains")):
            results.append(_contains_result(self.name, "response_contains", text.lower(), lowered))
        for text in _as_list(expects.get("response_not_contains")):
            results.append(_not_contains_result(self.name, "response_not_contains", text.lower(), lowered))
        return results


def discover_verifiers() -> list[Verifier]:
    verifier_types = Verifier.__subclasses__()
    return [verifier_type() for verifier_type in verifier_types]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _result(verifier: str, assertion: str, expected: Any, actual: Any) -> VerificationResult:
    return VerificationResult(verifier=verifier, passed=actual == expected, assertion=assertion, expected=expected, actual=actual)


def _not_result(verifier: str, assertion: str, expected: Any, actual: Any) -> VerificationResult:
    return VerificationResult(verifier=verifier, passed=actual != expected, assertion=assertion, expected=expected, actual=actual)


def _contains_result(verifier: str, assertion: str, expected: Any, actual: Any) -> VerificationResult:
    return VerificationResult(verifier=verifier, passed=expected in actual, assertion=assertion, expected=expected, actual=sorted(actual) if isinstance(actual, set) else actual)


def _not_contains_result(verifier: str, assertion: str, expected: Any, actual: Any) -> VerificationResult:
    return VerificationResult(verifier=verifier, passed=expected not in actual, assertion=assertion, expected=expected, actual=sorted(actual) if isinstance(actual, set) else actual)
