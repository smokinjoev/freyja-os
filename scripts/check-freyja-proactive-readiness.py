#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freyja.proactive import DEFAULT_POLICY, ProactivePlanner


DEFAULT_OUTPUT = Path("certification/reports/freyja-proactive-readiness.json")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.replace(";", ",").split(",") if item.strip()}


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check disabled-by-default Freyja proactive schedule readiness.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--chat-stable", action="store_true")
    parser.add_argument("--recipients", default="")
    parser.add_argument("--destinations", default="")
    parser.add_argument("--approved-schedules", default="")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = ProactivePlanner(args.policy).readiness(
        chat_stable=args.chat_stable,
        recipients_verified=_csv_set(args.recipients),
        destinations_verified=_csv_set(args.destinations),
        approved_schedule_ids=_csv_set(args.approved_schedules),
    )
    report["git_head"] = _git_head()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
