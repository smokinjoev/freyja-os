from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
import sys
import textwrap
from typing import Any

from certification.context import CertificationContext
from certification.models import CertificationCase


SUPPORTED_EXPECTATION_KEYS = frozenset(
    {
        "provider",
        "provider_not",
        "privacy_local",
        "selected_tier",
        "selected_tier_not",
        "provider_profile_id",
        "tool_called",
        "tool_not_called",
        "capability_authorized",
        "capability_denied",
        "memory_lookup",
        "cloud_context_includes_sensitive_memory",
        "memory_authoritative",
        "memory_provenance_kind",
        "vision_used",
        "connector_called",
        "response_contains",
        "response_not_contains",
        "classifier_failed_safe",
        "classifier_confidence_below_threshold",
        "worker_action_allowed",
        "macagent_director_authorized",
        "python_behavior",
        "records_cold_start_latency",
        "records_warm_start_latency",
        "records_total_provider_latency",
        "records_time_to_first_token",
    }
)


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
        if "selected_tier" in expects:
            results.append(_result(self.name, "selected_tier", expects["selected_tier"], context.selected_tier))
        if "selected_tier_not" in expects:
            results.append(_not_result(self.name, "selected_tier_not", expects["selected_tier_not"], context.selected_tier))
        if "provider_profile_id" in expects:
            results.append(_result(self.name, "provider_profile_id", expects["provider_profile_id"], context.provider_profile_id))
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
        expects = case.expects
        results: list[VerificationResult] = []
        if "memory_lookup" in expects:
            results.append(_result(self.name, "memory_lookup", bool(expects["memory_lookup"]), bool(context.memory_lookups)))
        if "cloud_context_includes_sensitive_memory" in expects:
            actual = any(bool(item.get("included_in_cloud")) and item.get("sensitivity") == "sensitive" for item in context.memory_lookups if isinstance(item, dict))
            results.append(_result(self.name, "cloud_context_includes_sensitive_memory", bool(expects["cloud_context_includes_sensitive_memory"]), actual))
        if "memory_authoritative" in expects:
            actual = _first_evidence_value(context, "memory_authoritative")
            results.append(_result(self.name, "memory_authoritative", expects["memory_authoritative"], actual))
        if "memory_provenance_kind" in expects:
            actual = _first_evidence_value(context, "memory_provenance_kind")
            results.append(_result(self.name, "memory_provenance_kind", expects["memory_provenance_kind"], actual))
        return results


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


class ClassifierVerifier(Verifier):
    name = "classifier"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expects = case.expects
        results: list[VerificationResult] = []
        if "classifier_failed_safe" in expects:
            actual = bool(context.classifier_error or context.fallback_events or _first_evidence_value(context, "classifier_failed_safe"))
            results.append(_result(self.name, "classifier_failed_safe", bool(expects["classifier_failed_safe"]), actual))
        if "classifier_confidence_below_threshold" in expects:
            actual = _first_evidence_value(context, "classifier_confidence_below_threshold")
            if actual is None and context.classifier_confidence is not None:
                actual = context.classifier_confidence < 0.8
            results.append(_result(self.name, "classifier_confidence_below_threshold", bool(expects["classifier_confidence_below_threshold"]), actual))
        return results


class WorkerVerifier(Verifier):
    name = "worker"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        if "worker_action_allowed" not in case.expects:
            return []
        return [_result(self.name, "worker_action_allowed", case.expects["worker_action_allowed"], _first_evidence_value(context, "worker_action_allowed"))]


class MacAgentVerifier(Verifier):
    name = "macagent"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        if "macagent_director_authorized" not in case.expects:
            return []
        return [_result(self.name, "macagent_director_authorized", case.expects["macagent_director_authorized"], _first_evidence_value(context, "macagent_director_authorized"))]


class PythonBehaviorVerifier(Verifier):
    name = "python_behavior"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        checks = case.expects.get("python_behavior")
        if not checks:
            return []
        code = _extract_python_code(response)
        script = _python_behavior_script(code, checks)
        try:
            completed = subprocess.run(
                [sys.executable, "-I"],
                input=script,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [
                VerificationResult(
                    verifier=self.name,
                    passed=False,
                    assertion="python_behavior",
                    expected="all assertions pass",
                    actual=type(exc).__name__,
                    evidence=str(exc),
                )
            ]

        passed = completed.returncode == 0
        evidence = (completed.stderr or completed.stdout).strip()
        return [
            VerificationResult(
                verifier=self.name,
                passed=passed,
                assertion="python_behavior",
                expected="all assertions pass",
                actual="passed" if passed else f"exit {completed.returncode}",
                evidence=evidence[-1000:],
            )
        ]


class TimingVerifier(Verifier):
    name = "timing"

    def verify(self, case: CertificationCase, context: CertificationContext, response: str) -> list[VerificationResult]:
        expects = case.expects
        results: list[VerificationResult] = []
        timing_keys = {
            "records_cold_start_latency": "cold_start_latency_ms",
            "records_warm_start_latency": "warm_start_latency_ms",
            "records_total_provider_latency": "total_provider_latency_ms",
            "records_time_to_first_token": "time_to_first_token_ms",
        }
        for expectation, timing_key in timing_keys.items():
            if expectation in expects:
                actual = timing_key in context.timing or _first_evidence_value(context, expectation) is True
                results.append(_result(self.name, expectation, bool(expects[expectation]), actual))
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


def _extract_python_code(response: str) -> str:
    match = re.search(r"```(?:python|py)?\s*(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return response.strip()


def _python_behavior_script(code: str, checks: Any) -> str:
    if isinstance(checks, str):
        check_source = checks
    else:
        check_source = "\n".join(str(check) for check in _as_list(checks))
    return "\n".join(
        (
            code,
            "",
            textwrap.dedent(
                """
                def _freyja_assert(condition, message):
                    if not condition:
                        raise AssertionError(message)
                """
            ).strip(),
            check_source,
            "",
        )
    )


def _first_evidence_value(context: CertificationContext, key: str) -> Any:
    if key in context.rev2_evidence:
        return context.rev2_evidence[key]
    for collection in (
        context.connector_operations,
        context.memory_lookups,
        context.capability_authorizations,
        context.fallback_events,
    ):
        for item in collection:
            if isinstance(item, dict) and key in item:
                return item[key]
    return None
