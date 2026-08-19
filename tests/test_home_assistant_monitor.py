import pytest

from freyja.config import settings
from freyja.home_assistant_monitor import (
    home_assistant_inventory_monitor_enabled,
    poll_home_assistant_inventory_once,
)
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> ToolRegistry:
    monkeypatch.setattr(settings, "tools_enabled", True)
    registry = ToolRegistry(audit_enabled=False)
    register_builtin_tools(registry)
    return registry


def test_home_assistant_inventory_monitor_requires_rest_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "home_assistant_inventory_poll_enabled", True)
    monkeypatch.setattr(settings, "home_assistant_base_url", "")
    monkeypatch.setattr(settings, "home_assistant_access_token", "")

    assert home_assistant_inventory_monitor_enabled() is False

    monkeypatch.setattr(settings, "home_assistant_base_url", "http://homeassistant.local:8123")
    monkeypatch.setattr(settings, "home_assistant_access_token", "token")

    assert home_assistant_inventory_monitor_enabled() is True


async def test_home_assistant_inventory_monitor_executes_inventory_tool(
    registry: ToolRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "home_assistant_inventory_snapshot_path", str(tmp_path / "ha-inventory.json"))
    monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"sensor.kitchen_temperature":"72"}')

    result = await poll_home_assistant_inventory_once(registry)

    assert result["success"] is True
    assert result["snapshot_updated"] is True
    assert result["current_count"] == 1
    assert (tmp_path / "ha-inventory.json").exists()
