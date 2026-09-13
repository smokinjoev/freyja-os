from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "freyja-opencode-control.py"


def _module():
    spec = importlib.util.spec_from_file_location("freyja_opencode_control", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_alias_accepts_legacy_string_entries(tmp_path: Path) -> None:
    module = _module()
    module.STATE_FILE = tmp_path / "controller-sessions.json"
    module.STATE_FILE.write_text(json.dumps({"coder": "ses_abc"}), encoding="utf-8")

    assert module._session("coder") == {"session": "ses_abc"}


def test_session_alias_preserves_remote_connection_details(tmp_path: Path) -> None:
    module = _module()
    module.STATE_FILE = tmp_path / "controller-sessions.json"
    module.STATE_FILE.write_text(
        json.dumps(
            {
                "atlas-dashboard": {
                    "base_url": "http://100.119.235.114:4097",
                    "session": "ses_remote",
                    "username": "joe",
                }
            }
        ),
        encoding="utf-8",
    )

    assert module._session("atlas-dashboard") == {
        "base_url": "http://100.119.235.114:4097",
        "session": "ses_remote",
        "username": "joe",
    }
