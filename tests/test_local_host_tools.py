"""Tests for read-only local host tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.tools.local_host import (
    _ALLOWED_EXECUTABLES,
    _executable_path,
    _run_read_only_command,
    register_local_host_tools,
)
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry(audit_enabled=False)
    register_local_host_tools(r)
    return r


class TestAllowlist:
    def test_executable_path_resolves_existing(self):
        for name in _ALLOWED_EXECUTABLES:
            path = _ALLOWED_EXECUTABLES[name]
            if path:
                assert _executable_path(name) == path

    def test_executable_path_missing_raises(self):
        # Simulate an executable that is not in the allowlist.
        with pytest.raises(RuntimeError):
            _executable_path("nonexistent_tool")


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_successful_hostname(self):
        result = await _run_read_only_command("hostname", [])
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["stdout"] != ""
        assert "duration_ms" in result

    @pytest.mark.asyncio
    async def test_successful_date(self):
        result = await _run_read_only_command("date", ["-Iseconds"])
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["stdout"] != ""

    @pytest.mark.asyncio
    async def test_failure_nonzero_exit(self):
        result = await _run_read_only_command("git", ["not-a-valid-subcommand"])
        assert result["success"] is False
        assert result["exit_code"] != 0
        assert result["stderr"] != ""

    @pytest.mark.asyncio
    async def test_timeout(self):
        # Use the always-available `date` executable with a tiny timeout and
        # patch the create_subprocess_exec coroutine to simulate a hang.
        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError,
        ):
            result = await _run_read_only_command("date", ["-Iseconds"], timeout_seconds=0.1)
        assert result["success"] is False
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"].lower()

    @pytest.mark.asyncio
    async def test_no_shell_injection(self):
        result = await _run_read_only_command("hostname", ["; rm -rf /"])
        # `hostname` treats the whole string as one argument, so no shell runs.
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "; rm" not in result["stdout"]


class TestHostnameTool:
    @pytest.mark.asyncio
    async def test_hostname_tool_success(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="hostname", arguments={})
        result = await registry.execute(req)
        assert result.success is True
        assert "hostname" in result.output
        assert result.output["success"] is True
        assert result.output["exit_code"] == 0


class TestCurrentTimeTool:
    @pytest.mark.asyncio
    async def test_current_time_tool_success(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="current_time", arguments={})
        result = await registry.execute(req)
        assert result.success is True
        assert "iso_timestamp" in result.output
        assert result.output["success"] is True


class TestDiskUsageTool:
    @pytest.mark.asyncio
    async def test_disk_usage_default_path(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={})
        result = await registry.execute(req)
        assert result.success is True
        assert result.output["path"] == str(Path(__file__).resolve().parents[1])
        assert result.output["success"] is True

    @pytest.mark.asyncio
    async def test_disk_usage_disallowed_path(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": "/etc"})
        result = await registry.execute(req)
        # Registry-level success means the tool executed without crashing.
        assert result.success is True
        # Tool-level success reflects the policy check.
        assert result.output["success"] is False
        assert "outside the allowed roots" in result.output["stderr"]


class TestDirectorHealthTool:
    @pytest.mark.asyncio
    async def test_director_health_success(self, registry: ToolRegistry):
        response = httpx.Response(200, text='{"status":"healthy"}')
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=response):
            req = ToolExecutionRequest(tool_name="director_health", arguments={})
            result = await registry.execute(req)
        assert result.success is True
        assert result.output["status_code"] == 200
        assert result.output["success"] is True

    @pytest.mark.asyncio
    async def test_director_health_failure(self, registry: ToolRegistry):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
            req = ToolExecutionRequest(tool_name="director_health", arguments={})
            result = await registry.execute(req)
        assert result.success is True
        assert result.output["success"] is False
        assert "refused" in result.output["error"].lower()


class TestRepositoryStatusTool:
    @pytest.mark.asyncio
    async def test_repository_status_success(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="repository_status", arguments={})
        result = await registry.execute(req)
        assert result.success is True
        assert "repository_root" in result.output
        assert "branch_status" in result.output
        assert result.output["success"] is True


class TestValidation:
    @pytest.mark.asyncio
    async def test_disallowed_tool_not_in_registry(self, registry: ToolRegistry):
        assert registry.get_tool("arbitrary_shell") is None

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_not_found(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="rm_rf_root", arguments={})
        result = await registry.execute(req)
        assert result.success is False
        assert result.error_code == "tool_not_found"

    @pytest.mark.asyncio
    async def test_disabled_tool(self, registry: ToolRegistry):
        registry.set_enabled("hostname", False)
        req = ToolExecutionRequest(tool_name="hostname", arguments={})
        result = await registry.execute(req)
        assert result.success is False
        assert result.error_code == "tool_disabled"
