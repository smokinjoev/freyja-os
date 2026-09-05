from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-freyja-channels-readiness.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_freyja_channels_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_channels_readiness_fails_closed_without_env(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SIGNAL_ALLOWED_SENDERS", raising=False)
    monkeypatch.delenv("SIGNAL_ACCOUNT_NUMBER", raising=False)
    monkeypatch.delenv("SIGNAL_REST_API_URL", raising=False)

    report = _module().build_report()

    assert report["secrets_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["deterministic_gateway_only"] is True
    assert report["telegram"]["allowlist_configured"] is False
    assert report["telegram"]["transport_adapter"] == "TelegramLongPollingTransport"
    assert report["telegram"]["transport_configured"] is False
    assert report["telegram"]["identity_map_configured"] is False
    assert report["telegram"]["allowlist_identity_map_complete"] is False
    assert report["telegram"]["ready_for_live_round_trip"] is False
    assert report["telegram"]["missing_configuration"] == [
        "TELEGRAM_ALLOWED_USER_IDS",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_IDENTITY_MAP",
        "OPEN_WEBUI_API_KEY",
    ]
    assert report["signal"]["allowlist_configured"] is False
    assert report["signal"]["transport_adapter"] == "SignalCliRestTransport"
    assert report["signal"]["transport_configured"] is False
    assert report["signal"]["identity_map_configured"] is False
    assert report["signal"]["allowlist_identity_map_complete"] is False
    assert report["signal"]["ready_for_live_round_trip"] is False
    assert report["signal"]["missing_configuration"] == [
        "SIGNAL_ALLOWED_SENDERS",
        "SIGNAL_ACCOUNT_NUMBER",
        "SIGNAL_IDENTITY_MAP",
        "OPEN_WEBUI_API_KEY",
        "SIGNAL_REST_API_URL",
    ]
    assert report["whatsapp"]["status"] == "disabled"


def test_channels_readiness_reports_counts_not_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1001,1002")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token-value")
    monkeypatch.setenv("TELEGRAM_IDENTITY_MAP", "1001:joe,1002:beth")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "+15550001")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "+15550009")
    monkeypatch.setenv("SIGNAL_REST_API_URL", "http://signal.local")
    monkeypatch.setenv("SIGNAL_IDENTITY_MAP", "+15550001:joe")
    monkeypatch.setenv("OPEN_WEBUI_API_KEY", "secret-open-webui-key")

    report = _module().build_report()
    serialized = json.dumps(report)

    assert report["telegram"]["allowlist_count"] == 2
    assert report["telegram"]["transport_configured"] is True
    assert report["telegram"]["identity_map_configured"] is True
    assert report["telegram"]["allowlist_identity_map_complete"] is True
    assert report["telegram"]["ready_for_live_round_trip"] is True
    assert report["telegram"]["missing_configuration"] == []
    assert report["signal"]["allowlist_count"] == 1
    assert report["signal"]["transport_configured"] is True
    assert report["signal"]["identity_map_configured"] is True
    assert report["signal"]["allowlist_identity_map_complete"] is True
    assert report["signal"]["ready_for_live_round_trip"] is True
    assert report["signal"]["missing_configuration"] == []
    assert "secret-token-value" not in serialized
    assert "secret-open-webui-key" not in serialized
    assert "+15550001" not in serialized
    assert "+15550009" not in serialized


def test_channels_readiness_reports_incomplete_identity_map_without_sender_values(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1001,1002")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token-value")
    monkeypatch.setenv("TELEGRAM_IDENTITY_MAP", "1001:joe")
    monkeypatch.setenv("OPEN_WEBUI_API_KEY", "secret-open-webui-key")
    monkeypatch.delenv("SIGNAL_ALLOWED_SENDERS", raising=False)
    monkeypatch.delenv("SIGNAL_ACCOUNT_NUMBER", raising=False)
    monkeypatch.delenv("SIGNAL_REST_API_URL", raising=False)
    monkeypatch.delenv("SIGNAL_IDENTITY_MAP", raising=False)

    report = _module().build_report()
    serialized = json.dumps(report)

    assert report["telegram"]["allowlist_identity_map_complete"] is False
    assert report["telegram"]["ready_for_live_round_trip"] is False
    assert "TELEGRAM_IDENTITY_MAP:missing_allowlist_entries" in report["telegram"]["missing_configuration"]
    assert "1002" not in serialized


def test_channels_readiness_writes_report(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    output = tmp_path / "channels.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "freyja-channels-readiness"
