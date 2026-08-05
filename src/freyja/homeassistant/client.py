from __future__ import annotations

from typing import Any

import httpx


class HomeAssistantClient:
    """Minimal async client for Home Assistant's authenticated REST API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token.strip()
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._token)

    async def health(self) -> bool:
        if not self.configured:
            return False
        try:
            response = await self._request("GET", "/api/")
        except (httpx.HTTPError, ValueError):
            return False
        return response.status_code == 200

    async def states(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/api/states")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("Home Assistant states response must be an array of objects")
        return payload

    async def call_service(self, domain: str, service: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not domain.replace("_", "").isalnum() or not service.replace("_", "").isalnum():
            raise ValueError("invalid Home Assistant service name")
        response = await self._request("POST", f"/api/services/{domain}/{service}", json=data)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Home Assistant service response must be an array")
        return [item for item in payload if isinstance(item, dict)]

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.configured:
            raise RuntimeError("Home Assistant is not configured")
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self._timeout, headers=headers, transport=self._transport) as client:
            return await client.request(method, f"{self.base_url}{path}", **kwargs)
