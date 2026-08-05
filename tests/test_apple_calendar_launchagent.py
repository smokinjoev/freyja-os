from pathlib import Path
import plistlib


ROOT = Path(__file__).resolve().parents[1]


def test_calendar_launchagent_is_user_scoped_and_does_not_embed_token() -> None:
    payload = plistlib.loads((ROOT / "scripts/com.freyja-os.apple-calendar.plist").read_bytes())
    assert payload["Label"] == "com.freyja-os.apple-calendar"
    assert payload["ProgramArguments"] == ["/Users/freyja/freyja-os/scripts/run-apple-calendar-bridge.sh"]
    assert "FREYJA_APPLE_CALENDAR_TOKEN" not in str(payload)


def test_installer_protects_generated_token_file() -> None:
    script = (ROOT / "scripts/install-apple-calendar-bridge.sh").read_text()
    assert "openssl rand -hex 32" in script
    assert 'chmod 600 "${CONFIG_FILE}"' in script
    assert "sudo" not in script


def test_bridge_runner_sets_project_pythonpath() -> None:
    script = (ROOT / "scripts/run-apple-calendar-bridge.sh").read_text()
    assert 'export PYTHONPATH="${PROJECT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"' in script
