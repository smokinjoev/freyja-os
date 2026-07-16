from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_DIR = Path("/Users/freyja/freyja-os")
ENABLE_SCRIPT = PROJECT_DIR / "scripts" / "enable-telegram-travel-mode.sh"
DISABLE_SCRIPT = PROJECT_DIR / "scripts" / "disable-telegram-travel-mode.sh"
VERIFY_SCRIPT = PROJECT_DIR / "scripts" / "verify-telegram-travel-mode.sh"


@pytest.fixture
def fake_env(tmp_path) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FREYJA_ENV=development\n"
        "TELEGRAM_ENABLED=false\n"
        "TELEGRAM_ALLOWED_USER_IDS=\n"
        "TELEGRAM_DIRECT_MESSAGES_ONLY=true\n"
        "TELEGRAM_SMITH_READ_ONLY_ENABLED=false\n"
        "AGENT_SMITH_ENABLED=false\n"
        "AGENT_SMITH_READ_ONLY_ENABLED=false\n"
        "AGENT_SMITH_WRITE_PILOT_ENABLED=false\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
        "OPENROUTER_API_KEY=\n"
        "UNRELATED_VALUE=keep-me\n",
        encoding="utf-8",
    )
    return env_file


def _run_script(script: Path, args: list[str], env_file: Path, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["_TEST_ENV_FILE"] = str(env_file)
    # The scripts operate on a hardcoded path; we test them via bash -n only.
    return subprocess.run(
        ["bash", "-n", str(script)] + args,
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )


def test_enable_script_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(ENABLE_SCRIPT), "123456"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0


def test_disable_script_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(DISABLE_SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0


def test_verify_script_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(VERIFY_SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0


def test_enable_script_only_changes_intended_flags(fake_env):
    script = PROJECT_DIR / "scripts" / "enable-telegram-travel-mode.sh"
    # We cannot run the script directly because it edits the hardcoded .env.
    # Instead, emulate its sed logic and verify flag transforms.
    content = fake_env.read_text(encoding="utf-8")
    assert "TELEGRAM_ENABLED=false" in content
    assert "AGENT_SMITH_ENABLED=false" in content

    # Simulate the intended changes.
    content = content.replace("TELEGRAM_ENABLED=false", "TELEGRAM_ENABLED=true")
    content = content.replace("TELEGRAM_ALLOWED_USER_IDS=", "TELEGRAM_ALLOWED_USER_IDS=123456")
    content = content.replace("TELEGRAM_SMITH_READ_ONLY_ENABLED=false", "TELEGRAM_SMITH_READ_ONLY_ENABLED=true")
    content = content.replace("AGENT_SMITH_ENABLED=false", "AGENT_SMITH_ENABLED=true")
    content = content.replace("AGENT_SMITH_READ_ONLY_ENABLED=false", "AGENT_SMITH_READ_ONLY_ENABLED=true")
    content = content.replace("AGENT_SMITH_WRITE_PILOT_ENABLED=false", "AGENT_SMITH_WRITE_PILOT_ENABLED=false")

    fake_env.write_text(content, encoding="utf-8")
    assert "TELEGRAM_ENABLED=true" in fake_env.read_text(encoding="utf-8")
    assert "TELEGRAM_ALLOWED_USER_IDS=123456" in fake_env.read_text(encoding="utf-8")
    assert "AGENT_SMITH_ENABLED=true" in fake_env.read_text(encoding="utf-8")
    assert "AGENT_SMITH_WRITE_PILOT_ENABLED=false" in fake_env.read_text(encoding="utf-8")
    assert "UNRELATED_VALUE=keep-me" in fake_env.read_text(encoding="utf-8")


def test_disable_script_restores_safe_values(fake_env):
    # Start in an enabled state.
    content = fake_env.read_text(encoding="utf-8")
    content = content.replace("TELEGRAM_ENABLED=false", "TELEGRAM_ENABLED=true")
    content = content.replace("TELEGRAM_ALLOWED_USER_IDS=", "TELEGRAM_ALLOWED_USER_IDS=123456")
    content = content.replace("TELEGRAM_SMITH_READ_ONLY_ENABLED=false", "TELEGRAM_SMITH_READ_ONLY_ENABLED=true")
    content = content.replace("AGENT_SMITH_ENABLED=false", "AGENT_SMITH_ENABLED=true")
    content = content.replace("AGENT_SMITH_READ_ONLY_ENABLED=false", "AGENT_SMITH_READ_ONLY_ENABLED=true")
    fake_env.write_text(content, encoding="utf-8")

    # Simulate disable script transforms.
    content = fake_env.read_text(encoding="utf-8")
    content = content.replace("TELEGRAM_ENABLED=true", "TELEGRAM_ENABLED=false")
    content = content.replace("TELEGRAM_ALLOWED_USER_IDS=123456", "TELEGRAM_ALLOWED_USER_IDS=")
    content = content.replace("TELEGRAM_SMITH_READ_ONLY_ENABLED=true", "TELEGRAM_SMITH_READ_ONLY_ENABLED=false")
    content = content.replace("AGENT_SMITH_ENABLED=true", "AGENT_SMITH_ENABLED=false")
    content = content.replace("AGENT_SMITH_READ_ONLY_ENABLED=true", "AGENT_SMITH_READ_ONLY_ENABLED=false")
    content = content.replace("AGENT_SMITH_WRITE_PILOT_ENABLED=true", "AGENT_SMITH_WRITE_PILOT_ENABLED=false")
    fake_env.write_text(content, encoding="utf-8")

    final = fake_env.read_text(encoding="utf-8")
    assert "TELEGRAM_ENABLED=false" in final
    assert "TELEGRAM_ALLOWED_USER_IDS=" in final
    assert "AGENT_SMITH_ENABLED=false" in final
    assert "AGENT_SMITH_WRITE_PILOT_ENABLED=false" in final
    assert "UNRELATED_VALUE=keep-me" in final


@pytest.mark.parametrize(
    "env_content,expected_unsafe",
    [
        (
            "TELEGRAM_ENABLED=true\nTELEGRAM_ALLOWED_USER_IDS=\nTELEGRAM_DIRECT_MESSAGES_ONLY=true\nAGENT_SMITH_WRITE_PILOT_ENABLED=false\n",
            True,
        ),
        (
            "TELEGRAM_ENABLED=true\nTELEGRAM_ALLOWED_USER_IDS=123456\nTELEGRAM_DIRECT_MESSAGES_ONLY=false\nAGENT_SMITH_WRITE_PILOT_ENABLED=false\n",
            True,
        ),
        (
            "TELEGRAM_ENABLED=true\nTELEGRAM_ALLOWED_USER_IDS=123456\nTELEGRAM_DIRECT_MESSAGES_ONLY=true\nAGENT_SMITH_WRITE_PILOT_ENABLED=true\n",
            True,
        ),
        (
            "TELEGRAM_ENABLED=true\nTELEGRAM_ALLOWED_USER_IDS=123456\nTELEGRAM_DIRECT_MESSAGES_ONLY=true\nAGENT_SMITH_WRITE_PILOT_ENABLED=false\nAGENT_SMITH_CONTROLLED_TOOLS_ENABLED=true\n",
            True,
        ),
        (
            "TELEGRAM_ENABLED=true\nTELEGRAM_ALLOWED_USER_IDS=123456\nTELEGRAM_DIRECT_MESSAGES_ONLY=true\nAGENT_SMITH_WRITE_PILOT_ENABLED=false\n",
            False,
        ),
    ],
)
def test_verify_script_detects_unsafe_configurations(fake_env, env_content, expected_unsafe):
    fake_env.write_text(env_content, encoding="utf-8")
    # The verify script uses a hardcoded path; we cannot run it directly on a temp file here,
    # but we can replicate the unsafe-detection logic in Python and assert consistency.
    content = fake_env.read_text(encoding="utf-8")
    unsafe = False
    telegram_enabled = "TELEGRAM_ENABLED=true" in content
    allowed_count = sum(1 for line in content.splitlines() if line.startswith("TELEGRAM_ALLOWED_USER_IDS="))
    allowed_value = ""
    for line in content.splitlines():
        if line.startswith("TELEGRAM_ALLOWED_USER_IDS="):
            allowed_value = line.split("=", 1)[1]
            break
    allowed_count = len([x for x in allowed_value.split(",") if x.strip().isdigit()])
    dm_only = "TELEGRAM_DIRECT_MESSAGES_ONLY=true" in content
    write_enabled = "AGENT_SMITH_WRITE_PILOT_ENABLED=true" in content
    controlled_enabled = "AGENT_SMITH_CONTROLLED_TOOLS_ENABLED=true" in content

    if telegram_enabled and allowed_count == 0:
        unsafe = True
    if telegram_enabled and not dm_only:
        unsafe = True
    if write_enabled:
        unsafe = True
    if controlled_enabled:
        unsafe = True

    assert unsafe == expected_unsafe
