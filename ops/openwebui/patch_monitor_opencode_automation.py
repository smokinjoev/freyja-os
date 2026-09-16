from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_AUTOMATIONS = Path("/app/backend/open_webui/utils/automations.py")

OLD_LINES_BLOCK = """        lines = [
            f"OpenCode monitor: {status.get('active_count', len(active))} active, {status.get('attention_count', len(review))} need attention.",
            f"Queue: running={queue.get('running', 0)}, queued={queue.get('queued', 0)}, review={queue.get('needs_review', 0)}, blocked={queue.get('blocked', 0)}, stale={queue.get('stale', 0)}.",
            "Live view: http://100.115.228.56:8000/agent-runs",
        ]
"""

PATCHED_LINES_BLOCK = """        supervisor = status.get('supervisor') or {}
        supervisor_payload = supervisor.get('payload') or {}
        supervisor_state = 'ok' if supervisor.get('ok') else 'needs attention'
        supervisor_detail = (
            f"Supervisor: {supervisor_state}, status={supervisor.get('status', 'unknown')}, "
            f"age={supervisor.get('age_seconds', 'unknown')}s, pid={supervisor_payload.get('pid', 'unknown')}."
        )
        lines = [
            f"OpenCode monitor: {status.get('active_count', len(active))} open, {status.get('attention_count', len(review))} need attention.",
            supervisor_detail,
            f"Queue: running={queue.get('running', 0)}, queued={queue.get('queued', 0)}, review={queue.get('needs_review', 0)}, blocked={queue.get('blocked', 0)}, stale={queue.get('stale', 0)}.",
            "Live view: http://100.115.228.56:8000/agent-runs",
        ]
"""


def patch_text(text: str) -> tuple[str, bool]:
    if PATCHED_LINES_BLOCK in text:
        return text, False
    if OLD_LINES_BLOCK not in text:
        raise ValueError("OpenWebUI automation status formatter anchor not found")
    return text.replace(OLD_LINES_BLOCK, PATCHED_LINES_BLOCK), True


def patch_file(path: Path) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    patched, changed = patch_text(original)
    if changed:
        path.write_text(patched, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "changed": changed,
        "has_supervisor_summary": "Supervisor:" in patched and "supervisor_payload" in patched,
        "uses_open_wording": "} open," in patched,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Patch OpenWebUI Monitor OpenCode automation fallback summary.")
    parser.add_argument("--automations", type=Path, default=DEFAULT_AUTOMATIONS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = patch_file(args.automations)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
