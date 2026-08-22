import pytest

from freyja.agents.coder_access import CloydCoderRuntime, CoderAccessPolicy


def test_cloyd_has_local_coder_modules() -> None:
    policy = CoderAccessPolicy()

    for tool_name in (
        "repository_status",
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
async def test_runtime_denies_unapproved_write_before_tool_lookup() -> None:
    result = await CloydCoderRuntime().execute(
        tool_name="write_pilot_file_write",
        arguments={"target_path": "README.md", "content": "changed"},
    )

    assert result.success is False
    assert result.error_code == "approval_required"
