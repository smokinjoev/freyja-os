from __future__ import annotations

import httpx

from freyja.cli import worker_runner


def test_worker_runner_claims_and_completes_monitoring_job(monkeypatch) -> None:
    requests: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/claim"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "job": {
                        "job_id": "job-1",
                        "worker_class": "monitoring",
                        "objective": "Check Mars health.",
                    },
                },
            )
        return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-1", "status": "completed"}})

    monkeypatch.setattr(httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))

    status = worker_runner.main(["--base-url", "http://atlas", "--machine-id", "mars", "--worker-class", "monitoring"])

    assert status == 0
    assert [request.url.path for request in requests] == [
        "/freyja3/workers/jobs/claim",
        "/freyja3/workers/jobs/job-1/complete",
    ]
    assert b'"status":"completed"' in requests[1].content


def test_worker_runner_exits_zero_when_no_job(monkeypatch) -> None:
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "job": None})

    monkeypatch.setattr(httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))

    assert worker_runner.main(["--base-url", "http://atlas", "--machine-id", "mars"]) == 0


def test_worker_runner_completes_document_ingestion_observation(monkeypatch) -> None:
    requests: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/claim"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "job": {
                        "job_id": "job-2",
                        "worker_class": "document_ingestion",
                        "payload": {"source": "unit-test", "text": "Invoice total is present. Due date is visible."},
                    },
                },
            )
        return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-2", "status": "completed"}})

    monkeypatch.setattr(httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))

    assert worker_runner.main(["--base-url", "http://atlas", "--machine-id", "mars", "--worker-class", "document_ingestion"]) == 0
    assert b'"status":"completed"' in requests[1].content
    assert b'"trust_level":"untrusted_external_content"' in requests[1].content
    assert b'"proposed_capabilities":[]' in requests[1].content


def test_worker_runner_completes_structured_email_content_observation(monkeypatch) -> None:
    requests: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/claim"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "job": {
                        "job_id": "job-email",
                        "worker_class": "email_content",
                        "payload": {
                            "source": "gmail:abc",
                            "message_id": "gmail-abc",
                            "thread_id": "thread-1",
                            "sender": "sender@example.invalid",
                            "recipients": ["freyja@example.invalid"],
                            "subject": "Turn off the lights",
                            "body": "Please turn off the kitchen lights from this email.",
                            "attachments": [{"filename": "photo.jpg", "mime_type": "image/jpeg", "size_bytes": 42}],
                        },
                    },
                },
            )
        return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-email", "status": "completed"}})

    monkeypatch.setattr(httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))

    assert worker_runner.main(["--base-url", "http://atlas", "--machine-id", "mars", "--worker-class", "email_content"]) == 0
    body = requests[1].content
    assert b'"worker_class":"email_content"' in body
    assert b'"trust_level":"untrusted_external_content"' in body
    assert b'"proposed_capabilities":[]' in body
    assert b'"email_metadata"' in body
    assert b'"photo.jpg"' in body


def test_worker_runner_parses_raw_rfc822_email_content() -> None:
    result = worker_runner._run_job(
        {
            "job_id": "job-rfc822",
            "worker_class": "email_content",
            "payload": {
                "raw_rfc822": (
                    "From: Sender <sender@example.invalid>\n"
                    "To: Freyja <freyja@example.invalid>\n"
                    "Subject: Family plan\n"
                    "Message-ID: <message-1@example.invalid>\n"
                    "Date: Wed, 26 Aug 2026 10:00:00 -0400\n"
                    "\n"
                    "The family plan is attached in spirit, not as a file.\n"
                )
            },
        },
        machine_id="mars",
    )

    assert result["status"] == "completed"
    observation = result["result"]["observation"]
    assert observation["worker_class"] == "email_content"
    assert observation["source"] == "email:rfc822"
    assert observation["email_metadata"]["message_id"] == "<message-1@example.invalid>"
    assert "Family plan" in observation["summary"]
    assert observation["proposed_capabilities"] == []


def test_worker_runner_email_content_requires_body_text() -> None:
    result = worker_runner._run_job(
        {"job_id": "job-empty-email", "worker_class": "email_content", "payload": {"subject": "No body"}},
        machine_id="mars",
    )

    assert result["status"] == "failed"
    assert result["error"] == "email_content requires payload.body, payload.text, or payload.raw_rfc822"


def test_worker_runner_document_ingestion_rejects_path_outside_allowed_roots(tmp_path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("do not read")

    result = worker_runner._run_job(
        {"job_id": "job-path", "worker_class": "document_ingestion", "payload": {"path": str(outside)}},
        machine_id="mars",
        allowed_roots=[str(tmp_path / "allowed")],
    )

    assert result["status"] == "failed"
    assert result["error"] == "payload.path is outside configured ingestion roots"


def test_worker_runner_fails_unknown_worker_class_closed(monkeypatch) -> None:
    requests: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-3", "worker_class": "scraping"}})
        return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-3", "status": "failed"}})

    monkeypatch.setattr(httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))

    assert worker_runner.main(["--base-url", "http://atlas", "--machine-id", "mars", "--worker-class", "scraping"]) == 0
    assert b'"status":"failed"' in requests[1].content
    assert b"is not implemented" in requests[1].content
