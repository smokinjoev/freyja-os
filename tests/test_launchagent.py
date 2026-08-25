import os
import pathlib
import platform
import shutil
import plistlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLIST_SRC = REPO_ROOT / "scripts" / "com.freyja-os.director.plist"
LOG_DIR = REPO_ROOT / "logs"


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


def test_plist_starts_rev2_director_entrypoint() -> None:
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    args = data.get("ProgramArguments", [])
    assert "freyja.atlas_app:app" in args
    assert "freyja.roadmode_app:app" not in args


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
    install_root = pathlib.Path(data["WorkingDirectory"])
    assert pathlib.Path(env["PYTHONPATH"]) == install_root / "src"


def test_plist_stdout_stderr_point_to_logs() -> None:
    with open(PLIST_SRC, "rb") as f:
        data = plistlib.load(f)

    install_root = pathlib.Path(data["WorkingDirectory"])
    expected_log = install_root / "logs" / "director.log"
    assert pathlib.Path(data["StandardOutPath"]) == expected_log
    assert pathlib.Path(data["StandardErrorPath"]) == expected_log


@pytest.mark.skipif(platform.system() != "Darwin", reason="plutil is macOS-specific")
def test_plist_passes_lint() -> None:
    if shutil.which("plutil") is None:
        pytest.skip("plutil is not available")
    result = _run(["plutil", "-lint", str(PLIST_SRC)])
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_expected_paths_exist() -> None:
    uvicorn = REPO_ROOT / ".venv" / "bin" / "uvicorn"
    assert uvicorn.exists() or shutil.which("uvicorn") is not None
    assert (REPO_ROOT / "src" / "freyja" / "main.py").exists()
    assert (REPO_ROOT / "src" / "freyja" / "atlas_app.py").exists()
    assert (REPO_ROOT / "scripts" / "install-director.sh").exists()
    assert (REPO_ROOT / "scripts" / "status-director.sh").exists()
    assert (REPO_ROOT / "scripts" / "restart-director.sh").exists()
    assert (REPO_ROOT / "scripts" / "remove-director.sh").exists()


def test_director_status_script_checks_rev2_protected_health_without_printing_token() -> None:
    script = (REPO_ROOT / "scripts" / "status-director.sh").read_text(encoding="utf-8")

    assert "/providers/health" in script
    assert "/iris-router/health" in script
    assert "/macagent/health" in script
    assert "Authorization: Bearer ${FREYJA_CONNECTOR_TOKEN_VALUE}" in script
    assert 'echo "${FREYJA_CONNECTOR_TOKEN_VALUE}"' not in script


@pytest.mark.skipif(platform.system() != "Darwin", reason="LaunchAgent ownership checks are macOS-specific")
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
    if platform.system() != "Darwin" or shutil.which("launchctl") is None:
        return False
    # launchctl list from root cannot see gui-domain services; print can.
    uid = _get_freyja_uid()
    if not uid:
        return False
    result = _run(["launchctl", "print", f"gui/{uid}/com.freyja-os.director"], check=False)
    return result.returncode == 0 and "com.freyja-os.director" in result.stdout


def test_service_health_if_loaded() -> None:
    if not _service_is_loaded():
        pytest.skip("LaunchAgent is not currently loaded")

    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
            body = response.read().decode()
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, PermissionError):
            pytest.skip(f"Loopback health check blocked by test sandbox: {reason}")
        pytest.fail(f"Director health check failed: {exc}")
    except Exception as exc:
        pytest.fail(f"Director health check failed: {exc}")

    assert '"status":"healthy"' in body
