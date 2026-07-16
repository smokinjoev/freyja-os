"""Tests for read-only local host tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from freyja.tools.local_host import (
    _ALLOWED_EXECUTABLES,
    _executable_path,
    _hostname_implementation,
    _run_read_only_command,
    _safe_hostname,
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
        # The returned hostname must not contain shell metacharacters.
        assert ";" not in result.output["hostname"]
        assert "rm" not in result.output["hostname"].lower()

    @pytest.mark.asyncio
    async def test_hostname_rejects_compromised_binary(self, monkeypatch):
        """A malicious hostname binary must not leak commands into the output."""

        async def _fake_run(executable: str, args: list[str], **kwargs):
            return {
                "command": f"{executable} {' '.join(args)}",
                "stdout": "; rm -rf /",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 1,
                "success": True,
            }

        monkeypatch.setattr("freyja.tools.local_host._run_read_only_command", _fake_run)
        # Also make scutil unavailable so the implementation falls back to socket.
        monkeypatch.setitem(_ALLOWED_EXECUTABLES, "scutil", None)
        monkeypatch.setattr("socket.gethostname", lambda: "safe-fallback-host")

        result = await _hostname_implementation(ToolExecutionRequest(tool_name="hostname", arguments={}))
        assert result["success"] is True
        assert result["hostname"] == "safe-fallback-host"
        assert ";" not in result["hostname"]

    @pytest.mark.asyncio
    async def test_hostname_fails_when_every_source_is_compromised(self, monkeypatch):
        async def _fake_run(executable: str, args: list[str], **kwargs):
            return {
                "command": f"{executable} {' '.join(args)}",
                "stdout": "; rm -rf /",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 1,
                "success": True,
            }

        monkeypatch.setattr("freyja.tools.local_host._run_read_only_command", _fake_run)
        monkeypatch.setitem(_ALLOWED_EXECUTABLES, "scutil", None)
        monkeypatch.setattr("socket.gethostname", lambda: "; rm -rf /")

        result = await _hostname_implementation(ToolExecutionRequest(tool_name="hostname", arguments={}))
        assert result["success"] is False
        assert "hostname output is not a valid hostname" in result["stderr"]

    def test_safe_hostname_validation(self):
        assert _safe_hostname("Iris") == "Iris"
        assert _safe_hostname("joes-Mac-mini") == "joes-Mac-mini"
        assert _safe_hostname("host-1.local") == "host-1.local"
        assert _safe_hostname("  Iris  ") == "Iris"
        assert _safe_hostname("; rm -rf /") is None
        assert _safe_hostname("host name") is None
        assert _safe_hostname("") is None


class TestCurrentTimeTool:
    @pytest.mark.asyncio
    async def test_current_time_tool_success(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="current_time", arguments={})
        result = await registry.execute(req)
        assert result.success is True
        assert "iso_timestamp" in result.output
        assert result.output["success"] is True


class TestDiskUsageTool:
    @pytest.fixture(autouse=True)
    def _repo_root(self):
        self.repo_root = Path(__file__).resolve().parents[1]

    @pytest.mark.asyncio
    async def test_disk_usage_default_path(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={})
        result = await registry.execute(req)
        assert result.success is True
        assert result.output["path"] == str(self.repo_root)
        assert result.output["success"] is True

    @pytest.mark.asyncio
    async def test_disk_usage_repo_root(self, registry: ToolRegistry):
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(self.repo_root)})
        result = await registry.execute(req)
        assert result.success is True
        assert result.output["success"] is True
        assert result.output["path"] == str(self.repo_root)

    @pytest.mark.asyncio
    async def test_disk_usage_normal_inside_repo(self, registry: ToolRegistry):
        path = self.repo_root / "src"
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(path)})
        result = await registry.execute(req)
        assert result.success is True
        assert result.output["success"] is True
        assert result.output["path"] == str(path.resolve())

    @pytest.mark.asyncio
    async def test_disk_usage_dotdot_traversal_outside_repo(self, registry: ToolRegistry):
        path = self.repo_root / ".." / "etc"
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(path)})
        result = await registry.execute(req)
        assert result.success is True
        assert result.output["success"] is False
        assert "outside the allowed repository root" in result.output["stderr"]

    @pytest.mark.asyncio
    async def test_disk_usage_symlink_inside_pointing_outside(self, registry: ToolRegistry, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        symlink = self.repo_root / f".tmp_symlink_outside_{uuid4().hex}"
        try:
            symlink.symlink_to(outside)
            req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(symlink)})
            result = await registry.execute(req)
            assert result.success is True
            assert result.output["success"] is False
            assert "symlink" in result.output["stderr"].lower()
        finally:
            symlink.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_disk_usage_symlink_chain_escapes_repo(self, registry: ToolRegistry, tmp_path):
        outside = tmp_path / "outside_chain"
        outside.mkdir()
        link_a = tmp_path / "link_a"
        link_b = self.repo_root / f".tmp_symlink_chain_{uuid4().hex}"
        link_a.symlink_to(outside)
        try:
            link_b.symlink_to(link_a)
            req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(link_b)})
            result = await registry.execute(req)
            assert result.success is True
            assert result.output["success"] is False
            assert "symlink" in result.output["stderr"].lower()
        finally:
            link_b.unlink(missing_ok=True)
            link_a.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_disk_usage_symlink_stays_inside_repo(self, registry: ToolRegistry):
        target = self.repo_root / "src"
        symlink = self.repo_root / f".tmp_symlink_inside_{uuid4().hex}"
        try:
            symlink.symlink_to(target)
            req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(symlink)})
            result = await registry.execute(req)
            assert result.success is True
            assert result.output["success"] is True
            assert result.output["path"] == str(target.resolve())
        finally:
            symlink.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_disk_usage_nonexistent_path_inside_repo(self, registry: ToolRegistry):
        path = self.repo_root / f".tmp_nonexistent_{uuid4().hex}"
        req = ToolExecutionRequest(tool_name="disk_usage", arguments={"path": str(path)})
        result = await registry.execute(req)
        assert result.success is True
        # `df` may fail for a nonexistent path, but the policy check passes.
        assert "outside" not in result.output["stderr"]
        assert "symlink" not in result.output["stderr"].lower()


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
