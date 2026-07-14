import os
import pathlib
import plistlib
import subprocess

import pytest

PROJECT_DIR = pathlib.Path("/Users/freyja/freyja-os")
PLIST_SRC = PROJECT_DIR / "scripts" / "com.freyja-os.director.plist"
LOG_DIR = PROJECT_DIR / "logs"
EXPECTED_LOG = LOG_DIR / "director.log"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def test_plist_exists_and_has_expected_label() -> None:
    assert PLIST_SRC.exists(), f"Missing plist source: {PLIST_SRC}"
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    assert data["Label"] == "com.freyja-os.director"
    assert data["UserName"] == "freyja"


def test_plist_arguments_bind_localhost_only() -> None:
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    args = data.get("ProgramArguments", [])
    assert "127.0.0.1" in args, "Director must bind to 127.0.0.1"
    assert "8000" in args, "Director port must be 8000"


def test_plist_keepalive_restarts_on_unexpected_exit() -> None:
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    keep_alive = data.get("KeepAlive")
    assert isinstance(keep_alive, dict)
    assert keep_alive.get("SuccessfulExit") is False


def test_plist_sets_working_directory_and_pythonpath() -> None:
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    env = data.get("EnvironmentVariables", {})
    assert env.get("PYTHONPATH") == str(PROJECT_DIR / "src")
    assert data.get("WorkingDirectory") == str(PROJECT_DIR)


def test_plist_stdout_stderr_point_to_logs() -> None:
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    assert data.get("StandardOutPath") == str(EXPECTED_LOG)
    assert data.get("StandardErrorPath") == str(EXPECTED_LOG)


def test_plist_passes_lint() -> None:
    result = _run(["plutil", "-lint", str(PLIST_SRC)])
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_expected_paths_exist() -> None:
    assert (PROJECT_DIR / ".venv" / "bin" / "uvicorn").exists()
    assert (PROJECT_DIR / "src" / "freyja" / "main.py").exists()
    assert (PROJECT_DIR / "scripts" / "install-director.sh").exists()
    assert (PROJECT_DIR / "scripts" / "status-director.sh").exists()
    assert (PROJECT_DIR / "scripts" / "restart-director.sh").exists()
    assert (PROJECT_DIR / "scripts" / "remove-director.sh").exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="Ownership checks require root")
def test_project_files_owned_by_freyja_user() -> None:
    for path in [PLIST_SRC, LOG_DIR]:
        stat = os.stat(path)
        owner = _run(["id", "-un", str(stat.st_uid)]).stdout.strip()
        assert owner == "freyja", f"{path} is owned by {owner}, expected freyja"


def _get_freyja_uid() -> str:
    result = _run(["id", "-u", "freyja"], check=False)
    return result.stdout.strip()


def _service_is_loaded() -> bool:
    # launchctl list from root cannot see gui-domain services; print can.
    uid = _get_freyja_uid()
    if not uid:
        return False
    result = _run(["launchctl", "print", f"gui/{uid}/com.freyja-os.director"], check=False)
    return result.returncode == 0 and "com.freyja-os.director" in result.stdout


def test_service_health_if_loaded() -> None:
    if not _service_is_loaded():
        pytest.skip("LaunchAgent is not currently loaded")

    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
            body = response.read().decode()
    except Exception as exc:
        pytest.fail(f"Director health check failed: {exc}")

    assert '"status":"healthy"' in body
