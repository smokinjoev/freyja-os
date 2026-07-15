"""Tests for the hardened IrisMaintenanceBackend.

These tests verify that the only Smith maintenance surface is the fixed set of
controlled-write tools: ``bounded_file_write``, ``git_commit``, and
``restart_freyja_director``.  Generic command interfaces, broad executable
allowlists, and ``/usr/bin/systemctl`` must not be exposed.
"""

from pathlib import Path
from unittest import mock

import pytest

from freyja.tools.errors import ToolError
from freyja.tools.iris_maintenance import (
    IrisMaintenanceBackend,
    PathViolationError,
    _ALLOWED_EXECUTABLES,
    _COMMAND_TEMPLATES,
    register_smith_controlled_tools,
)
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def backend(tmp_path):
    return IrisMaintenanceBackend(allowed_root=tmp_path)


@pytest.fixture
def registry(tmp_path):
    """A registry that uses the controlled-write backend with a temp root."""
    tool_registry = ToolRegistry()
    backend = IrisMaintenanceBackend(allowed_root=tmp_path)

    def _make_implementation(tool_name):
        async def _impl(request: ToolExecutionRequest) -> dict:
            if tool_name == "bounded_file_write":
                return await backend.bounded_file_write(
                    request.arguments["path"],
                    request.arguments["content"],
                    approved=request.arguments.get("approved", False),
                    request_id=request.request_id,
                )
            if tool_name == "git_commit":
                return await backend.git_commit(
                    request.arguments.get("repo_path", "."),
                    request.arguments["message"],
                    file_path=request.arguments.get("file_path"),
                    files=request.arguments.get("files"),
                    request_id=request.request_id,
                )
            if tool_name == "git_add":
                return await backend.git_add(
                    request.arguments.get("repo_path", "."),
                    request.arguments["files"],
                    request_id=request.request_id,
                )
            if tool_name == "restart_freyja_director":
                return await backend.restart_freyja_director(request_id=request.request_id)
            raise RuntimeError(f"unexpected tool {tool_name}")

        return _impl

    tool_registry.register(
        ToolDefinition(
            name="bounded_file_write",
            description="test",
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "approved": {"type": "boolean"},
                },
            },
        ),
        _make_implementation("bounded_file_write"),
    )
    tool_registry.register(
        ToolDefinition(
            name="git_commit",
            description="test",
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            input_schema={
                "type": "object",
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
        ),
        _make_implementation("git_commit"),
    )
    tool_registry.register(
        ToolDefinition(
            name="git_add",
            description="test",
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        ),
        _make_implementation("git_add"),
    )
    tool_registry.register(
        ToolDefinition(
            name="restart_freyja_director",
            description="test",
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            input_schema={"type": "object", "properties": {}},
        ),
        _make_implementation("restart_freyja_director"),
    )
    return tool_registry


@pytest.mark.anyio
async def test_allowed_executable_list_only_git():
    assert _ALLOWED_EXECUTABLES == {"/usr/bin/git"}


@pytest.mark.anyio
async def test_command_templates_are_git_only():
    assert set(_COMMAND_TEMPLATES.keys()) == {"git_status", "git_add_single", "git_commit"}
    for template in _COMMAND_TEMPLATES.values():
        assert template[0] == "/usr/bin/git"


@pytest.mark.anyio
async def test_systemctl_not_allowed():
    assert "/usr/bin/systemctl" not in _ALLOWED_EXECUTABLES
    for template in _COMMAND_TEMPLATES.values():
        assert "/usr/bin/systemctl" not in template


@pytest.mark.anyio
async def test_generic_cat_ls_touch_templates_removed():
    assert "read_file" not in _COMMAND_TEMPLATES
    assert "list_directory" not in _COMMAND_TEMPLATES
    assert "disk_usage" not in _COMMAND_TEMPLATES
    assert "service_status" not in _COMMAND_TEMPLATES
    assert "service_restart" not in _COMMAND_TEMPLATES


@pytest.mark.anyio
async def test_bounded_file_write_requires_approval(backend):
    result = await backend.bounded_file_write("file.txt", "hello", approved=False)
    assert result["success"] is False
    assert "not explicitly approved" in result["error"]
    assert not (backend.allowed_root / "file.txt").exists()


@pytest.mark.anyio
async def test_bounded_file_write_creates_file_with_backup(backend):
    target = backend.allowed_root / "file.txt"
    target.write_text("original", encoding="utf-8")
    result = await backend.bounded_file_write("file.txt", "updated", approved=True)
    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "updated"
    backups = list(backend.allowed_root.glob("file.txt.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "original"


@pytest.mark.anyio
async def test_bounded_file_write_rejects_path_outside_root(backend, tmp_path):
    # Construct a path that is genuinely outside backend.allowed_root.
    outside = backend.allowed_root.parent / "outside.txt"
    outside.write_text("exists", encoding="utf-8")
    with pytest.raises(PathViolationError):
        await backend.bounded_file_write(str(outside), "x", approved=True)
    assert outside.read_text(encoding="utf-8") == "exists"
    # Also reject absolute path to a non-existent file outside root.
    outside_missing = backend.allowed_root.parent / "missing.txt"
    with pytest.raises(PathViolationError):
        await backend.bounded_file_write(str(outside_missing), "x", approved=True)
    assert not outside_missing.exists()


@pytest.mark.anyio
async def test_bounded_file_write_rejects_traversal_escape(backend):
    target = backend.allowed_root / "file.txt"
    target.write_text("safe", encoding="utf-8")
    with pytest.raises(PathViolationError):
        await backend.bounded_file_write("../outside.txt", "x", approved=True)
    assert target.read_text(encoding="utf-8") == "safe"


@pytest.mark.anyio
async def test_bounded_file_write_rejects_secret_path(backend):
    """Strengthened secret-path test.

    * The backend raises ``PathViolationError`` before touching the filesystem.
    * No file or directory is written.
    * The Tool Registry boundary returns a sanitized public error.
    """
    secret_path = "secrets/api.key"

    with mock.patch.object(backend, "bounded_file_write", wraps=backend.bounded_file_write) as wrapped:
        with pytest.raises(PathViolationError):
            await backend.bounded_file_write(secret_path, "leak", approved=True)

    # The wrapper confirms the method was called; the exception prevents any write.
    assert wrapped.called
    # No file or directory was created in the filesystem.
    assert not (backend.allowed_root / "secrets").exists()
    assert not (backend.allowed_root / secret_path).exists()


@pytest.mark.anyio
async def test_tool_registry_returns_sanitized_public_error_for_secret_path(registry):
    request = ToolExecutionRequest(
        tool_name="bounded_file_write",
        arguments={"path": "secrets/api.key", "content": "leak", "approved": True},
    )
    result = await registry.execute(request)
    assert result.success is False
    # The registry catches the backend PathViolationError and maps it to a
    # sanitized tool_error.
    assert result.error_code == "tool_error"
    assert result.public_error_message == "Tool execution failed."
    assert "PathViolationError" not in str(result.output)
    assert "secrets/api.key" not in str(result.output)


@pytest.mark.anyio
async def test_git_commit_rejects_outside_root(backend, tmp_path):
    # Construct a repo path that is genuinely outside backend.allowed_root.
    outside_repo = backend.allowed_root.parent / "other-repo"
    outside_repo.mkdir()
    with pytest.raises(PathViolationError):
        await backend.git_commit(str(outside_repo), "msg")
    # Also reject absolute path to a non-existent repo outside root.
    outside_missing = backend.allowed_root.parent / "missing-repo"
    with pytest.raises(PathViolationError):
        await backend.git_commit(str(outside_missing), "msg")


@pytest.mark.anyio
async def test_restart_freyja_director_uses_fixed_script(backend, tmp_path):
    """restart_freyja_director must invoke the fixed script with no extra arguments."""
    script = tmp_path / "freyja-os" / "scripts" / "restart-director.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\necho restarted\n", encoding="utf-8")
    script.chmod(0o755)

    with mock.patch(
        "freyja.tools.iris_maintenance._RESTART_DIRECTOR_SCRIPT",
        str(script),
    ):
        result = await backend.restart_freyja_director()

    assert result["success"] is True
    assert result["script"] == str(script)
    assert result["stdout_tail"].strip() == "restarted"
    assert result.get("returncode") == 0


@pytest.mark.anyio
async def test_restart_freyja_director_failure_when_script_missing(backend):
    with mock.patch(
        "freyja.tools.iris_maintenance._RESTART_DIRECTOR_SCRIPT",
        "/nonexistent/restart-director.sh",
    ):
        result = await backend.restart_freyja_director()
    assert result["success"] is False
    assert "Restart script not found" in result["error"]


@pytest.mark.anyio
async def test_register_smith_controlled_tools_only_exposes_fixed_tools():
    tool_registry = ToolRegistry()
    register_smith_controlled_tools(tool_registry)
    all_tools = tool_registry.list_tools(include_disabled=True)
    names = {tool.name for tool in all_tools}
    assert names == {"bounded_file_write", "git_add", "git_commit", "restart_freyja_director"}
    for tool in all_tools:
        assert tool.risk_level == ToolRiskLevel.CONTROLLED_WRITE


@pytest.mark.anyio
async def test_git_add_rejects_non_list_files(backend):
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    for bad in (None, [], "file.txt", 42, ["ok.txt", 123]):
        result = await backend.git_add(str(repo), bad)
        assert result["success"] is False, f"Expected failure for {bad!r}"


@pytest.mark.anyio
async def test_git_add_rejects_option_like_and_broad_directives(backend):
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    rejected = ["-f", "--force", "-u", "-A", "--all", ".", "--refresh", "--update", "--ignore-removal", ""]
    for raw in rejected:
        result = await backend.git_add(str(repo), [raw])
        assert result["success"] is False, f"Expected rejection for {raw!r}"
        assert "Rejected" in result["error"] or "non-empty" in result["error"]


@pytest.mark.anyio
async def test_git_add_rejects_wildcards(backend):
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    for wildcard in ["*.txt", "src/?.*", "[abc].py", "src/*.py"]:
        result = await backend.git_add(str(repo), [wildcard])
        assert result["success"] is False, f"Expected wildcard rejection for {wildcard!r}"
        assert "wildcard" in result["error"].lower()


@pytest.mark.anyio
async def test_git_add_rejects_path_escape_and_absolute(backend, tmp_path):
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    # Parent traversal.
    result = await backend.git_add(str(repo), ["../outside.txt"])
    assert result["success"] is False
    assert "outside the allowed root" in result["error"] or "parent references" in result["error"]

    # Absolute path outside the backend root.
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    result = await backend.git_add(str(repo), [str(outside)])
    assert result["success"] is False
    assert "outside" in result["error"].lower() or "forbidden" in result["error"].lower()


@pytest.mark.anyio
async def test_git_add_only_stages_approved_files(backend):
    """Only the requested, reviewed files are staged; others are untouched."""
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    (repo / "approved.txt").write_text("a", encoding="utf-8")
    (repo / "other.txt").write_text("b", encoding="utf-8")

    # Initialize git so status can be read.
    import subprocess as _subprocess

    _subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], check=True)
    _subprocess.run(["/usr/bin/git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    _subprocess.run(["/usr/bin/git", "-C", str(repo), "config", "user.name", "Test"], check=True)

    result = await backend.git_add(str(repo), ["approved.txt"])
    assert result["success"] is True, result.get("stderr_tail", result.get("error"))

    status = _subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "status", "--short"],
        capture_output=True,
        text=True,
        check=True,
    )
    entries = [line.strip() for line in status.stdout.splitlines() if line.strip()]
    staged = {line.split()[-1] for line in entries if line.startswith("A ") or line.startswith("M ")}
    unstaged = {line.split()[-1] for line in entries if line.startswith("?")}
    assert "approved.txt" in staged
    assert "other.txt" not in staged
    assert "other.txt" in unstaged


