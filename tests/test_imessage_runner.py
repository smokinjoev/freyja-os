from __future__ import annotations

import importlib.util
from pathlib import Path

from connectors.imessage.config import IMessageSettings
from connectors.imessage.gateway import IMessageGateway


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run-imessage-connector.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("imessage_runner", RUNNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_not_ready_when_gateway_disabled(tmp_path):
    runner = _load_runner()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(tmp_path / "chat.db"),
        imessage_allowed_senders="+15551234567",
    )
    gateway = IMessageGateway()
    gateway._enabled = False

    assert runner._runtime_ready(settings, gateway) is False


def test_runtime_not_ready_without_database(tmp_path):
    runner = _load_runner()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(tmp_path / "missing.db"),
        imessage_allowed_senders="+15551234567",
    )
    gateway = IMessageGateway()
    gateway._enabled = True

    assert runner._runtime_ready(settings, gateway) is False


def test_runtime_not_ready_without_allowlist(tmp_path):
    runner = _load_runner()
    database = tmp_path / "chat.db"
    database.touch()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(database),
        imessage_allowed_senders="",
    )
    gateway = IMessageGateway()
    gateway._enabled = True

    assert runner._runtime_ready(settings, gateway) is False


def test_runtime_ready_with_enabled_gateway_database_and_allowlist(tmp_path):
    runner = _load_runner()
    database = tmp_path / "chat.db"
    database.touch()
    settings = IMessageSettings(
        _env_file=None,
        imessage_database_path=str(database),
        imessage_allowed_senders="+15551234567",
    )
    gateway = IMessageGateway()
    gateway._enabled = True

    assert runner._runtime_ready(settings, gateway) is True
