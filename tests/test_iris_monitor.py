from unittest.mock import AsyncMock

import pytest

from freyja.config import settings
from freyja.iris_monitor import _darwin_available_memory_mb, iris_warm_monitor_enabled, warm_iris_once


class _Client:
    def __init__(self, *, warmed: bool = True, resident: bool = True) -> None:
        self.warm = AsyncMock(return_value=warmed)
        self.model_resident = AsyncMock(return_value=resident)


def test_iris_warm_monitor_requires_iris_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "iris_router_enabled", False)
    monkeypatch.setattr(settings, "iris_router_warm_enabled", True)
    assert iris_warm_monitor_enabled() is False

    monkeypatch.setattr(settings, "iris_router_enabled", True)
    assert iris_warm_monitor_enabled() is True


def test_darwin_available_memory_counts_inactive_reclaimable_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    def _check_output(command: list[str], text: bool) -> str:
        if command == ["sysctl", "-n", "hw.pagesize"]:
            return "16384\n"
        if command == ["vm_stat"]:
            return "\n".join(
                [
                    "Mach Virtual Memory Statistics: (page size of 16384 bytes)",
                    "Pages free: 100.",
                    "Pages inactive: 200.",
                    "Pages speculative: 300.",
                    "Pages purgeable: 400.",
                ]
            )
        raise AssertionError(command)

    monkeypatch.setattr("freyja.iris_monitor.subprocess.check_output", _check_output)

    assert _darwin_available_memory_mb() == 15


async def test_warm_iris_once_verifies_residency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("freyja.iris_monitor.available_memory_mb", lambda: 8192)
    monkeypatch.setattr(settings, "iris_router_min_available_memory_mb", 8192)
    client = _Client(warmed=True, resident=True)

    result = await warm_iris_once(client)  # type: ignore[arg-type]

    assert result["warmed"] is True
    assert result["resident"] is True
    client.warm.assert_awaited_once()
    client.model_resident.assert_awaited_once()


async def test_warm_iris_once_skips_when_memory_is_low(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("freyja.iris_monitor.available_memory_mb", lambda: 2048)
    monkeypatch.setattr(settings, "iris_router_min_available_memory_mb", 8192)
    client = _Client()

    result = await warm_iris_once(client)  # type: ignore[arg-type]

    assert result["event"] == "iris_router_warm_skipped_low_memory"
    assert result["warmed"] is False
    client.warm.assert_not_awaited()
    client.model_resident.assert_not_awaited()
