from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-completion-audit.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location("freyja5_completion_audit", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_bundle(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "freyja5-readiness-bundle",
                "passed": False,
                "source_ready": True,
                "live_blocked": True,
                "checks": [],
            }
        ),
        encoding="utf-8",
    )


def test_freyja5_completion_audit_maps_requirements_to_current_evidence(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    bundle = tmp_path / "freyja5-readiness-bundle.json"
    agent_export = tmp_path / "freyja5-agent-definitions.json"
    _write_bundle(bundle)
    agent_export.write_text(
        json.dumps({"export_type": "freyja5-agent-definitions", "source_controlled": True, "secrets_included": False}),
        encoding="utf-8",
    )

    audit = audit_module.build_audit(readiness_bundle=bundle, agent_export=agent_export)
    requirements = {requirement["id"]: requirement for requirement in audit["requirements"]}

    assert audit["status"] == "source-ready-live-blocked"
    assert audit["source_ready"] is True
    assert audit["live_blocked"] is True
    assert audit["agent_export"] == {"path": str(agent_export), "ok": True, "status": "valid"}
    assert audit["certification"]["targets"] == ["A", "B", "C", "D", "E", "F", "G"]
    assert requirements["fallback-preserved"]["status"] == "complete"
    assert requirements["webgui-side-by-side"]["status"] == "complete"
    assert requirements["gateway-boundary"]["status"] == "complete"
    assert requirements["semantic-routes"]["status"] == "complete"
    assert requirements["persistent-agents"]["status"] == "complete"
    assert requirements["mcp-boundaries"]["status"] == "complete"
    assert requirements["traceability"]["status"] == "complete"
    assert requirements["certification-targets-a-g"]["status"] == "partial"
    assert requirements["vulcan-live-nexus"]["status"] == "blocked"
    assert requirements["atlas-msty-go"]["blockers"] == ["msty_go_always_on_linux_validation"]
    assert requirements["iris-live-apple-mcp"]["blockers"] == ["iris_apple_session"]
    assert requirements["hera-live-voice-avatar"]["blockers"] == ["hera_voice_avatar_hardware"]


def test_freyja5_completion_audit_cli_writes_json(tmp_path: Path, capsys) -> None:
    audit_module = load_audit_module()
    bundle = tmp_path / "freyja5-readiness-bundle.json"
    output = tmp_path / "freyja5-completion-audit.json"
    _write_bundle(bundle)

    assert audit_module.main(["--readiness-bundle", str(bundle), "--agent-export", str(tmp_path / "missing.json"), "--output", str(output)]) == 2

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert printed["report_type"] == "freyja5-completion-audit"
    assert written["requirements"] == printed["requirements"]
    assert written["agent_export"]["status"] == "missing"


def test_freyja5_completion_audit_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111
