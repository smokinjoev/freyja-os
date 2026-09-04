from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "refresh-open-webui-home-agent-evidence.py"


def _module():
    spec = importlib.util.spec_from_file_location("refresh_open_webui_home_agent_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_report_sequences_credential_free_evidence(monkeypatch, tmp_path: Path) -> None:
    module = _module()
    calls: list[tuple[list[str], set[int], Path | None]] = []
    snapshot = tmp_path / "webui.db"
    snapshot.write_text("", encoding="utf-8")

    monkeypatch.setattr(module, "_snapshot_open_webui_database", lambda container, target_dir: snapshot)

    def fake_run(args, *, allowed_returncodes=None, stdout_path=None):
        allowed = allowed_returncodes or {0}
        calls.append((args, allowed, stdout_path))
        return {
            "command": " ".join(args),
            "returncode": 1 if "summarize-open-webui-home-agent-readiness.py" in args else 0,
            "ok": 1 in allowed if "summarize-open-webui-home-agent-readiness.py" in args else True,
            "allowed_returncodes": sorted(allowed),
            "elapsed_seconds": 0.001,
            "stdout_path": str(stdout_path) if stdout_path else None,
            "stderr_present": False,
        }

    monkeypatch.setattr(module, "_run", fake_run)

    report = module.refresh("open-webui")

    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["failed_steps"] == []
    commands = [" ".join(call[0]) for call in calls]
    assert any("check-open-webui-model-proxy-catalog.py" in command for command in commands)
    assert any("count-open-webui-home-resources-live.py" in command for command in commands)
    assert any("audit-open-webui-home-agent-access.py" in command for command in commands)
    assert any(call[1] == {0, 1} and any("summarize-open-webui-home-agent-readiness.py" in part for part in call[0]) for call in calls)
    assert any(call[2] and call[2].name == "open-webui-home-agents-offline-apply.json" for call in calls)


def test_refresh_report_fails_when_snapshot_and_step_fail(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_snapshot_open_webui_database", lambda container, target_dir: None)
    monkeypatch.setattr(
        module,
        "_run",
        lambda args, **kwargs: {
            "command": " ".join(args),
            "returncode": 2,
            "ok": False,
            "allowed_returncodes": [0],
            "elapsed_seconds": 0.001,
            "stdout_path": None,
            "stderr_present": False,
        },
    )

    report = module.refresh("open-webui")

    assert report["ok"] is False
    assert report["failed_steps"]
    assert report["failed_steps"][0]["step"] == "snapshot_open_webui_database"


def test_refresh_main_writes_report(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _module()
    output = tmp_path / "refresh.json"
    monkeypatch.setattr(
        module,
        "refresh",
        lambda container: {
            "report_type": "open-webui-home-agent-evidence-refresh",
            "generated_at_unix": 1,
            "git_head": "test-head",
            "secrets_included": False,
            "private_content_included": False,
            "step_count": 1,
            "failed_steps": [],
            "ok": True,
            "steps": [{"ok": True}],
        },
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda args, **kwargs: {
            "command": " ".join(args),
            "returncode": 0,
            "ok": True,
            "allowed_returncodes": [0],
            "elapsed_seconds": 0.001,
            "stdout_path": None,
            "stderr_present": False,
        },
    )

    assert module.main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-agent-evidence-refresh"
    assert written["post_refresh_bundle"]["ok"] is True
