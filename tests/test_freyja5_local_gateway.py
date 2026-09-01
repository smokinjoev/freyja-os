from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-local-gateway.py"


def load_gateway_module():
    spec = importlib.util.spec_from_file_location("freyja5_local_gateway", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_local_gateway_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111


def test_freyja5_local_gateway_defaults_to_local_health_url() -> None:
    module = load_gateway_module()
    assert module.base_url("0.0.0.0", 8500) == "http://127.0.0.1:8500"
    assert module.base_url("localhost", 8500) == "http://localhost:8500"


def test_freyja5_local_gateway_start_sets_safe_test_environment(monkeypatch, tmp_path: Path) -> None:
    module = load_gateway_module()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

    monkeypatch.setattr(module, "health_status", lambda host, port: {"healthy": False, "url": f"http://127.0.0.1:{port}/health"})
    monkeypatch.setattr(module.time, "monotonic", iter([0.0, 99.0]).__next__)

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return FakeProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    log_file = tmp_path / "freyja5.log"
    args = module.build_parser().parse_args(
        [
            "--pid-file",
            str(tmp_path / "freyja5.pid"),
            "--log-file",
            str(log_file),
            "start",
            "--token",
            "test-token",
            "--timeout",
            "0",
        ]
    )

    assert module.command_start(args) == 1
    env = captured["env"]
    assert env["FREYJA_CONNECTOR_TOKEN"] == "test-token"
    assert env["FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED"] == "false"
    assert env["CLOUD_ENABLED"] == "false"
    assert "freyja.main:app" in captured["cmd"]
