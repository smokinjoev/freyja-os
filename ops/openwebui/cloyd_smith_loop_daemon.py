#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json


DEPRECATION_MESSAGE = (
    "The OpenWebUI container JSON-ledger Cloyd-Smith daemon is deprecated. "
    "Use the local SQLite supervisor at scripts/cloyd-smith-loop-daemon.py."
)


def run_once() -> list[dict[str, str]]:
    return [
        {
            "ok": "false",
            "status": "deprecated",
            "next_action": "run local SQLite supervisor",
            "message": DEPRECATION_MESSAGE,
        }
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Deprecated OpenWebUI JSON-ledger Cloyd-Smith daemon.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.parse_args()
    print(json.dumps(run_once(), indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
