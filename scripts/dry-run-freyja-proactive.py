#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(REPO_ROOT / "src"))

from freyja.proactive import DEFAULT_POLICY, ProactivePlanner


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "freyja-proactive-dry-run.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render Freyja proactive schedule dry-run dispatches without sending notifications.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = ProactivePlanner(args.policy).dry_run_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["all_sends_suppressed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
