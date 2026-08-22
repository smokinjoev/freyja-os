import subprocess

import pytest

from freyja.agents.coder_access import CloydCoderRuntime, CoderAccessPolicy, is_coding_request
from freyja.config import settings


def test_cloyd_has_local_coder_modules() -> None:
    policy = CoderAccessPolicy()

    for tool_name in (
        "repository_status",
        "get_current_commit",
        "repository_diff_summary",
        "run_test_suite",
        "compile_project",
        "validate_diff",
    ):
        decision = policy.authorize(agent_id="cloyd-gibbler", tool_name=tool_name)
        assert decision.allowed is True
        assert decision.approval_required is False


def test_cloyd_write_modules_require_explicit_approval() -> None:
    policy = CoderAccessPolicy()

    for tool_name in (
        "bounded_file_write",
        "git_add",
        "git_commit",
        "write_pilot_file_write",
        "write_pilot_git_add",
        "write_pilot_git_commit",
    ):
        denied = policy.authorize(agent_id="cloyd-gibbler", tool_name=tool_name)
        allowed = policy.authorize(
            agent_id="cloyd-gibbler",
            tool_name=tool_name,
            approval_granted=True,
        )
        assert denied.allowed is False
        assert denied.approval_required is True
        assert allowed.allowed is True


def test_other_personal_agents_do_not_inherit_cloyd_coder_access() -> None:
    policy = CoderAccessPolicy()

    assert policy.authorize(
        agent_id="benedict",
        tool_name="run_test_suite",
    ).allowed is False
    assert policy.authorize(
        agent_id="agent-44",
        tool_name="repository_status",
    ).allowed is False
    assert policy.authorize(
        agent_id="freyja",
        tool_name="write_pilot_file_write",
        approval_granted=True,
    ).allowed is False


def test_generic_shell_is_not_a_coder_module() -> None:
    decision = CoderAccessPolicy().authorize(
        agent_id="cloyd-gibbler",
        tool_name="shell",
        approval_granted=True,
    )

    assert decision.allowed is False
    assert decision.reason == "tool is not a coder module"


@pytest.mark.asyncio
async def test_runtime_can_read_current_commit() -> None:
    result = await CloydCoderRuntime().execute(
        tool_name="get_current_commit",
        request_id="cloyd-commit",
    )

    assert result.success is True
    assert result.output.get("commit")


@pytest.mark.asyncio
async def test_current_commit_uses_configured_repository_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    monkeypatch.setattr(settings, "repository_root", str(repo))

    result = await CloydCoderRuntime().execute(
        tool_name="get_current_commit",
        request_id="cloyd-configured-root",
    )

    assert result.success is True
    assert result.output["git_available"] is True
    assert result.output["repository_root"] == str(repo.resolve())
    assert result.output["commit"]


@pytest.mark.asyncio
async def test_runtime_denies_unapproved_write_before_tool_lookup() -> None:
    result = await CloydCoderRuntime().execute(
        tool_name="write_pilot_file_write",
        arguments={"target_path": "README.md", "content": "changed"},
    )

    assert result.success is False
    assert result.error_code == "approval_required"


def test_coding_request_detection_is_conservative() -> None:
    assert is_coding_request("Cloyd, fix this test") is True
    assert is_coding_request("Run pytest and review the diff") is True
    assert is_coding_request("code: implement the router") is True
    assert is_coding_request("How was your day?") is False
    assert is_coding_request("Write Beth a reminder") is False
