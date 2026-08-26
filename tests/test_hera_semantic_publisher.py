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
            "--metadata-json",
            '{"sensor":"camera"}',
        ]
    )

    assert status == 0
    assert seen["url"] == "http://atlas:8300/events/semantic"
    assert seen["headers"]["Authorization"] == "Bearer test-token"
    assert seen["headers"]["x-freyja-security-domain"] == "system"
    assert seen["json"]["source_machine_id"] == "hera"
    assert seen["json"]["event_type"] == "person_present"
    assert seen["json"]["metadata"] == {"sensor": "camera"}
    assert '"ok":true' in capsys.readouterr().out.replace(" ", "")


def test_hera_semantic_publisher_rejects_non_object_metadata(capsys) -> None:
    status = hera_semantic_publisher.main(
        [
            "--event-type",
            "camera_unavailable",
            "--confidence",
            "1.0",
            "--metadata-json",
            '["not", "an", "object"]',
        ]
    )

    assert status == 2
    assert "metadata json must decode to an object" in capsys.readouterr().err


def test_hera_semantic_publisher_reads_event_defaults_from_environment(monkeypatch) -> None:
    seen: dict = {}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict, json: dict):
            seen["json"] = json
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(hera_semantic_publisher.httpx, "Client", FakeClient)
    monkeypatch.setenv("FREYJA3_EVENT_TYPE", "camera_unavailable")
    monkeypatch.setenv("FREYJA3_EVENT_CONFIDENCE", "1.0")
    monkeypatch.setenv("FREYJA3_EVENT_ROOM", "hera")
    monkeypatch.setenv("FREYJA3_EVENT_METADATA_JSON", '{"reason":"camera"}')

    status = hera_semantic_publisher.main([])

    assert status == 0
    assert seen["json"]["event_type"] == "camera_unavailable"
    assert seen["json"]["confidence"] == 1.0
    assert seen["json"]["room"] == "hera"
    assert seen["json"]["metadata"] == {"reason": "camera"}
