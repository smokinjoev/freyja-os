"""IrisMaintenanceBackend: tightly scoped controlled-write maintenance tools.

This module registers the only three maintenance tools that require elevated
or write privileges for Agent Smith:

* ``bounded_file_write`` – explicit, approved file writes inside the repository.
* ``git_commit``         – a fixed git commit operation (no push).
* ``restart_freyja_director`` – restart the Director LaunchAgent via a fixed script.

No generic command interface is exposed to Agent Smith.  All subprocess calls
use fixed executable paths and fixed argument arrays; ``shell=True`` is never
used.  Path boundaries, secret-path rejection, atomic writes, rollback copies,
and a minimal environment are enforced throughout.
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freyja.config import settings
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

#: Maximum bytes captured per stream before truncation.
_MAX_CAPTURE_BYTES = 128 * 1024

#: Maximum length of a stream that is returned in the JSON output.
_MAX_OUTPUT_CHARS = 8 * 1024

#: Absolute executable paths that may be invoked by this backend.
#:
#: Note: ``/usr/bin/git`` is the only executable needed for the fixed
#: ``git_commit`` operation.  No generic command interface is exposed to
#: Agent Smith.  ``/usr/bin/systemctl`` and generic read-only utilities such
#: as ``/bin/cat``, ``/bin/ls``, ``/bin/df`` have been intentionally removed.
_ALLOWED_EXECUTABLES = {
    "/usr/bin/git",
}

#: Fixed command templates.  These are not exposed to Smith; they are used
#: only by the fixed ``git_commit`` implementation.
_COMMAND_TEMPLATES: dict[str, list[str]] = {
    "git_status": ["/usr/bin/git", "-C", "{repo}", "status", "--short", "--branch"],
    "git_add_single": ["/usr/bin/git", "-C", "{repo}", "add", "{path}"],
    "git_commit": ["/usr/bin/git", "-C", "{repo}", "commit", "-m", "{message}"],
}

_SECRET_PATH_PATTERNS = [
    re.compile(r"(^|/|\.)env"),
    re.compile(r"(^|/)secrets?(/|$)"),
    re.compile(r"(^|/|\.)(key|pem|crt|p12|pfx|keystore)(/|$)"),
    re.compile(r"(^|/)\.ssh(/|$)"),
    re.compile(r"(^|/)\.aws(/|$)"),
    re.compile(r"(^|/)\.git-credentials(/|$)"),
    re.compile(r"(^|/)\.password-store(/|$)"),
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESTART_DIRECTOR_SCRIPT = str(_REPO_ROOT / "scripts" / "restart-director.sh")
_RESTART_DIRECTOR_FIXED_ARGS = []


def _is_secret_path(path: Path) -> bool:
    path_str = str(path)
    return any(pattern.search(path_str) for pattern in _SECRET_PATH_PATTERNS)


def _minimal_environment() -> dict[str, str]:
    """Return a minimal environment that avoids inheriting secret-bearing variables."""
    allowed = {"HOME", "LANG", "LC_ALL", "LC_CTYPE", "LOGNAME", "USER"}
    env: dict[str, str] = {}
    for key in allowed:
        value = os.environ.get(key)
        if value:
            env[key] = value
    # Use a tightly controlled PATH so no arbitrary directories are searched.
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return env


class MaintenanceError(Exception):
    """Raised when a maintenance operation fails validation or execution."""


class PathViolationError(MaintenanceError):
    """Raised when a requested path is outside the allowed root or is secret."""


class IrisMaintenanceBackend:
    """Hardened controlled-write backend for Agent Smith maintenance tools."""

    def __init__(self, allowed_root: Path | None = None) -> None:
        self._allowed_root = (allowed_root or _get_allowed_root()).resolve()

    @property
    def allowed_root(self) -> Path:
        return self._allowed_root

    def resolve_within_root(self, requested_path: str) -> Path:
        """Resolve *requested_path* within the allowed root.

        Rejects absolute paths outside the root, paths containing parent
        references that escape the root, symlink escapes, and secret-looking paths.
        """
        # Reject empty paths and paths with obvious parent-traversal components.
        if not requested_path:
            raise PathViolationError("Path must not be empty")
        raw = Path(requested_path)
        parts = raw.parts
        if ".." in parts:
            raise PathViolationError(
                f"Path '{requested_path}' contains forbidden parent references",
            )
        if raw.is_absolute():
            resolved = raw.resolve()
        else:
            resolved = (self._allowed_root / raw).resolve()
        try:
            resolved.relative_to(self._allowed_root)
        except ValueError as exc:
            raise PathViolationError(
                f"Path '{requested_path}' is outside the allowed root '{self._allowed_root}'",
            ) from exc
        # Reject symlink escapes: after resolve(), the real path must still be
        # under the allowed root.
        real_resolved = resolved.resolve(strict=False)
        try:
            real_resolved.relative_to(self._allowed_root)
        except ValueError as exc:
            raise PathViolationError(
                f"Path '{requested_path}' resolves to a real path outside the allowed root",
            ) from exc
        if _is_secret_path(resolved):
            raise PathViolationError(
                f"Path '{requested_path}' matches a protected secret pattern",
            )
        return resolved

    def backup_path(self, target: Path) -> Path:
        """Return a unique backup path for *target* under the same directory."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return target.parent / f"{target.name}.bak.{timestamp}"

    async def bounded_file_write(
        self,
        requested_path: str,
        content: str,
        *,
        approved: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Write *content* to *requested_path* inside the allowed root.

        Requires ``approved=True``.  Before writing, a rollback copy of the
        existing file is created with ``shutil.copy2`` in the same directory.
        The actual write is performed atomically with a temporary file and
        ``os.replace``.  All validation (root boundary, symlink escape,
        secret pattern) is performed before any filesystem modification.
        """
        if not approved:
            return {
                "success": False,
                "error": "File write was not explicitly approved (approved=True is required)",
                "path": requested_path,
                "request_id": request_id,
            }

        # Resolve and validate the path *before* any filesystem mutation.
        target = self.resolve_within_root(requested_path)

        if target.exists() and not target.is_file():
            return {
                "success": False,
                "error": f"Path '{requested_path}' is not a regular file",
                "path": str(target),
                "request_id": request_id,
            }

        backup_record: dict[str, Any] | None = None
        if target.exists():
            backup = self.backup_path(target)
            if backup.exists():
                return {
                    "success": False,
                    "error": f"Backup path '{backup}' already exists; aborting",
                    "path": str(target),
                    "request_id": request_id,
                }
            try:
                shutil.copy2(str(target), str(backup))
            except Exception as exc:  # noqa: BLE001
                return {
                    "success": False,
                    "error": f"Failed to create rollback copy: {exc}",
                    "path": str(target),
                    "request_id": request_id,
                }
            backup_record = {"original": str(target), "backup": str(backup)}

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(target.parent),
                prefix=f".{target.name}",
                suffix=".tmp",
                delete=False,
            ) as tmp_handle:
                tmp_handle.write(content)
                tmp_path = Path(tmp_handle.name)
            os.replace(str(tmp_path), str(target))
        except Exception as exc:  # noqa: BLE001
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return {
                "success": False,
                "error": f"Failed to write file: {exc}",
                "path": str(target),
                "backup": backup_record,
                "request_id": request_id,
            }

        return {
            "success": True,
            "path": str(target),
            "bytes_written": len(content.encode("utf-8")),
            "backup": backup_record,
            "request_id": request_id,
        }

    async def git_add(
        self,
        repo_path: str,
        files: list[str],
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Stage an explicit list of repository-relative files.

        * *files* must be a non-empty list of reviewed repository-relative paths.
        * Absolute paths, parent traversal, symlink escapes, protected/secret
          paths, option-like values (strings beginning with ``-``), ``.``,
          ``-A``, ``--all``, and wildcards are rejected.
        * Each path is resolved under *repo_path*, which itself must lie within
          the allowed root.
        * Only the fixed ``/usr/bin/git`` executable is invoked with a fixed
          argument array; user-supplied values are passed as individual
          positional arguments and are never interpreted as git options.
        """
        try:
            repo = self.resolve_within_root(repo_path)
        except PathViolationError as exc:
            return {
                "success": False,
                "error": _sanitize_path_error(exc),
                "request_id": request_id,
            }

        if not isinstance(files, list) or not files:
            return {
                "success": False,
                "error": "files must be a non-empty list of reviewed repository-relative paths",
                "request_id": request_id,
            }

        resolved_files: list[str] = []
        for raw in files:
            if not isinstance(raw, str):
                return {
                    "success": False,
                    "error": f"Invalid file entry type in files list: {type(raw).__name__}",
                    "request_id": request_id,
                }
            if raw == "" or raw.startswith("-"):
                return {
                    "success": False,
                    "error": f"Rejected option-like or empty file entry: {raw!r}",
                    "request_id": request_id,
                }
            if raw in {".", "-A", "--all", "--refresh", "--update", "--ignore-removal"}:
                return {
                    "success": False,
                    "error": f"Rejected broad staging directive: {raw!r}",
                    "request_id": request_id,
                }
            if any(ch in raw for ch in "*?["):
                return {
                    "success": False,
                    "error": f"Rejected wildcard in file entry: {raw!r}",
                    "request_id": request_id,
                }
            raw_path = Path(raw)
            try:
                if raw_path.is_absolute():
                    resolved = self.resolve_within_root(raw)
                else:
                    resolved = self.resolve_within_root(str(repo / raw))
            except PathViolationError as exc:
                return {
                    "success": False,
                    "error": _sanitize_path_error(exc),
                    "request_id": request_id,
                }
            try:
                resolved.relative_to(repo)
            except ValueError:
                return {
                    "success": False,
                    "error": f"File entry {raw!r} resolves outside the repository",
                    "request_id": request_id,
                }
            resolved_files.append(str(resolved))

        args: list[str] = ["/usr/bin/git", "-C", str(repo), "add", "--"]
        args.extend(resolved_files)
        return await self._execute_fixed_command(
            args,
            timeout_seconds=30,
            request_id=request_id,
            command_key="git_add",
        )

    async def git_commit(
        self,
        repo_path: str,
        message: str,
        *,
        file_path: str | None = None,
        files: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Commit changes in *repo_path* after staging an explicit file list.

        * *file_path* is deprecated; prefer *files*, which is hardened through
          :meth:`git_add`.
        * This deliberately does not push and is limited to the allowed root.
        * Only the fixed ``/usr/bin/git`` executable and fixed argument arrays are
          used.
        """
        repo = self.resolve_within_root(repo_path)
        if files is not None:
            stage = await self.git_add(str(repo), files, request_id=request_id)
            if not stage["success"]:
                return stage
        elif file_path is not None:
            target = self.resolve_within_root(file_path)
            stage = await self._execute_command(
                "git_add_single",
                {"repo": str(repo), "path": str(target)},
                timeout_seconds=30,
                request_id=request_id,
            )
            if not stage["success"]:
                return stage
        return await self._execute_command(
            "git_commit",
            {"repo": str(repo), "message": message},
            timeout_seconds=30,
            request_id=request_id,
        )

    async def restart_freyja_director(
        self,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Restart the Freyja Director service using the fixed restart script."""
        script = Path(_RESTART_DIRECTOR_SCRIPT)
        if not script.is_file():
            return {
                "success": False,
                "error": f"Restart script not found: {_RESTART_DIRECTOR_SCRIPT}",
                "request_id": request_id,
            }

        start = time.monotonic()
        argv = [str(script), *_RESTART_DIRECTOR_FIXED_ARGS]
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=_minimal_environment(),
                ),
                timeout=90,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            duration_ms = int((time.monotonic() - start) * 1000)
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "restart_freyja_director exceeded 90s timeout",
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "timeout": True,
                "duration_ms": int((time.monotonic() - start) * 1000),
                "request_id": request_id,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "error": f"Failed to run restart script: {exc}",
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "timeout": False,
                "duration_ms": int((time.monotonic() - start) * 1000),
                "request_id": request_id,
            }

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": _tail_output(stdout_text),
            "stderr_tail": _tail_output(stderr_text),
            "timeout": False,
            "duration_ms": duration_ms,
            "command": "restart_freyja_director",
            "script": str(script),
            "request_id": request_id,
        }

    async def _execute_command(
        self,
        command_key: str,
        substitutions: dict[str, Any],
        *,
        timeout_seconds: int = 30,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a fixed command template with *substitutions*.

        Substitutions are applied safely: placeholder values are treated as
        literal arguments, never split or interpreted by a shell.
        """
        if command_key not in _COMMAND_TEMPLATES:
            raise MaintenanceError(f"Unknown command template '{command_key}'")
        template = _COMMAND_TEMPLATES[command_key]
        executable = template[0]
        if executable not in _ALLOWED_EXECUTABLES:
            raise MaintenanceError(f"Executable '{executable}' is not in the allowlist")

        args: list[str] = []
        for token in template:
            if token.startswith("{") and token.endswith("}"):
                key = token[1:-1]
                value = substitutions.get(key)
                if value is None:
                    raise MaintenanceError(f"Missing substitution for '{key}'")
                args.append(str(value))
            else:
                args.append(token)

        return await self._execute_fixed_command(
            args,
            timeout_seconds=timeout_seconds,
            request_id=request_id,
            command_key=command_key,
        )

    async def _execute_fixed_command(
        self,
        args: list[str],
        *,
        timeout_seconds: int = 30,
        request_id: str | None = None,
        command_key: str,
    ) -> dict[str, Any]:
        """Run a fully-built argument array as a subprocess.

        The caller is responsible for ensuring every element of *args* is a
        trusted literal; no shell interpretation occurs.
        """
        if not args:
            raise MaintenanceError("Cannot execute an empty argument list")
        executable = args[0]
        if executable not in _ALLOWED_EXECUTABLES:
            raise MaintenanceError(f"Executable '{executable}' is not in the allowlist")

        start = time.monotonic()
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=_minimal_environment(),
                ),
                timeout=timeout_seconds,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            duration_ms = int((time.monotonic() - start) * 1000)
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Command '{command_key}' exceeded {timeout_seconds}s timeout",
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "timeout": True,
                "duration_ms": int((time.monotonic() - start) * 1000),
                "request_id": request_id,
            }
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": False,
                "error": f"Failed to run command: {exc}",
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "timeout": False,
                "duration_ms": duration_ms,
                "request_id": request_id,
            }

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        stdout_tail = _tail_output(stdout_text)
        stderr_tail = _tail_output(stderr_text)

        record = {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "stdout_size": len(stdout_bytes),
            "stderr_size": len(stderr_bytes),
            "timeout": False,
            "duration_ms": duration_ms,
            "request_id": request_id,
            "command": command_key,
        }
        return record


def _sanitize_path_error(exc: PathViolationError) -> str:
    """Return a generic, user-safe message from a PathViolationError."""
    message = str(exc)
    if "matches a protected secret pattern" in message:
        return "Path matches a protected secret pattern"
    if "parent references" in message:
        return "Path contains forbidden parent references"
    if "real path outside" in message:
        return "Path resolves outside the allowed root through a symlink"
    return "Path is outside the allowed root"


def _get_allowed_root() -> Path:
    root = Path(getattr(settings, "agent_smith_allowed_root", str(_REPO_ROOT)))
    if not root.is_absolute():
        root = _REPO_ROOT / root
    return root.resolve()


def _tail_output(text: str, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[-max_chars:]
    if "\n" in truncated:
        truncated = truncated[truncated.index("\n") + 1 :]
    return f"<truncated>\n{truncated}"


#: Module-level backend instance used by tool implementations.
_backend: IrisMaintenanceBackend | None = None


def _get_backend() -> IrisMaintenanceBackend:
    global _backend
    if _backend is None:
        _backend = IrisMaintenanceBackend()
    return _backend


def _set_backend(backend: IrisMaintenanceBackend | None) -> None:
    global _backend
    _backend = backend


async def _bounded_file_write_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    return await _get_backend().bounded_file_write(
        args["path"],
        args["content"],
        approved=args.get("approved", False),
        request_id=request.request_id,
    )


async def _git_commit_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    return await _get_backend().git_commit(
        args.get("repo_path", "."),
        args["message"],
        file_path=args.get("file_path"),
        request_id=request.request_id,
    )


async def _restart_freyja_director_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    return await _get_backend().restart_freyja_director(request_id=request.request_id)


async def _git_add_implementation(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    return await _get_backend().git_add(
        args.get("repo_path", "."),
        args["files"],
        request_id=request.request_id,
    )


def register_smith_controlled_tools(registry: ToolRegistry) -> None:
    """Register the only controlled-write maintenance tools available to Smith."""
    registry.register(
        ToolDefinition(
            name="bounded_file_write",
            description=(
                "Explicitly approved overwrite of a file within the allowed repository root. "
                "Creates a rollback backup and writes atomically."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["path", "content", "approved"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "approved": {"type": "boolean"},
                },
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "iris", "controlled_write", "filesystem"],
        ),
        _bounded_file_write_implementation,
    )
    registry.register(
        ToolDefinition(
            name="git_add",
            description="Stage an explicit list of reviewed files within the allowed repository root.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["files"],
                "properties": {
                    "repo_path": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "iris", "controlled_write", "git"],
        ),
        _git_add_implementation,
    )
    registry.register(
        ToolDefinition(
            name="git_commit",
            description="Stage and commit changes within the allowed repository root (no push).",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["message"],
                "properties": {
                    "repo_path": {"type": "string"},
                    "message": {"type": "string"},
                    "file_path": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "iris", "controlled_write", "git"],
        ),
        _git_commit_implementation,
    )
    registry.register(
        ToolDefinition(
            name="restart_freyja_director",
            description="Restart the Freyja Director LaunchAgent via the fixed restart script.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=True,
            timeout_seconds=90,
            tags=["smith", "iris", "controlled_write", "service"],
        ),
        _restart_freyja_director_implementation,
    )


def register_smith_iris_maintenance_tools(registry: ToolRegistry) -> None:
    """Alias for :func:`register_smith_controlled_tools`."""
    register_smith_controlled_tools(registry)
