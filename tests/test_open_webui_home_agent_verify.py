from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "open-webui-home-agent-verify.py"


def _module():
    spec = importlib.util.spec_from_file_location("open_webui_home_agent_verify", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_script_knows_required_agents_and_operations() -> None:
    module = _module()

    assert module.REQUIRED_HOME_MEMORY_OPERATIONS == {
        "search",
        "remember",
        "update",
        "forget",
        "record-decision",
        "recent-events",
    }
    assert module.REQUIRED_AGENT_MODELS == {
        "agent/freyja",
        "agent/cloyd-gibbler",
        "agent/benedict",
        "agent/benedict-paralegal",
        "agent/agent-47",
        "agent/jennacide",
    }
    assert module.FREYJA41_BASELINE_TAG == "freyja-4.1-baseline-before-5.0-20260831-161448"
    assert module.PROTECTED_RUNNING_SERVICES == {
        "freyja-open-webui-atlas-open-webui-1",
        "freyja-open-webui-atlas-model-proxy-1",
        "freyja3-agent-gateway-1",
        "freyja3-litellm-1",
    }


def test_verify_script_writes_secret_free_report(tmp_path: Path, capsys) -> None:
    module = _module()

    def fake_request(method, url, *, headers=None, payload=None, timeout=10.0):
        if url.endswith("/api/version"):
            return 200, {"version": "0.11.3"}, None
        if url.endswith("/api/config"):
            return 200, {"features": {"auth": True}}, None
        if url.endswith("/health"):
            return 200, {"status": "healthy"}, None
        if url.endswith("/v1/models"):
            return 200, {"data": [{"id": model} for model in module.REQUIRED_AGENT_MODELS]}, None
        if url.endswith("/freyja-home-memory/operations"):
            return 200, {"operations": sorted(module.REQUIRED_HOME_MEMORY_OPERATIONS)}, None
        if url.endswith("/freyja-home-memory/remember"):
            return 200, {"id": payload["record_id"]}, None
        if "x-freyja-client-subject" in (headers or {}) and headers["x-freyja-client-subject"] == "person:beth":
            return 403, {"detail": "denied"}, None
        if "/freyja-home-memory/search" in url:
            return 200, {"records": [{"id": payload["record_id"] if payload else "live-verify-1"}]}, None
        raise AssertionError(url)

    def fake_run_command(args):
        if args[:3] == ["git", "tag", "--list"]:
            return 0, module.FREYJA41_BASELINE_TAG + "\n", ""
        if args[:2] == ["docker", "ps"]:
            return (
                0,
                "\n".join(f"{name}\tUp 1 hour (healthy)" for name in sorted(module.PROTECTED_RUNNING_SERVICES)),
                "",
            )
        raise AssertionError(args)

    output = tmp_path / "report.json"
    with (
        patch.object(module, "request_json", side_effect=fake_request),
        patch.object(module, "run_command", side_effect=fake_run_command),
        patch.object(module.time, "time", return_value=1),
    ):
        assert module.main(["--no-model-proxy-container", "--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert report == printed
    assert report["secrets_included"] is False
    assert report["ok"] is True
    assert report["optional_checks_pending"] == ["model_proxy_agent_models"]
    assert any(check["name"] == "freyja41_baseline_tag_present" and check["ok"] for check in report["checks"])
    assert any(check["name"] == "protected_side_by_side_services_running" and check["ok"] for check in report["checks"])
    assert "token" not in str(report).lower()
    assert "api_key" not in str(report).lower()


def test_verify_script_can_check_model_proxy_when_url_is_supplied(tmp_path: Path) -> None:
    module = _module()

    def fake_request(method, url, *, headers=None, payload=None, timeout=10.0):
        if url.endswith("/api/version"):
            return 200, {"version": "0.11.3"}, None
        if url.endswith("/api/config"):
            return 200, {"features": {"auth": True}}, None
        if url.endswith("/health"):
            return 200, {"status": "healthy"}, None
        if url.endswith("/v1/models"):
            return 200, {"data": [{"id": model} for model in module.REQUIRED_AGENT_MODELS]}, None
        if url.endswith("/freyja-home-memory/operations"):
            return 200, {"operations": sorted(module.REQUIRED_HOME_MEMORY_OPERATIONS)}, None
        if url.endswith("/freyja-home-memory/remember"):
            return 200, {"id": payload["record_id"]}, None
        if "x-freyja-client-subject" in (headers or {}) and headers["x-freyja-client-subject"] == "person:beth":
            return 403, {"detail": "denied"}, None
        if "/freyja-home-memory/search" in url:
            return 200, {"records": [{"id": "live-verify-1"}]}, None
        raise AssertionError(url)

    def fake_run_command(args):
        if args[:3] == ["git", "tag", "--list"]:
            return 0, module.FREYJA41_BASELINE_TAG + "\n", ""
        if args[:2] == ["docker", "ps"]:
            return (
                0,
                "\n".join(f"{name}\tUp 1 hour (healthy)" for name in sorted(module.PROTECTED_RUNNING_SERVICES)),
                "",
            )
        raise AssertionError(args)

    output = tmp_path / "report.json"
    with (
        patch.object(module, "request_json", side_effect=fake_request),
        patch.object(module, "run_command", side_effect=fake_run_command),
        patch.object(module.time, "time", return_value=1),
    ):
        assert module.main(["--model-proxy-url", "http://proxy.test", "--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["optional_checks_pending"] == []
    assert any(check["name"] == "model_proxy_agent_models" and check["ok"] for check in report["checks"])


def test_verify_script_can_check_model_proxy_from_container(tmp_path: Path) -> None:
    module = _module()

    def fake_request(method, url, *, headers=None, payload=None, timeout=10.0):
        if url.endswith("/api/version"):
            return 200, {"version": "0.11.3"}, None
        if url.endswith("/api/config"):
            return 200, {"features": {"auth": True}}, None
        if url.endswith("/health"):
            return 200, {"status": "healthy"}, None
        if url.endswith("/v1/models"):
            return 200, {"data": [{"id": model} for model in module.REQUIRED_AGENT_MODELS]}, None
        if url.endswith("/freyja-home-memory/operations"):
            return 200, {"operations": sorted(module.REQUIRED_HOME_MEMORY_OPERATIONS)}, None
        if url.endswith("/freyja-home-memory/remember"):
            return 200, {"id": payload["record_id"]}, None
        if "x-freyja-client-subject" in (headers or {}) and headers["x-freyja-client-subject"] == "person:beth":
            return 403, {"detail": "denied"}, None
        if "/freyja-home-memory/search" in url:
            return 200, {"records": [{"id": "live-verify-1"}]}, None
        raise AssertionError(url)

    def fake_run_command(args):
        if args[:3] == ["git", "tag", "--list"]:
            return 0, module.FREYJA41_BASELINE_TAG + "\n", ""
        if args[:2] == ["docker", "ps"]:
            return (
                0,
                "\n".join(f"{name}\tUp 1 hour (healthy)" for name in sorted(module.PROTECTED_RUNNING_SERVICES)),
                "",
            )
        if args[:3] == ["docker", "exec", module.DEFAULT_MODEL_PROXY_CONTAINER]:
            return 0, json.dumps({"status": 200, "data": [{"id": model} for model in module.REQUIRED_AGENT_MODELS]}), ""
        raise AssertionError(args)

    output = tmp_path / "report.json"
    with (
        patch.object(module, "request_json", side_effect=fake_request),
        patch.object(module, "run_command", side_effect=fake_run_command),
        patch.object(module.time, "time", return_value=1),
    ):
        assert module.main(["--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["model_proxy_container"] == module.DEFAULT_MODEL_PROXY_CONTAINER
    assert report["optional_checks_pending"] == []
    assert any(check["name"] == "model_proxy_agent_models" and check["ok"] for check in report["checks"])


def test_verify_script_uses_supplied_api_key_without_writing_it_to_report(tmp_path: Path, capsys) -> None:
    module = _module()
    observed_auth_headers = []

    def fake_request(method, url, *, headers=None, payload=None, timeout=10.0):
        if url.endswith("/api/models"):
            observed_auth_headers.append((headers or {}).get("authorization"))
            return 200, {"data": [{"id": "agent/freyja"}]}, None
        if url.endswith("/api/version"):
            return 200, {"version": "0.11.3"}, None
        if url.endswith("/api/config"):
            return 200, {"features": {"auth": True}}, None
        if url.endswith("/health"):
            return 200, {"status": "healthy"}, None
        if url.endswith("/v1/models"):
            return 200, {"data": [{"id": model} for model in module.REQUIRED_AGENT_MODELS]}, None
        if url.endswith("/freyja-home-memory/operations"):
            return 200, {"operations": sorted(module.REQUIRED_HOME_MEMORY_OPERATIONS)}, None
        if url.endswith("/freyja-home-memory/remember"):
            return 200, {"id": payload["record_id"]}, None
        if "x-freyja-client-subject" in (headers or {}) and headers["x-freyja-client-subject"] == "person:beth":
            return 403, {"detail": "denied"}, None
        if "/freyja-home-memory/search" in url:
            return 200, {"records": [{"id": "live-verify-1"}]}, None
        raise AssertionError(url)

    def fake_run_command(args):
        if args[:3] == ["git", "tag", "--list"]:
            return 0, module.FREYJA41_BASELINE_TAG + "\n", ""
        if args[:2] == ["docker", "ps"]:
            return (
                0,
                "\n".join(f"{name}\tUp 1 hour (healthy)" for name in sorted(module.PROTECTED_RUNNING_SERVICES)),
                "",
            )
        raise AssertionError(args)

    output = tmp_path / "report.json"
    with (
        patch.object(module, "request_json", side_effect=fake_request),
        patch.object(module, "run_command", side_effect=fake_run_command),
        patch.object(module.time, "time", return_value=1),
    ):
        assert module.main(["--no-model-proxy-container", "--open-webui-api-key", "secret-token", "--output", str(output)]) == 0

    report_text = output.read_text(encoding="utf-8")
    printed = capsys.readouterr().out
    assert observed_auth_headers == ["Bearer secret-token"]
    assert "secret-token" not in report_text
    assert "secret-token" not in printed
    report = json.loads(report_text)
    assert report["auth_required_checks_pending"] == []
