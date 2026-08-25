from __future__ import annotations

import importlib.util
import urllib.error
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
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(
        module,
        "_imsg_whois_local",
        lambda settings, address, timeout: {
            "known": address == "+15550000000",
            "service": "imessage" if address == "+15550000000" else "unknown",
        },
    )
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": False, "error": "timeout"})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})

    status = module._imessage_status(check_director=False, check_rev2_director=False, check_route_smoke=False, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is True
    assert status["allowed_sender_count"] == 2
    assert status["locally_known_imessage_sender_count"] == 1
    assert status["imsg_status"] == {"ok": True, "status_code": 0}
    assert status["messages_applescript"] == {"ok": False, "error": "timeout"}
    assert "joe@example.com" not in str(status)
    assert "+15550000000" not in str(status)


def test_imessage_status_reports_transport_diagnostics_without_requiring_send(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(
        module,
        "_imsg_whois_local",
        lambda settings, address, timeout: {"known": False, "service": "unknown", "error": "timeout"},
    )
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": False, "error": "timeout"})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": False, "error": "timeout"})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})

    status = module._imessage_status(check_director=False, check_rev2_director=False, check_route_smoke=False, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is True
    assert status["locally_known_imessage_sender_count"] == 0
    assert status["imsg_status"]["error"] == "timeout"
    assert status["messages_applescript"]["error"] == "timeout"
    assert "joe@example.com" not in str(status)


def test_signal_status_redacts_sender_values(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("SIGNAL_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "+15550000001")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "joe=+15550000002,beth=+15550000003")
    monkeypatch.setenv("FREYJA_DIRECTOR_URL", "http://atlas-director:8000")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")

    status = module._signal_status(check_director=False, check_rev2_director=False, check_rest=False)

    assert status["ready_for_live_smoke"] is True
    assert status["allowed_sender_count"] == 2
    assert status["account_number_configured"] is True
    assert "+15550000001" not in str(status)
    assert "+15550000002" not in str(status)
    assert "+15550000003" not in str(status)


def test_signal_status_requires_token_for_live_smoke(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("SIGNAL_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "+15550000001")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "joe=+15550000002")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "")

    status = module._signal_status(check_director=False, check_rev2_director=False, check_rest=False)

    assert status["ready_for_live_smoke"] is False
    assert status["connector_token_configured"] is False


def test_signal_status_requires_requested_health_checks(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("SIGNAL_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "+15550000001")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "joe=+15550000002")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(module, "_http_health", lambda url, timeout=5.0, headers=None: {"ok": False, "status_code": 503})

    status = module._signal_status(check_director=True, check_rev2_director=False, check_rest=True)

    assert status["ready_for_live_smoke"] is False
    assert status["director_health"]["ok"] is False


def test_gmail_status_reports_configuration_without_secrets(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("GMAIL_ENABLED", "true")
    monkeypatch.setenv("GMAIL_IDENTITY", "freyja@example.com")
    monkeypatch.setenv("GMAIL_ALLOWED_SENDERS", "joe=worker@example.com")
    monkeypatch.setenv("GMAIL_IMAP_USERNAME", "freyja@example.com")
    monkeypatch.setenv("GMAIL_IMAP_PASSWORD", "imap-secret")
    monkeypatch.setenv("GMAIL_SMTP_USERNAME", "freyja@example.com")
    monkeypatch.setenv("GMAIL_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "connector-secret")
    monkeypatch.setattr(module, "_launchagent_status", lambda label: {"ok": True, "checked": True, "label": label})

    status = module._gmail_status(check_director=False, check_rev2_director=False)

    assert status["enabled"] is True
    assert status["host_role"] == "atlas-launchagent"
    assert status["identity_configured"] is True
    assert status["allowed_sender_count"] == 1
    assert status["transport_configured"] is True
    assert status["imap_username_configured"] is True
    assert status["imap_password_configured"] is True
    assert status["smtp_username_configured"] is True
    assert status["smtp_password_configured"] is True
    assert status["launchagent"]["ok"] is True
    assert status["ready_for_live_smoke"] is True
    assert "imap-secret" not in str(status)
    assert "smtp-secret" not in str(status)
    assert "connector-secret" not in str(status)


def test_gmail_status_blocks_live_smoke_until_credentials(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    monkeypatch.setenv("GMAIL_IDENTITY", "")
    monkeypatch.setenv("GMAIL_ALLOWED_SENDERS", "")
    monkeypatch.setenv("GMAIL_IMAP_USERNAME", "")
    monkeypatch.setenv("GMAIL_IMAP_PASSWORD", "")
    monkeypatch.setenv("GMAIL_SMTP_USERNAME", "")
    monkeypatch.setenv("GMAIL_SMTP_PASSWORD", "")
    monkeypatch.setattr(module, "_launchagent_status", lambda label: {"ok": False, "checked": True, "label": label})

    status = module._gmail_status(check_director=False, check_rev2_director=False)

    assert status["ready_for_live_smoke"] is False
    assert status["identity_configured"] is False
    assert status["allowed_sender_count"] == 0
    assert status["transport_configured"] is False
    assert status["launchagent"]["ok"] is False


def test_http_health_reports_permission_denied_detail(monkeypatch):
    module = _load_script()

    def raise_permission_denied(request, timeout):
        raise urllib.error.URLError(PermissionError(1, "Operation not permitted"))

    monkeypatch.setattr(module.urllib.request, "urlopen", raise_permission_denied)

    status = module._http_health("http://127.0.0.1:8000/health", timeout=3.0)

    assert status == {
        "ok": False,
        "error": "URLError",
        "detail": "errno=1 Operation not permitted",
    }


def test_clip_tail_preserves_actionable_traceback_end() -> None:
    module = _load_script()

    clipped = module._clip_tail("prefix " * 100 + "ModuleNotFoundError: No module named 'freyja.inference'", limit=80)

    assert "ModuleNotFoundError" in clipped
    assert "freyja.inference" in clipped


def test_imessage_runtime_source_drift_reports_matching_and_diff_files(tmp_path):
    module = _load_script()
    checkout = tmp_path / "checkout"
    runtime = tmp_path / "runtime"
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("\n".join(module._imessage_runtime_source_paths()) + "\n", encoding="utf-8")
    for root in (checkout, runtime):
        for rel_path in module._imessage_runtime_source_paths(manifest):
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"same {rel_path}", encoding="utf-8")
    (runtime / "src/freyja/router.py").write_text("stale router", encoding="utf-8")

    status = module._imessage_runtime_source_drift(checkout_root=checkout, runtime_root=runtime, manifest=manifest)

    assert status["ok"] is False
    assert status["drift_count"] == 1
    files = {entry["path"]: entry for entry in status["files"]}
    assert files["connectors/imessage/gateway.py"]["status"] == "ok"
    assert files["src/freyja/agents/coding_lane.py"]["status"] == "ok"
    assert files["src/freyja/inference.py"]["status"] == "ok"
    assert files["src/freyja/media.py"]["status"] == "ok"
    assert files["src/freyja/router.py"]["status"] == "diff"
    assert files["src/freyja/router.py"]["checkout_sha256"] != files["src/freyja/router.py"]["runtime_sha256"]


def test_imessage_runtime_source_drift_reports_missing_import_dependency(tmp_path):
    module = _load_script()
    checkout = tmp_path / "checkout"
    runtime = tmp_path / "runtime"
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("\n".join(module._imessage_runtime_source_paths()) + "\n", encoding="utf-8")
    for root in (checkout, runtime):
        for rel_path in module._imessage_runtime_source_paths(manifest):
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"same {rel_path}", encoding="utf-8")
    (runtime / "src/freyja/agents/coding_lane.py").unlink()

    status = module._imessage_runtime_source_drift(checkout_root=checkout, runtime_root=runtime, manifest=manifest)

    files = {entry["path"]: entry for entry in status["files"]}
    assert status["ok"] is False
    assert status["drift_count"] == 1
    assert files["src/freyja/agents/coding_lane.py"]["status"] == "missing-runtime"


def test_imessage_runtime_source_drift_fails_closed_when_manifest_missing(tmp_path):
    module = _load_script()

    status = module._imessage_runtime_source_drift(
        checkout_root=tmp_path / "checkout",
        runtime_root=tmp_path / "runtime",
        manifest=tmp_path / "missing-manifest.txt",
    )

    assert status["ok"] is False
    assert status["drift_count"] == 1
    assert status["files"] == [{"path": str(tmp_path / "missing-manifest.txt"), "status": "missing-manifest"}]


def test_imessage_status_requires_runtime_source_without_drift(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(module, "_imsg_whois_local", lambda settings, address, timeout: {"known": True, "service": "imessage"})
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(
        module,
        "_imessage_runtime_source_drift",
        lambda: {
            "ok": False,
            "drift_count": 1,
            "files": [{"path": "src/freyja/router.py", "status": "diff"}],
        },
    )
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})

    status = module._imessage_status(check_director=False, check_rev2_director=False, check_route_smoke=False, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is False
    assert status["runtime_source_drift"]["files"][0]["path"] == "src/freyja/router.py"


def test_imessage_status_requires_runtime_import_check(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(module, "_imsg_whois_local", lambda settings, address, timeout: {"known": True, "service": "imessage"})
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(
        module,
        "_imessage_runtime_import_check",
        lambda: {"ok": False, "error": "ModuleNotFoundError"},
    )

    status = module._imessage_status(check_director=False, check_rev2_director=False, check_route_smoke=False, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is False
    assert status["runtime_import_check"]["ok"] is False


def test_imessage_status_can_require_protected_rev2_director_surface(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(
        module,
        "_imsg_whois_local",
        lambda settings, address, timeout: {"known": True, "service": "imessage"},
    )
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})
    monkeypatch.setattr(
        module,
        "_director_rev2_health",
        lambda base_url, token, timeout: {"ok": False, "checks": {"/providers/health": {"ok": False, "status_code": 404}}},
    )

    status = module._imessage_status(check_director=False, check_rev2_director=True, check_route_smoke=False, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is False
    assert status["director_rev2_health"]["ok"] is False


def test_imessage_status_can_require_synthetic_route_smoke(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(module, "_imsg_whois_local", lambda settings, address, timeout: {"known": True, "service": "imessage"})
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})
    monkeypatch.setattr(
        module,
        "_imessage_route_smoke",
        lambda settings, timeout, identity=None: {
            "ok": True,
            "terminal_equivalent": True,
            "imessage": {"provider": "local_reasoning"},
            "terminal": {"provider": "local_reasoning"},
        },
    )

    status = module._imessage_status(check_director=False, check_rev2_director=False, check_route_smoke=True, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is True
    assert status["synthetic_route_smoke"]["ok"] is True


def test_imessage_status_fails_when_synthetic_route_smoke_is_not_local_reasoning(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(module, "_imsg_whois_local", lambda settings, address, timeout: {"known": True, "service": "imessage"})
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})
    monkeypatch.setattr(
        module,
        "_imessage_route_smoke",
        lambda settings, timeout, identity=None: {
            "ok": False,
            "terminal_equivalent": False,
            "imessage": {"provider": "ollama", "checks": {"provider_matches": False}},
            "terminal": {"provider": "local_reasoning", "checks": {"provider_matches": True}},
        },
    )

    status = module._imessage_status(check_director=False, check_rev2_director=False, check_route_smoke=True, check_inprocess_route_smoke=False, route_identity=None)

    assert status["ready_for_live_smoke"] is False
    assert status["synthetic_route_smoke"]["terminal_equivalent"] is False
    assert status["synthetic_route_smoke"]["imessage"]["provider"] == "ollama"
    assert status["synthetic_route_smoke"]["imessage"]["checks"]["provider_matches"] is False


def test_imessage_status_can_require_inprocess_route_smoke(monkeypatch, tmp_path):
    module = _load_script()
    db_path = tmp_path / "chat.db"
    db_path.touch()
    imsg_path = tmp_path / "imsg"
    imsg_path.touch()
    monkeypatch.setenv("IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("IMESSAGE_IMSG_PATH", str(imsg_path))
    monkeypatch.setenv("IMESSAGE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IMESSAGE_ALLOWED_SENDERS", "joe=joe@example.com")
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret")
    monkeypatch.setattr(module, "_imsg_whois_local", lambda settings, address, timeout: {"known": True, "service": "imessage"})
    monkeypatch.setattr(module, "_run_command", lambda command, timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_messages_applescript_status", lambda timeout: {"ok": True, "status_code": 0})
    monkeypatch.setattr(module, "_imessage_runtime_source_drift", lambda: {"ok": True, "drift_count": 0, "files": []})
    monkeypatch.setattr(module, "_imessage_runtime_import_check", lambda: {"ok": True})
    monkeypatch.setattr(
        module,
        "_imessage_inprocess_route_smoke",
        lambda settings, timeout, identity=None: {
            "ok": True,
            "source": "inprocess",
            "terminal_equivalent": True,
            "prompt_context_equivalent": True,
            "direct_agent_context_present": True,
        },
    )

    status = module._imessage_status(
        check_director=False,
        check_rev2_director=False,
        check_route_smoke=False,
        check_inprocess_route_smoke=True,
        route_identity=None,
    )

    assert status["ready_for_live_smoke"] is True
    assert status["inprocess_route_smoke"]["source"] == "inprocess"
    assert status["inprocess_route_smoke"]["prompt_context_equivalent"] is True


def test_imessage_route_smoke_posts_trusted_headers_and_checks_trace(monkeypatch):
    module = _load_script()
    captured = []

    class Settings:
        freyja_director_url = "http://director"
        freyja_connector_token = "secret"

    def fake_post(url, *, payload, timeout=5.0, headers=None):
        captured.append({"url": url, "payload": payload, "headers": headers})
        interface = headers["X-Freyja-Client-Type"]
        return {
            "ok": True,
            "status_code": 200,
            "payload": {
                "provider": "local_reasoning",
                "model": "gpt-oss-freyja:20b-analysis-prefill",
                "response": "ack",
                "privacy_classification": "routine",
                "trace": {
                    "interface": interface,
                    "person": {"person_id": "joe"},
                    "principal": {"client_subject": "agent:cloyd-gibbler"},
                },
            },
        }

    status = module._imessage_route_smoke(Settings(), timeout=3.0, post_json=fake_post)

    assert status["ok"] is True
    assert status["terminal_equivalent"] is True
    assert len(captured) == 2
    assert {call["headers"]["X-Freyja-Client-Type"] for call in captured} == {"imessage", "terminal"}
    for call in captured:
        assert call["url"] == "http://director/route"
        assert call["payload"]["include_trace"] is True
        assert call["headers"]["X-Freyja-Client-Subject"] == "agent:cloyd-gibbler"
        assert call["headers"]["Authorization"] == "Bearer secret"
    assert status["imessage"]["checks"] == {
        "response_present": True,
        "provider_matches": True,
        "interface_matches": True,
        "person_matches": True,
        "principal_matches": True,
    }
    assert status["terminal"]["checks"]["interface_matches"] is True


def test_imessage_route_smoke_supports_custom_identity(monkeypatch):
    module = _load_script()
    captured = []

    class Settings:
        freyja_director_url = "http://director"
        freyja_connector_token = ""

    identity = module.SyntheticRouteIdentity(
        person_id="beth",
        person_display_name="Beth",
        person_preferred_name="Beth",
        agent_id="benedict",
        agent_display_name="Benedict",
        expected_provider="local_reasoning",
    )

    def fake_post(url, *, payload, timeout=5.0, headers=None):
        captured.append({"payload": payload, "headers": headers})
        interface = headers["X-Freyja-Client-Type"]
        return {
            "ok": True,
            "status_code": 200,
            "payload": {
                "provider": "local_reasoning",
                "model": "gpt-oss-freyja:20b-analysis-prefill",
                "response": "ack",
                "trace": {
                    "interface": interface,
                    "person": {"person_id": "beth"},
                    "principal": {"client_subject": "agent:benedict"},
                },
            },
        }

    status = module._imessage_route_smoke(Settings(), timeout=3.0, identity=identity, post_json=fake_post)

    assert status["ok"] is True
    assert status["terminal_equivalent"] is True
    assert {call["headers"]["X-Freyja-Client-Subject"] for call in captured} == {"agent:benedict"}
    assert {call["headers"]["X-Freyja-Account-Owner"] for call in captured} == {"person:beth"}
    assert {call["headers"]["X-Freyja-Agent-Display-Name"] for call in captured} == {"Benedict"}
    assert status["imessage"]["expected_person_id"] == "beth"
    assert status["imessage"]["expected_client_subject"] == "agent:benedict"


def test_director_rev2_health_requires_heavy_local_ready(monkeypatch):
    module = _load_script()

    def fake_http_json(url, timeout=5.0, headers=None):
        return {
            "ok": True,
            "status_code": 200,
            "payload": {
                "providers": [
                    {"provider_id": "legacy_ollama", "ready": True},
                    {"provider_id": "heavy_local", "ready": False},
                    {"provider_id": "qwen_coding", "ready": True},
                ]
            },
        }

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(module, "_http_health", lambda url, timeout=5.0, headers=None: {"ok": True, "status_code": 200})

    status = module._director_rev2_health("http://director", "secret", timeout=5.0)

    assert status["ok"] is False
    providers = status["checks"]["/providers/health"]
    assert providers["required_provider_readiness"]["heavy_local"] is False
    assert providers["unavailable_required_providers"] == ["heavy_local"]


def test_director_rev2_health_accepts_required_provider_profiles(monkeypatch):
    module = _load_script()

    def fake_http_json(url, timeout=5.0, headers=None):
        return {
            "ok": True,
            "status_code": 200,
            "payload": {
                "providers": [
                    {"provider_id": "legacy_ollama", "ready": True},
                    {"provider_id": "heavy_local", "ready": True},
                    {"provider_id": "qwen_coding", "ready": True},
                ]
            },
        }

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(module, "_http_health", lambda url, timeout=5.0, headers=None: {"ok": True, "status_code": 200})

    status = module._director_rev2_health("http://director", "secret", timeout=5.0)

    assert status["ok"] is True
    assert status["checks"]["/providers/health"]["unavailable_required_providers"] == []


def test_main_returns_nonzero_when_selected_connector_not_ready(monkeypatch, capsys):
    module = _load_script()
    monkeypatch.setenv("SIGNAL_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "")

    result = module.main(["--connector", "signal"])

    assert result == 1
    output = capsys.readouterr().out
    assert "ready_for_live_smoke" in output


def test_main_writes_json_report_when_output_path_is_supplied(monkeypatch, tmp_path, capsys):
    module = _load_script()
    output_path = tmp_path / "messaging-production-check.json"
    monkeypatch.setenv("SIGNAL_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_ACCOUNT_NUMBER", "")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "")

    result = module.main(["--connector", "signal", "--output", str(output_path)])

    assert result == 1
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == capsys.readouterr().out
