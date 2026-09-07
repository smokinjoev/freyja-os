#!/usr/bin/env python3
"""Run a read-only Freyja 5 delegated tool-session smoke."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from freyja.agent_gateway import AgentGateway, GatewayRequest  # noqa: E402
from freyja.agent_runtime_v3 import AgentRuntimeV3  # noqa: E402
from freyja.foundation_models import GatewaySender, SecurityDomainId  # noqa: E402
from freyja.tools.builtin import register_builtin_tools  # noqa: E402
from freyja.tools.registry import ToolRegistry  # noqa: E402


DEFAULT_OUTPUT = Path("certification/reports/freyja5-live-tool-smoke.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only Freyja 5 delegated tool-session smoke.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--prompt",
        default="Cloyd, use the calendar tool to read today's schedule for Freyja 5 live MCP validation.",
    )
    return parser


def run_smoke(prompt: str) -> dict[str, Any]:
    registry = ToolRegistry(default_timeout_seconds=35)
    register_builtin_tools(registry)
    gateway_result = AgentGateway().handle(
        GatewayRequest(
            sender=GatewaySender(
                sender_id="joe",
                display_name="Joe",
                channel="operator",
                authenticated=True,
                security_domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
            ),
            target_agent="cloyd",
            prompt=prompt,
            conversation_id="freyja5-live-tool-smoke",
            channel="operator",
            message_id="freyja5-live-tool-smoke-20260901",
            permissions=frozenset({"tool:calendar.read", "household:calendar.read"}),
            actor_principal="joe",
            authenticated_subject="joe",
            tool_policy="read-only-live-smoke",
            audit_reason="Freyja 5 live delegated tool-session validation",
        )
    )
    if gateway_result.handoff is None:
        raise RuntimeError("gateway did not return a handoff")
    result = AgentRuntimeV3(tool_registry=registry, run_inference=False).run(gateway_result.handoff)
    tool_results = [
        {
            "capability_id": item.get("capability_id"),
            "tool_name": item.get("tool_name"),
            "success": item.get("success"),
            "error_code": item.get("error_code"),
            "public_error_message": item.get("public_error_message"),
            "output_keys": sorted((item.get("output") or {}).keys()) if isinstance(item.get("output"), dict) else [],
        }
        for item in result.tool_results
    ]
    executed = [item for item in tool_results if item["success"] is True]
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-live-tool-smoke",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if executed else "failed",
        "trace_id": result.trace_id,
        "agent_id": result.agent_id,
        "selected_tools": list(result.selected_tools),
        "tool_results": tool_results,
        "trace_summary": {
            "selected_tools": result.trace_summary.get("selected_tools"),
            "tool_calls": result.trace_summary.get("tool_calls"),
            "tool_boundaries": result.trace_summary.get("tool_boundaries"),
            "agent": result.trace_summary.get("agent"),
            "machine": result.trace_summary.get("machine"),
            "egress_state": result.trace_summary.get("egress_state"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke(args.prompt)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
