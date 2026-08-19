from __future__ import annotations

import asyncio
from typing import Any

import fastapi.testclient
import httpx
import pytest

from freyja.config import settings
from freyja.tools.calendar import set_calendar_service


class ASGITestClient:
    """Synchronous test client backed by httpx ASGITransport.

    The Starlette TestClient bundled through this dependency set can block on
    requests under Python 3.14. Tests only need a small sync get/post/put
    surface, so run each request through an isolated async ASGI client.
    """

    __test__ = False

    def __init__(self, app: Any, base_url: str = "http://testserver", **kwargs: Any) -> None:
        self.app = app
        self.base_url = base_url
        self.client = kwargs.get("client", ("127.0.0.1", 123))

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def _request() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, client=self.client)
            async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def __enter__(self) -> "ASGITestClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


fastapi.testclient.TestClient = ASGITestClient


@pytest.fixture(autouse=True)
def stable_calendar_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "calendar_default_provider", "memory")
    monkeypatch.setattr(settings, "apple_calendar_enabled", False)
    set_calendar_service(None)
    yield
    set_calendar_service(None)
