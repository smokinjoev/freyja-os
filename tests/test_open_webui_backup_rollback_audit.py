from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit-open-webui-backup-rollback.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_open_webui_backup_rollback", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _runbook(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "docker compose --env-file deploy/compose/open-webui/.env",
                "git apply .codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch",
                "open-webui-data-volume.tgz",
                "tar -xzf",
                "http://127.0.0.1:3001/api/version",
            ]
        ),
        encoding="utf-8",
    )


def test_backup_rollback_audit_accepts_readable_open_webui_archive(tmp_path: Path) -> None:
    backup = tmp_path / "open-webui-data-volume.tgz"
    runbook = tmp_path / "runbook.md"
    _tar(backup, {"webui.db": b"sqlite-ish", "config.json": b"{}"})
    _runbook(runbook)

    report = _module().build_report(backup, runbook)

    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["backup"]["contains_webui_db"] is True
    assert report["backup"]["tar_gzip_readable"] is True
    assert report["backup"]["member_count"] == 2
    assert report["backup_scope"]["report_sanitized"] is True
    assert report["backup_scope"]["archive_may_contain_private_content"] is False
    assert report["backup_scope"]["archive_handling"] == "treat_as_sensitive_do_not_commit_or_print_contents"
    assert len(report["backup"]["sha256"]) == 64
    assert "sqlite-ish" not in json.dumps(report)
    steps = report["rollback_documentation"]["steps"]
    assert [step["step"] for step in steps] == [
        "stop_open_webui",
        "restore_source_checkpoint",
        "restore_open_webui_volume",
        "start_open_webui",
        "verify_open_webui",
    ]
    assert steps[0]["command"].startswith("docker compose --env-file deploy/compose/open-webui/.env")
    assert "open-webui-data-volume.tgz" in steps[2]["command"]
    assert steps[-1]["command"] == "curl -fsS --max-time 10 http://127.0.0.1:3001/api/version"
    assert "TOKEN" not in json.dumps(steps)
    assert "PASSWORD" not in json.dumps(steps)


def test_backup_rollback_audit_rejects_missing_rollback_step(tmp_path: Path) -> None:
    backup = tmp_path / "open-webui-data-volume.tgz"
    runbook = tmp_path / "runbook.md"
    _tar(backup, {"webui.db": b"sqlite-ish"})
    runbook.write_text("open-webui-data-volume.tgz", encoding="utf-8")

    report = _module().build_report(backup, runbook)

    assert report["ok"] is False
    assert report["rollback_documentation"]["missing_required_phrases"]
    assert report["rollback_documentation"]["steps"]


def test_backup_rollback_audit_marks_archives_with_upload_or_cache_content_sensitive(tmp_path: Path) -> None:
    backup = tmp_path / "open-webui-data-volume.tgz"
    runbook = tmp_path / "runbook.md"
    _tar(backup, {"webui.db": b"sqlite-ish", "uploads/document.pdf": b"private-ish"})
    _runbook(runbook)

    report = _module().build_report(backup, runbook)

    assert report["ok"] is True
    assert report["private_content_included"] is False
    assert report["backup"]["contains_upload_or_cache_dirs"] is True
    assert report["backup_scope"]["archive_may_contain_private_content"] is True
    assert report["backup_scope"]["archive_contains_user_uploaded_or_vector_content"] is True
    assert "private-ish" not in json.dumps(report)


def test_backup_rollback_audit_writes_report(tmp_path: Path, capsys) -> None:
    backup = tmp_path / "open-webui-data-volume.tgz"
    runbook = tmp_path / "runbook.md"
    output = tmp_path / "audit.json"
    _tar(backup, {"webui.db": b"sqlite-ish"})
    _runbook(runbook)

    assert _module().main(["--backup", str(backup), "--runbook", str(runbook), "--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-backup-rollback-audit"
    assert isinstance(written["generated_at_unix"], int)
    assert written["git_head"]