@pytest.mark.anyio
async def test_git_add_rejects_symlink_escape(backend):
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    outside = backend.allowed_root.parent / "escaped.txt"
    outside.write_text("secret", encoding="utf-8")
    link = repo / "link.txt"
    link.symlink_to(outside)
    result = await backend.git_add(str(repo), ["link.txt"])
    assert result["success"] is False
    assert "outside the allowed root" in result["error"]


@pytest.mark.anyio
async def test_git_add_rejects_secret_paths(backend):
    repo = backend.allowed_root / "repo"
    repo.mkdir()
    result = await backend.git_add(str(repo), [".env"])
    assert result["success"] is False
    assert "secret" in result["error"].lower()


@pytest.mark.anyio
async def test_git_add_tool_registry_returns_sanitized_public_error_for_bad_input(registry):
    request = ToolExecutionRequest(
        tool_name="git_add",
        arguments={"repo_path": ".", "files": ["-A"]},
    )
    result = await registry.execute(request)
    # Registry execution succeeded (ToolResult.success is True) but the tool
    # itself returned a sanitized failure dict in output.  The user-supplied
    # rejected value may appear in the tool-level error message, but internal
    # exception class names and filesystem paths must not leak.
    assert result.success is True
    assert result.output["success"] is False
    assert "PathViolationError" not in str(result.output)
    assert result.error_code is None
