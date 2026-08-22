"""Read-only local host tools for Freyja-OS on Iris.

This module provides bounded, fixed-executable diagnostic tools.  No generic
command interface is exposed: each tool maps to a fixed allowlisted executable
and argument list.  ``shell=True`` is never used.  All tools are read-only and
return structured results including stdout, stderr, exit_code, duration_ms,
and a clear success/failure flag.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from freyja.config import settings
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


#: Absolute executable paths that may be invoked by local read-only tools.
_ALLOWED_EXECUTABLES: dict[str, str | None] = {
    "hostname": shutil.which("hostname"),
    "scutil": shutil.which("scutil"),
    "date": shutil.which("date"),
    "df": shutil.which("df"),
    "curl": shutil.which("curl"),
    "git": shutil.which("git"),
}

#: Repository root for git_status and disk_usage.
_REPO_ROOT = Path(settings.repository_root).expanduser().resolve()

#: Maximum bytes captured per stream before truncation.
_MAX_CAPTURE_BYTES = 128 * 1024

#: Default timeout for local command tools (seconds).
_DEFAULT_TIMEOUT_SECONDS = 10

#: Valid hostname characters: alphanumeric, hyphen, dot, underscore. Must not
#: contain whitespace or shell metacharacters that could be misinterpreted.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,253}$")


def _safe_hostname(raw: str | None) -> str | None:
    """Return the raw string if it looks like a real hostname, otherwise None."""
    if not raw:
        return None
    cleaned = raw.strip().splitlines()[0]
    if not _HOSTNAME_RE.match(cleaned):
        return None
    return cleaned


def _executable_path(name: str) -> str:
    """Return the resolved path for an allowlisted executable.

    Raises RuntimeError if the executable is not available on this host.
    """
    path = _ALLOWED_EXECUTABLES.get(name)
    if not path:
        raise RuntimeError(f"Required executable '{name}' is not available on this host")
    return path


async def _run_read_only_command(
    executable: str,
    args: list[str],
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Run a fixed executable with fixed arguments and return a structured result.

    The command is never passed through a shell.  Captured stdout and stderr are
    truncated to ``_MAX_CAPTURE_BYTES``.  The result includes exit_code,
    duration_ms, and a success flag based solely on the process exit status.
    """
    path = _executable_path(executable)
    command = [path, *args]
    start = time.monotonic()
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
            ),
            timeout=timeout_seconds,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        duration_ms = int((time.monotonic() - start) * 1000)

        stdout = stdout_bytes[:_MAX_CAPTURE_BYTES].decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes[:_MAX_CAPTURE_BYTES].decode("utf-8", errors="replace").strip()
        success = proc.returncode == 0

        return {
            "command": " ".join(command),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "duration_ms": duration_ms,
            "success": success,
        }
    except asyncio.TimeoutError:
        return {
            "command": " ".join(command),
            "stdout": "",
            "stderr": f"Command timed out after {timeout_seconds} seconds",
            "exit_code": -1,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "success": False,
        }
    except Exception as exc:
        return {
            "command": " ".join(command),
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "success": False,
        }


async def _hostname_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    """Return the system hostname, preferring macOS scutil if available.

    On this host the ``hostname`` binary and ``socket.gethostname()`` both
    return the same compromised value (``; rm -rf /``), so we rely on
    ``scutil --get LocalHostName`` first, then validate anything we return.
    """
    scutil = _ALLOWED_EXECUTABLES.get("scutil")
    if scutil:
        result = await _run_read_only_command("scutil", ["--get", "LocalHostName"])
        raw = result.get("stdout", "")
        hostname = _safe_hostname(raw)
        if result["success"] and hostname is not None:
            return {
                "hostname": hostname,
                **result,
            }

    result = await _run_read_only_command("hostname", [])
    raw = result.get("stdout", "")
    hostname = _safe_hostname(raw)
    if result["success"] and hostname is not None:
        return {
            "hostname": hostname,
            **result,
        }

    # Last resort: a pure-Python hostname, but still validate it. A compromised
    # system can also return garbage from socket.gethostname().
    safe = _safe_hostname(socket.gethostname())
    if safe:
        result = {
            "command": "hostname",
            "stdout": safe,
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 0,
            "success": True,
        }
        result["hostname"] = safe
        return result

    return {
        "command": "hostname",
        "stdout": "",
        "stderr": "hostname output is not a valid hostname and no fallback is available",
        "exit_code": 1,
        "duration_ms": result.get("duration_ms", 0),
        "success": False,
    }


