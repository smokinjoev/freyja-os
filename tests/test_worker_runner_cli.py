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


def test_worker_runner_fails_unknown_worker_class_closed(monkeypatch) -> None:
    requests: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-2", "worker_class": "ingestion"}})
        return httpx.Response(200, json={"ok": True, "job": {"job_id": "job-2", "status": "failed"}})

    monkeypatch.setattr(httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))

    assert worker_runner.main(["--base-url", "http://atlas", "--machine-id", "mars", "--worker-class", "ingestion"]) == 0
    assert b'"status":"failed"' in requests[1].content
    assert b"is not implemented" in requests[1].content
