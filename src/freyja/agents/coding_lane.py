from __future__ import annotations

from dataclasses import dataclass

READ_ONLY_CODER_TOOLS = (
    "repository_status",
    "get_current_commit",
    "repository_diff_summary",
    "run_test_suite",
    "compile_project",
    "validate_diff",
)

WRITE_CODER_TOOLS = (
    "bounded_file_write",
    "git_add",
    "git_commit",
    "write_pilot_file_write",
    "write_pilot_git_add",
    "write_pilot_git_commit",
)


@dataclass(frozen=True)
class CodingLaneContract:
    orchestrator_model: str
    worker_model: str
    agent_id: str = "cloyd-gibbler"
    worker_name: str = "Agent Smith/Qwen coder"


def render_coding_lane_contract(contract: CodingLaneContract) -> str:
    """Render the deterministic coding handoff contract for Vulcan."""
    read_tools = ", ".join(READ_ONLY_CODER_TOOLS)
    write_tools = ", ".join(WRITE_CODER_TOOLS)
    return (
        "BEGIN AGENT SMITH QWEN CODING LANE\n"
        f"Orchestrator: Vulcan/local_reasoning ({contract.orchestrator_model}).\n"
        f"Worker target: {contract.worker_name} ({contract.worker_model}), agent_id={contract.agent_id}.\n"
        "Contract: Vulcan owns reasoning, planning, and final review. "
        "For repository work, Vulcan must emit bounded worker actions for the Smith/Qwen lane instead of "
        "answering that coding is unavailable.\n"
        "Worker action format: emit a fenced json block labelled smith_qwen_action with keys "
        "tool_name, arguments, approval_required, expected_result, and validation_command. "
        "Use one action per block. Set approval_required=true for any write, stage, commit, or file mutation.\n"
        f"Read-only worker tools: {read_tools}.\n"
        f"Write/commit worker tools requiring explicit approval: {write_tools}.\n"
        "Do not invent shell access. Do not use generic command execution. Do not claim inability merely "
        "because the request is coding-related. If no repository action is needed, return the final corrected "
        "artifact directly.\n"
        "END AGENT SMITH QWEN CODING LANE"
    )
