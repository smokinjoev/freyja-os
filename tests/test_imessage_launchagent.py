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
