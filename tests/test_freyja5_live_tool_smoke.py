from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-live-tool-smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("freyja5_live_tool_smoke", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_live_tool_smoke_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111


def test_freyja5_live_tool_smoke_report_is_sanitized(monkeypatch) -> None:
    module = load_smoke_module()

    class RuntimeResult:
        trace_id = "trace-1"
        agent_id = "cloyd-gibbler"
        selected_tools = ("calendar.read",)
        tool_results = (
            {
                "capability_id": "calendar.read",
                "tool_name": "calendar_today_schedule",
                "success": True,
                "error_code": None,
                "public_error_message": None,
                "output": {"events": []},
            },
        )
        trace_summary = {
            "selected_tools": ["calendar.read"],
            "tool_calls": ["calendar.read"],
            "tool_boundaries": [{"tool_id": "calendar.read", "protocol": "mcp", "machine_affinity": "iris"}],
            "agent": "cloyd-gibbler",
            "machine": None,
            "egress_state": "local-only",
        }

    class Runtime:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, handoff):
            return RuntimeResult()

    monkeypatch.setattr(module, "AgentRuntimeV3", Runtime)

    report = module.run_smoke("Cloyd, use the calendar tool.")

    assert report["status"] == "passed"
    assert report["agent_id"] == "cloyd-gibbler"
    assert report["selected_tools"] == ["calendar.read"]
    assert report["tool_results"] == [
        {
            "capability_id": "calendar.read",
            "tool_name": "calendar_today_schedule",
            "success": True,
            "error_code": None,
            "public_error_message": None,
            "output_keys": ["events"],
        }
    ]
