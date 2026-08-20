from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "messaging-production-check.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("messaging_production_check", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_imessage_status_redacts_sender_values(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com,beth=+15550000000")

    status = module._imessage_status(check_director=False)

    assert status["ready_for_live_smoke"] is True
    assert status["allowed_sender_count"] == 2
    assert "joe@example.com" not in str(status)
    assert "+15550000000" not in str(status)


def test_signal_status_redacts_sender_values(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("SIGNAL_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "+15550000001")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "joe=+15550000002,beth=+15550000003")
    monkeypatch.setenv("FREYJA_DIRECTOR_URL", "http://atlas-director:8000")

    status = module._signal_status(check_director=False, check_rest=False)

    assert status["ready_for_live_smoke"] is True
    assert status["allowed_sender_count"] == 2
    assert status["account_number_configured"] is True
    assert "+15550000001" not in str(status)
    assert "+15550000002" not in str(status)
    assert "+15550000003" not in str(status)


def test_main_returns_nonzero_when_selected_connector_not_ready(monkeypatch, capsys):
    module = _load_script()
    monkeypatch.setenv("SIGNAL_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "")

    result = module.main(["--connector", "signal"])

    assert result == 1
    output = capsys.readouterr().out
    assert "ready_for_live_smoke" in output
