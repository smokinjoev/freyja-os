#!/usr/bin/env python3
"""Summarize the latest Freyja Rev 2 readiness report."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from certification.rev2_preflight_status import main


if __name__ == "__main__":
    raise SystemExit(main())
