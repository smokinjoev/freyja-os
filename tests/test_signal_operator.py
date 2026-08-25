from __future__ import annotations

import importlib.util
from pathlib import Path

from connectors.signal.config import SignalSettings


REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_PATH = REPO_ROOT / "scripts" / "signal-operator.py"


def _load_operator():
    spec = importlib.util.spec_from_file_location("signal_operator", OPERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configured_recipients_are_sorted() -> None:
    operator = _load_operator()
    settings = SignalSettings(
        _env_file=None,
        signal_allowed_senders="+15550000002,+15550000001",
    )

    assert operator._configured_recipients(settings) == [
        "+15550000001",
        "+15550000002",
    ]


def test_allowlist_output_hashes_recipients(monkeypatch, capsys) -> None:
    operator = _load_operator()
    monkeypatch.setattr(
        operator,
        "_settings",
        lambda env_file: SignalSettings(_env_file=None, signal_allowed_senders="+15550000001"),
    )

    result = operator.main(["allowlist"])

    output = capsys.readouterr().out
    assert result == 0
    assert "recipient_hashes" in output
    assert "+15550000001" not in output


def test_live_smoke_defaults_to_dry_run_for_first_allowlisted_recipient() -> None:
    import asyncio

    operator = _load_operator()
    settings = SignalSettings(
        _env_file=None,
        signal_allowed_senders="+15550000002,+15550000001",
        signal_rest_api_url="http://signal-api:8080",
    )

    result = asyncio.run(
        operator._live_smoke(
            settings,
            recipient=None,
            text="Freyja 2.0 Signal live smoke test.",
            dry_run=True,
        )
    )

    assert result["schema_version"] == "1.0"
    assert result["report_type"] == "signal-live-smoke"
    assert result["dry_run"] is True
    assert result["status"] == "dry-run"
    assert result["plan"]["recipient_count"] == 2
    assert result["plan"]["recipient_hash"] == operator._safe_hash("+15550000001")
    assert result["plan"]["rest_api_url"] == "http://signal-api:8080"
    assert "+15550000001" not in str(result)
    assert result["sent"] == 0
    assert result["failed"] == 0


def test_live_smoke_rejects_non_allowlisted_recipient() -> None:
    import asyncio

    operator = _load_operator()
    settings = SignalSettings(
        _env_file=None,
        signal_allowed_senders="+15550000001",
    )

    result = asyncio.run(
        operator._live_smoke(
            settings,
            recipient="+15550000002",
            text="hello",
            dry_run=True,
        )
    )

    assert result["status"] == "error"
    assert result["error"] == "recipient is not in SIGNAL_ALLOWED_SENDERS"
    assert result["recipient_hash"] == operator._safe_hash("+15550000002")
    assert "+15550000002" not in str(result)
    assert result["sent"] == 0


def test_live_smoke_sends_only_when_not_dry_run(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()
    settings = SignalSettings(
        _env_file=None,
        signal_enabled=True,
        signal_account_number="+15550000009",
        signal_allowed_senders="+15550000001",
    )
    sent = {}

    async def fake_send_to(settings_arg, recipient, text):
        sent["recipient"] = recipient
        sent["text"] = text

    monkeypatch.setattr(operator, "_send_to", fake_send_to)

    dry_run = asyncio.run(
        operator._live_smoke(
            settings,
            recipient="+15550000001",
            text="hello",
            dry_run=True,
        )
    )
    sent_result = asyncio.run(
        operator._live_smoke(
            settings,
            recipient="+15550000001",
            text="hello",
            dry_run=False,
        )
    )

    assert dry_run["status"] == "dry-run"
    assert sent_result["status"] == "sent"
    assert sent_result["dry_run"] is False
    assert sent_result["sent"] == 1
    assert sent == {"recipient": "+15550000001", "text": "hello"}


def test_live_smoke_can_write_json_report(tmp_path, monkeypatch) -> None:
    operator = _load_operator()
    output = tmp_path / "signal-smoke.json"
    monkeypatch.setattr(
        operator,
        "_settings",
        lambda env_file: SignalSettings(_env_file=None, signal_allowed_senders="+15550000001"),
    )

    result = operator.main(["live-smoke", "--dry-run", "--output", str(output)])

    assert result == 0
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert '"report_type": "signal-live-smoke"' in text
    assert "+15550000001" not in text


def test_readiness_reports_blockers_without_raw_phone_numbers(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()
    settings = SignalSettings(
        _env_file=None,
        signal_enabled=False,
        signal_account_number="",
        signal_allowed_senders="+15550000001",
        freyja_connector_token="",
        signal_rest_api_url="http://signal-api:8080",
    )

    async def fake_rest_about(settings_arg):
        raise RuntimeError("offline")

    monkeypatch.setattr(operator, "_rest_about", fake_rest_about)

    result = asyncio.run(operator._readiness(settings, check_registered=False))

    assert result["report_type"] == "signal-readiness"
    assert result["status"] == "blocked"
    assert result["ready_for_live_smoke"] is False
    assert result["checks"]["allowed_recipient_count"] == 1
    assert result["checks"]["recipient_hashes"] == [operator._safe_hash("+15550000001")]
    assert "+15550000001" not in str(result)
    assert "Set SIGNAL_ENABLED=true" in result["missing"][0]
    assert any("signal-cli-rest-api" in item for item in result["missing"])


def test_readiness_passes_when_configured_and_account_registered(monkeypatch) -> None:
    import asyncio

    operator = _load_operator()
    settings = SignalSettings(
        _env_file=None,
        signal_enabled=True,
        signal_account_number="+15550000009",
        signal_allowed_senders="+15550000001",
        freyja_connector_token="token",
        signal_rest_api_url="http://signal-api:8080",
    )

    async def fake_rest_about(settings_arg):
        return {"version": "test"}

    async def fake_registered_accounts(settings_arg):
        return ["+15550000009"]

    monkeypatch.setattr(operator, "_rest_about", fake_rest_about)
    monkeypatch.setattr(operator, "_registered_accounts", fake_registered_accounts)

    result = asyncio.run(operator._readiness(settings, check_registered=True))

    assert result["status"] == "ready"
    assert result["ready_for_live_smoke"] is True
    assert result["missing"] == []
    assert result["checks"]["account_registered"] is True
    assert result["checks"]["registered_account_count"] == 1


def test_readiness_command_writes_report_and_uses_exit_code(tmp_path, monkeypatch) -> None:
    operator = _load_operator()
    output = tmp_path / "signal-readiness.json"
    monkeypatch.setattr(
        operator,
        "_settings",
        lambda env_file: SignalSettings(_env_file=None, signal_allowed_senders=""),
    )

    async def fake_rest_about(settings_arg):
        raise RuntimeError("offline")

    monkeypatch.setattr(operator, "_rest_about", fake_rest_about)

    result = operator.main(["readiness", "--output", str(output)])

    assert result == 1
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert '"report_type": "signal-readiness"' in text
    assert '"ready_for_live_smoke": false' in text
