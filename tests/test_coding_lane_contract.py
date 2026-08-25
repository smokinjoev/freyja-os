from freyja.agents.coding_lane import CodingLaneContract, render_coding_lane_contract


def test_coding_lane_contract_names_vulcan_and_qwen_worker() -> None:
    rendered = render_coding_lane_contract(
        CodingLaneContract(
            orchestrator_model="gpt-oss-freyja:20b-analysis-prefill",
            worker_model="qwen2.5-coder:14b-q3",
        )
    )

    assert "BEGIN AGENT SMITH QWEN CODING LANE" in rendered
    assert "Vulcan/local_reasoning (gpt-oss-freyja:20b-analysis-prefill)" in rendered
    assert "Agent Smith/Qwen coder (qwen2.5-coder:14b-q3)" in rendered
    assert "agent_id=cloyd-gibbler" in rendered


def test_coding_lane_contract_requires_bounded_actions_and_approval_for_writes() -> None:
    rendered = render_coding_lane_contract(
        CodingLaneContract(orchestrator_model="vulcan", worker_model="qwen-coder")
    )

    assert "smith_qwen_action" in rendered
    assert "tool_name, arguments, approval_required, expected_result, and validation_command" in rendered
    assert "repository_status" in rendered
    assert "run_test_suite" in rendered
    assert "write_pilot_file_write" in rendered
    assert "requiring explicit approval" in rendered
    assert "Do not invent shell access" in rendered
    assert "Do not use generic command execution" in rendered
