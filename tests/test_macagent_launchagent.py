from __future__ import annotations

import pathlib
import platform
import plistlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLIST_SRC = REPO_ROOT / "scripts" / "com.freyja-os.macagent.plist"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-macagent.sh"
STATUS_SCRIPT = REPO_ROOT / "scripts" / "status-macagent.sh"
RESTART_SCRIPT = REPO_ROOT / "scripts" / "restart-macagent.sh"
REMOVE_SCRIPT = REPO_ROOT / "scripts" / "remove-macagent.sh"


def _load_plist() -> dict:
    with PLIST_SRC.open("rb") as handle:
        return plistlib.load(handle)


def test_macagent_plist_exists_and_has_expected_label() -> None:
    data = _load_plist()

    assert data["Label"] == "com.freyja-os.macagent"


def test_macagent_plist_runs_macagent_script() -> None:
    data = _load_plist()

    assert data["ProgramArguments"] == [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(REPO_ROOT / "scripts" / "run-macagent.py"),
    ]
    assert pathlib.Path(data["WorkingDirectory"]) == REPO_ROOT


def test_macagent_plist_sets_environment() -> None:
    data = _load_plist()
    env = data["EnvironmentVariables"]

    assert env["HOME"] == "/Users/freyja"
    assert env["USER"] == "freyja"
    assert env["LOGNAME"] == "freyja"
    assert env["PYTHONPATH"] == f"{REPO_ROOT / 'src'}:{REPO_ROOT}"
    assert "/opt/homebrew/bin" in env["PATH"]


def test_macagent_plist_logs_to_runtime_log_file() -> None:
    data = _load_plist()
    expected_log = REPO_ROOT / "logs" / "macagent.log"

    assert pathlib.Path(data["StandardOutPath"]) == expected_log
    assert pathlib.Path(data["StandardErrorPath"]) == expected_log


def test_macagent_plist_restarts_on_unexpected_exit() -> None:
    data = _load_plist()

    assert data["RunAtLoad"] is True
    assert data["KeepAlive"]["SuccessfulExit"] is False
    assert data["ThrottleInterval"] == 10
    assert data["ProcessType"] == "Background"


@pytest.mark.skipif(platform.system() != "Darwin", reason="plutil is macOS-specific")
def test_macagent_plist_passes_lint() -> None:
    if shutil.which("plutil") is None:
        pytest.skip("plutil is not available")

    result = subprocess.run(
        ["plutil", "-lint", str(PLIST_SRC)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "OK" in result.stdout


def test_macagent_launchagent_scripts_exist() -> None:
    assert INSTALL_SCRIPT.exists()
    assert STATUS_SCRIPT.exists()
    assert RESTART_SCRIPT.exists()
    assert REMOVE_SCRIPT.exists()


def test_macagent_install_requires_runtime_token() -> None:
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "MACAGENT_TOKEN must be set" in script
    assert "grep -Eq '^MACAGENT_TOKEN=.+$'" in script


def test_macagent_runner_reexecs_into_project_virtualenv() -> None:
    script = (REPO_ROOT / "scripts" / "run-macagent.py").read_text(encoding="utf-8")

    assert '".venv" / "bin" / "python"' in script
    assert "os.execv(str(venv_python)" in script
    assert "root_path = str(repo_root)" in script
    assert "import uvicorn" in script


def test_macagent_status_script_checks_authenticated_health_without_printing_token() -> None:
    script = STATUS_SCRIPT.read_text(encoding="utf-8")

    assert "Authorization: Bearer ${MACAGENT_TOKEN_VALUE}" in script
    assert "/health" in script
    assert "MacAgent authenticated health: OK" in script
    assert 'echo "${MACAGENT_TOKEN_VALUE}"' not in script
    assert "token is not configured" in script
