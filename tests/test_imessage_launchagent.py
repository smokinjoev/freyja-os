from __future__ import annotations

import pathlib
import platform
import plistlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLIST_SRC = REPO_ROOT / "scripts" / "com.freyja-os.imessage-connector.plist"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-imessage-connector.sh"
STATUS_SCRIPT = REPO_ROOT / "scripts" / "status-imessage-connector.sh"
REMOVE_SCRIPT = REPO_ROOT / "scripts" / "remove-imessage-connector.sh"
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync-imessage-runtime.sh"
RUNTIME_MANIFEST = REPO_ROOT / "scripts" / "imessage-runtime-files.txt"
RUNTIME_ROOT = pathlib.Path("/Users/freyja/freyja-os-imessage-runtime")


def _load_plist() -> dict:
    with PLIST_SRC.open("rb") as handle:
        return plistlib.load(handle)


def test_imessage_plist_exists_and_has_expected_label() -> None:
    data = _load_plist()

    assert data["Label"] == "com.freyja-os.imessage-connector"
    assert "UserName" not in data


def test_imessage_plist_runs_runtime_connector() -> None:
    data = _load_plist()

    assert data["ProgramArguments"] == [
        str(RUNTIME_ROOT / ".venv" / "bin" / "python"),
        str(RUNTIME_ROOT / "scripts" / "run-imessage-connector.py"),
    ]
    assert pathlib.Path(data["WorkingDirectory"]) == RUNTIME_ROOT


def test_imessage_plist_sets_runtime_environment() -> None:
    data = _load_plist()
    env = data["EnvironmentVariables"]

    assert env["HOME"] == "/Users/freyja"
    assert env["USER"] == "freyja"
    assert env["LOGNAME"] == "freyja"
    assert str(RUNTIME_ROOT / "src") in env["PYTHONPATH"]
    assert str(RUNTIME_ROOT) in env["PYTHONPATH"]
    assert "/opt/homebrew/bin" in env["PATH"]


def test_imessage_plist_logs_to_runtime_log_file() -> None:
    data = _load_plist()
    expected_log = RUNTIME_ROOT / "logs" / "imessage-connector.log"

    assert pathlib.Path(data["StandardOutPath"]) == expected_log
    assert pathlib.Path(data["StandardErrorPath"]) == expected_log


def test_imessage_plist_restarts_on_unexpected_exit() -> None:
    data = _load_plist()

    assert data["RunAtLoad"] is True
    assert data["KeepAlive"]["SuccessfulExit"] is False
    assert data["ThrottleInterval"] == 10
    assert data["LimitLoadToSessionType"] == "Aqua"


@pytest.mark.skipif(platform.system() != "Darwin", reason="plutil is macOS-specific")
def test_imessage_plist_passes_lint() -> None:
    if shutil.which("plutil") is None:
        pytest.skip("plutil is not available")

    result = subprocess.run(
        ["plutil", "-lint", str(PLIST_SRC)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "OK" in result.stdout


def test_imessage_launchagent_scripts_exist() -> None:
    assert INSTALL_SCRIPT.exists()
    assert STATUS_SCRIPT.exists()
    assert REMOVE_SCRIPT.exists()
    assert SYNC_SCRIPT.exists()
    assert RUNTIME_MANIFEST.exists()


def test_imessage_runtime_manifest_lists_required_files() -> None:
    manifest = RUNTIME_MANIFEST.read_text()

    assert "connectors/imessage/gateway.py" in manifest
    assert "connectors/messaging.py" in manifest
    assert "src/freyja/agents/coding_lane.py" in manifest
    assert "src/freyja/inference.py" in manifest
    assert "src/freyja/media.py" in manifest
    assert "src/freyja/router.py" in manifest
    assert "scripts/run-imessage-connector.py" in manifest
    assert "scripts/com.freyja-os.imessage-connector.plist" in manifest


def test_imessage_status_reports_runtime_source_drift() -> None:
    status_source = STATUS_SCRIPT.read_text()

    assert "=== Runtime source drift ===" in status_source
    assert "=== Runtime import check ===" in status_source
    assert "check_runtime_imports" in status_source
    assert "freyja.router" in status_source
    assert "connectors.imessage.gateway" in status_source
    assert "imessage-runtime-files.txt" in status_source
    assert "DRIFT_PATHS=()" in status_source
    assert "while IFS= read -r REL_PATH" in status_source
    assert "cmp -s" in status_source
    assert "scripts/sync-imessage-runtime.sh" in status_source
    assert "--fail-on-drift" in status_source
    assert 'exit 1' in status_source


def test_imessage_sync_script_copies_runtime_critical_files_and_restarts() -> None:
    sync_source = SYNC_SCRIPT.read_text()

    assert "imessage-runtime-files.txt" in sync_source
    assert "BACKUP_DIR" in sync_source
    assert "restore_runtime_backup" in sync_source
    assert "backup_runtime_file" in sync_source
    assert "trap 'restore_runtime_backup' ERR" in sync_source
    assert "Verifying runtime imports" in sync_source
    assert "check_runtime_imports" in sync_source
    assert "freyja.router" in sync_source
    assert "connectors.imessage.gateway" in sync_source
    assert "SYNC_PATHS=()" in sync_source
    assert "while IFS= read -r REL_PATH" in sync_source
    assert 'rsync "${RSYNC_FLAGS[@]}" "${SRC}" "${DST}"' in sync_source
    assert '"${PROJECT_DIR}/scripts/install-imessage-connector.sh"' in sync_source
    assert '"${CHECKOUT_DIR}/scripts/status-imessage-connector.sh" --fail-on-drift' in sync_source


def test_imessage_sync_rolls_back_before_restart_on_import_failure() -> None:
    sync_source = SYNC_SCRIPT.read_text()

    assert "if ! check_runtime_imports; then" in sync_source
    assert "restore_runtime_backup" in sync_source
    assert "exit 1" in sync_source
    restart_index = sync_source.rindex('"${PROJECT_DIR}/scripts/install-imessage-connector.sh"')
    assert sync_source.index("if ! check_runtime_imports; then") < restart_index
    assert "SYNC_COMMITTED=1" in sync_source


def test_imessage_sync_script_supports_dry_run_without_restart() -> None:
    sync_source = SYNC_SCRIPT.read_text()

    assert "--dry-run" in sync_source
    assert "--no-restart" in sync_source
    assert "would sync" in sync_source
    assert "Dry run complete; runtime was not modified." in sync_source
