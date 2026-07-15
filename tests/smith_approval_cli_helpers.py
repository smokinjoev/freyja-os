"""Test helpers for the smith_approval CLI.

Provides an in-process transport backed by a FastAPI TestClient so the CLI
can be exercised without a live Director server.
"""

from __future__ import annotations

import json
from typing import Any


def make_test_client_transport(client: Any):
    """Return a transport callable for smith_approval._api_call."""

    def _transport(method: str, path: str, data: dict[str, Any] | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if data is not None:
            kwargs["json"] = data
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            from freyja.cli.smith_approval import ApiError

            try:
                payload = response.json()
            except Exception:
                payload = {"detail": response.text}
            raise ApiError(
                response.status_code,
                payload.get("detail", response.text),
                payload,
            )
        return response.json()

    return _transport
