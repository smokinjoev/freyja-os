from __future__ import annotations

import pathlib
import platform
import plistlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLIST_SRC = REPO_ROOT / "scripts" / "com.freyja-os.gmail-connector.plist"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-gmail-connector.sh"
STATUS_SCRIPT = REPO_ROOT / "scripts" / "status-gmail-connector.sh"
RUN_SCRIPT = REPO_ROOT / "scripts" / "run-gmail-connector.py"


def _load_plist() -> dict:
    with PLIST_SRC.open("rb") as handle:
        return plistlib.load(handle)


def test_gmail_plist_exists_and_has_expected_label() -> None:
    data = _load_plist()

    assert data["Label"] == "com.freyja-os.gmail-connector"
    assert "UserName" not in data


def test_gmail_plist_runs_connector_from_main_checkout() -> None:
    data = _load_plist()

    assert data["ProgramArguments"] == [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(REPO_ROOT / "scripts" / "run-gmail-connector.py"),
    ]
    assert pathlib.Path(data["WorkingDirectory"]) == REPO_ROOT


def test_gmail_plist_sets_environment() -> None:
    data = _load_plist()
    env = data["EnvironmentVariables"]

    assert env["HOME"] == "/Users/freyja"
    assert env["USER"] == "freyja"
    assert env["LOGNAME"] == "freyja"
    assert str(REPO_ROOT / "src") in env["PYTHONPATH"]
    assert str(REPO_ROOT) in env["PYTHONPATH"]
    assert "/opt/homebrew/bin" in env["PATH"]


def test_gmail_plist_logs_to_connector_log_file() -> None:
    data = _load_plist()
    expected_log = REPO_ROOT / "logs" / "gmail-connector.log"

    assert pathlib.Path(data["StandardOutPath"]) == expected_log
    assert pathlib.Path(data["StandardErrorPath"]) == expected_log


def test_gmail_plist_restarts_on_unexpected_exit() -> None:
    data = _load_plist()

    assert data["RunAtLoad"] is True
    assert data["KeepAlive"]["SuccessfulExit"] is False
    assert data["ThrottleInterval"] == 10
    assert data["LimitLoadToSessionType"] == "Aqua"


@pytest.mark.skipif(platform.system() != "Darwin", reason="plutil is macOS-specific")
def test_gmail_plist_passes_lint() -> None:
    if shutil.which("plutil") is None:
        pytest.skip("plutil is not available")

    result = subprocess.run(
        ["plutil", "-lint", str(PLIST_SRC)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "OK" in result.stdout


def test_gmail_launchagent_scripts_exist() -> None:
    assert INSTALL_SCRIPT.exists()
    assert STATUS_SCRIPT.exists()
    assert RUN_SCRIPT.exists()
