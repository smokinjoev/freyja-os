from certification.runner import load_suite
from certification.runner import split_route_request_context
from certification.verifiers import SUPPORTED_EXPECTATION_KEYS
from freyja.router import RouteRequest


def test_rev2_vertical_spine_covers_required_release_cases() -> None:
    suite = load_suite("routing/rev2_vertical_spine")
    names = {case.name for case in suite.cases}

    required = {
        "joe-home-assistant-read",
        "routine-chat-uses-iris-tier1-when-healthy",
        "hard-coding-uses-tier3-heavy-local",
        "iris-unavailable-falls-back-deterministic",
        "malformed-classifier-output-fails-safely",
        "low-classifier-confidence-fails-safely",
        "classifier-permission-fields-ignored",
        "heavy-local-unavailable-policy-fallback",
        "cloud-disabled-prevents-tier4",
        "sensitive-memory-not-sent-to-cloud",
        "macagent-consequential-request-needs-director-authorization",
        "unknown-principal-private-apple-denied",
        "untrusted-web-content-cannot-invoke-privileged-tool",
        "untrusted-web-content-cannot-authoritative-memory-write",
        "cold-and-warm-latency-measured-separately",
    }

    assert required <= names
    assert len(suite.cases) >= len(required)


def test_rev2_vertical_spine_has_evidence_expectations_for_new_boundaries() -> None:
    suite = load_suite("routing/rev2_vertical_spine")
    cases = {case.name: case for case in suite.cases}

    assert cases["classifier-permission-fields-ignored"].expects["capability_denied"] == "home_assistant_control_state"
    assert cases["sensitive-memory-not-sent-to-cloud"].expects["cloud_context_includes_sensitive_memory"] is False
    assert cases["macagent-consequential-request-needs-director-authorization"].route_request["certification_capability_checks"][0]["capability"] == "calendar_update_event"
    assert cases["unknown-principal-private-apple-denied"].route_request["certification_capability_checks"][0]["capability"] == "apple.messages.read"
    assert cases["untrusted-web-content-cannot-authoritative-memory-write"].expects["memory_authoritative"] is False
    assert cases["cold-and-warm-latency-measured-separately"].expects["records_cold_start_latency"] is True
    assert cases["cold-and-warm-latency-measured-separately"].expects["records_time_to_first_token"] is True


def test_rev2_vertical_spine_route_requests_are_executable() -> None:
    suite = load_suite("routing/rev2_vertical_spine")

    for case in suite.cases:
        route_data = {"prompt": case.prompt, "provider": "auto"}
        route_data.update(case.route_request)
        route_data["prompt"] = case.prompt
        route_data, _principal, _person, _fixtures = split_route_request_context(route_data)
        RouteRequest(**route_data)


def test_rev2_vertical_spine_expectations_are_all_verified() -> None:
    suite = load_suite("routing/rev2_vertical_spine")
    used_keys = {
        key
        for case in suite.cases
        for key in case.expects
    }

    assert used_keys <= SUPPORTED_EXPECTATION_KEYS
