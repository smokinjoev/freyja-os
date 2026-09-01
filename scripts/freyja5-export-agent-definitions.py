#!/usr/bin/env python3
"""Export non-secret Freyja 5 agent definitions from source control."""

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

from freyja.freyja5_config import (  # noqa: E402
    freyja5_agent_evidence,
    freyja5_gateway_evidence,
    freyja5_mcp_topology_evidence,
    freyja5_semantic_route_evidence,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export source-controlled Freyja 5 agent definitions.")
    parser.add_argument("--output", type=Path, help="Write the export JSON to this path.")
    return parser


def build_export() -> dict[str, Any]:
    mcp = freyja5_mcp_topology_evidence()
    return {
        "schema_version": "1.0",
        "export_type": "freyja5-agent-definitions",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_controlled": True,
        "secrets_included": False,
        "opaque_product_database": False,
        "intended_import_boundary": "atlas-persistent-agent-plane",
        "agents": freyja5_agent_evidence(),
        "semantic_routes": freyja5_semantic_route_evidence(),
        "mcp": {
            "default_agent_mcp_servers": mcp["default_agent_mcp_servers"],
            "servers": mcp["servers"],
            "agent_consumption": mcp["agent_consumption"],
            "agent_grants": mcp["agent_grants"],
        },
        "gateway_policy": freyja5_gateway_evidence()["policy"],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rendered = json.dumps(build_export(), indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
