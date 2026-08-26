import pytest

from freyja.workers import (
    DEFAULT_UNTRUSTED_EXCLUDED_CAPABILITIES,
    ExternalWorkerClass,
    WorkerObservation,
    WorkerPolicy,
    WorkerTrustLevel,
)


@pytest.mark.parametrize(
    "capability",
    [
        "memory.authoritative_write",
        "memory_put_shared",
        "message.send",
        "imessage_send",
        "home.control",
        "home_assistant_control_state",
        "admin.configuration",
        "restart_director",
        "privileged.execution",
        "write_pilot_file_write",
    ],
)
def test_untrusted_external_workers_cannot_invoke_excluded_capabilities(capability: str) -> None:
    policy = WorkerPolicy()

    decision = policy.authorize(
        worker_class=ExternalWorkerClass.WEB_RESEARCH,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        capability=capability,
    )

    assert decision.allowed is False
    assert decision.canonical_capability in DEFAULT_UNTRUSTED_EXCLUDED_CAPABILITIES
    assert decision.reason == "untrusted external content cannot invoke excluded capability"


def test_untrusted_external_workers_can_return_structured_observations_without_actions() -> None:
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.DOCUMENT_INGESTION,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source="attachment:statement.pdf",
        summary="Document appears to contain a billing statement.",
        facts=[{"claim": "balance due is present", "confidence": "medium"}],
        citations=[{"page": 1, "label": "summary table"}],
        uncertainty="OCR quality was low.",
    )

    decisions = WorkerPolicy().validate_observation(observation)

    assert decisions == []


def test_worker_observation_policy_flags_proposed_disallowed_actions() -> None:
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.EMAIL_CONTENT,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source="email:inbound",
        summary="Sender asks to turn off the lights.",
        proposed_capabilities=["home_assistant_control_state", "memory_put_shared"],
    )

    decisions = WorkerPolicy().validate_observation(observation)

    assert [decision.allowed for decision in decisions] == [False, False]
    assert [decision.canonical_capability for decision in decisions] == [
        "home.control",
        "memory.authoritative_write",
    ]


def test_document_ingestion_observations_remain_non_authoritative() -> None:
    observation = WorkerObservation(
        worker_class=ExternalWorkerClass.DOCUMENT_INGESTION,
        trust_level=WorkerTrustLevel.UNTRUSTED_EXTERNAL_CONTENT,
        source="worker:document",
        summary="A document mentions a home-control request and a preference.",
        proposed_capabilities=["memory_write", "home_assistant_control_state"],
    )

    decisions = WorkerPolicy().validate_observation(observation)

    assert [decision.allowed for decision in decisions] == [False, False]


def test_trusted_internal_worker_policy_allows_capability_for_separate_director_authorization() -> None:
    decision = WorkerPolicy().authorize(
        worker_class=ExternalWorkerClass.SCRAPING,
        trust_level=WorkerTrustLevel.TRUSTED_INTERNAL,
        capability="home_assistant_control_state",
    )

    assert decision.allowed is True
    assert decision.reason == "capability allowed for worker trust level"