async def _current_time_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    # Prefer the fixed ISO-8601 output from `date -Iseconds` when available.
    result = await _run_read_only_command("date", ["-Iseconds"])
    if result["success"]:
        return {
            "iso_timestamp": result["stdout"],
            "utc_timestamp": datetime.now(timezone.utc).isoformat(),
            **result,
        }
    # Fallback to a pure-Python timestamp if `date` is unavailable.
    return {
        "command": "",
        "stdout": datetime.now(timezone.utc).isoformat(),
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 0,
        "success": True,
        "iso_timestamp": datetime.now(timezone.utc).isoformat(),
        "utc_timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _disk_usage_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    target = request.arguments.get("path", str(_REPO_ROOT))
    repo_root = _REPO_ROOT.resolve()

    try:
        # Resolve the requested path fully, including any symlinks and ``..``
        # segments.  If the fully resolved real path leaves the repository root,
        # the request is rejected regardless of where the original path began.
        real_path = Path(target).resolve(strict=False)
    except (OSError, ValueError) as exc:
        return {
            "command": "",
            "stdout": "",
            "stderr": f"Path '{target}' cannot be resolved: {exc}",
            "exit_code": 1,
            "duration_ms": 0,
            "success": False,
        }

    try:
        real_path.relative_to(repo_root)
    except ValueError:
        return {
            "command": "",
            "stdout": "",
            "stderr": f"Path '{target}' is outside the allowed repository root",
            "exit_code": 1,
            "duration_ms": 0,
            "success": False,
        }

    result = await _run_read_only_command("df", ["-h", str(real_path)])
    if result["success"]:
        return {
            "path": str(real_path),
            **result,
        }
    return result


async def _director_health_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    start = time.monotonic()
    url = f"http://{settings.freyja_host}:{settings.freyja_port}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            duration_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code == 200
            return {
                "url": url,
                "status_code": response.status_code,
                "body": response.text[:_MAX_CAPTURE_BYTES],
                "duration_ms": duration_ms,
                "success": success,
            }
    except Exception as exc:
        return {
            "url": url,
            "status_code": -1,
            "body": "",
            "duration_ms": int((time.monotonic() - start) * 1000),
            "success": False,
            "error": str(exc),
        }


async def _repository_status_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    result = await _run_read_only_command(
        "git",
        ["-c", f"safe.directory={_REPO_ROOT}", "status", "--short", "--branch"],
        cwd=_REPO_ROOT,
    )
    if result["success"]:
        return {
            "repository_root": str(_REPO_ROOT),
            "branch_status": result["stdout"],
            **result,
        }
    return result


_LOCAL_HOST_TOOL_NAMES = (
    "hostname",
    "current_time",
    "disk_usage",
    "director_health",
    "repository_status",
)


def register_local_host_tools(registry: ToolRegistry) -> None:
    """Register the read-only local host diagnostic tools."""
    registry.register(
        ToolDefinition(
            name="hostname",
            description="Return the system hostname for the Iris host.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "hostname": {"type": "string"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=5,
            tags=["host", "read-only"],
        ),
        _hostname_implementation,
    )
    registry.register(
        ToolDefinition(
            name="current_time",
            description="Return the current system time in ISO-8601 format.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "iso_timestamp": {"type": "string"},
                    "utc_timestamp": {"type": "string"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=5,
            tags=["host", "read-only"],
        ),
        _current_time_implementation,
    )
    registry.register(
        ToolDefinition(
            name="disk_usage",
            description="Return disk usage for a path. Defaults to the Freyja-OS repository root.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to check disk usage for; defaults to the repository root.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["host", "read-only"],
        ),
        _disk_usage_implementation,
    )
    registry.register(
        ToolDefinition(
            name="director_health",
            description="Check whether the Freyja Director /health endpoint is reachable.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "status_code": {"type": "integer"},
                    "body": {"type": "string"},
                    "duration_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["freyja", "health", "read-only"],
        ),
        _director_health_implementation,
    )
    registry.register(
        ToolDefinition(
            name="repository_status",
            description="Return `git status --short --branch` for the Freyja-OS repository.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "repository_root": {"type": "string"},
                    "branch_status": {"type": "string"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["git", "repository", "read-only"],
        ),
        _repository_status_implementation,
    )
