from __future__ import annotations

import httpx

from freyja.cli import hera_semantic_publisher


def test_hera_semantic_publisher_posts_system_event(monkeypatch, capsys) -> None:
    seen: dict = {}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            seen["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict, json: dict):
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(hera_semantic_publisher.httpx, "Client", FakeClient)

    status = hera_semantic_publisher.main(
        [
            "--url",
            "http://atlas:8300/events/semantic",
            "--token",
            "test-token",
            "--event-type",
            "person_present",
            "--room",
            "kitchen",
            "--subject",
            "joe",
            "--confidence",
            "0.91",
        ]
    )

    assert status == 0
    assert seen["url"] == "http://atlas:8300/events/semantic"
    assert seen["headers"]["Authorization"] == "Bearer test-token"
    assert seen["headers"]["x-freyja-security-domain"] == "system"
    assert seen["json"]["source_machine_id"] == "hera"
    assert seen["json"]["event_type"] == "person_present"
    assert '"ok":true' in capsys.readouterr().out.replace(" ", "")
