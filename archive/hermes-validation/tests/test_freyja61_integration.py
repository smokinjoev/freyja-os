from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("freyja61_integration_audit", ROOT / "scripts" / "freyja61-integration-audit.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_freyja61_integration_contract_is_safe_and_complete() -> None:
    report = MODULE.audit()
    assert report["ok"], report["failures"]
    assert report["checked"] == {"endpoints": 12, "roles": 3, "activation_stages": 4}
