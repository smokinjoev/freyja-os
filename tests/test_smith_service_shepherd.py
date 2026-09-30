import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smith-service-shepherd.py"
SPEC = importlib.util.spec_from_file_location("smith_service_shepherd", SCRIPT)
assert SPEC and SPEC.loader
shepherd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shepherd)


def test_watchdog_alerts_once_when_a_known_healthy_state_becomes_critical(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(shepherd, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(shepherd, "LOG_PATH", tmp_path / "status.jsonl")
    config = {"smith_shepherd": {"docker_dependency": False, "managed_launch_agents": [], "managed_compose": []}}
    monkeypatch.setattr(shepherd, "read_yaml", lambda _path: config)
    monkeypatch.setattr(shepherd, "docker_ok", lambda: True)
    monkeypatch.setattr(
        shepherd,
        "probe_smith_routes",
        lambda _config: {"primary": {"available": True}, "openclaw_backdoor": {}, "tags_ok": True},
    )
    sent: list[str] = []
    monkeypatch.setattr(shepherd, "send_discord_alert", lambda _config, text: sent.append(text) or {"ok": True})

    healthy = shepherd.one_cycle(dry_run=True)
    assert healthy["escalation"]["transition"] == "unchanged"
    assert sent == []

    monkeypatch.setattr(
        shepherd,
        "probe_smith_routes",
        lambda _config: {"primary": {"available": False}, "openclaw_backdoor": {}, "tags_ok": False},
    )
    critical = shepherd.one_cycle(dry_run=True)
    assert critical["escalation"]["transition"] == "entered_critical"
    assert critical["escalation"]["automatic_repair"] is False
    assert sent == ["Agent Smith health alert: primary_model_route_unavailable. No repair was attempted."]

    repeated = shepherd.one_cycle(dry_run=True)
    assert repeated["escalation"]["transition"] == "unchanged"
    assert len(sent) == 1


def test_watchdog_does_not_alert_on_an_initial_critical_observation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(shepherd, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(shepherd, "LOG_PATH", tmp_path / "status.jsonl")
    config = {"smith_shepherd": {"docker_dependency": False, "managed_launch_agents": [], "managed_compose": []}}
    monkeypatch.setattr(shepherd, "read_yaml", lambda _path: config)
    monkeypatch.setattr(shepherd, "docker_ok", lambda: True)
    monkeypatch.setattr(
        shepherd,
        "probe_smith_routes",
        lambda _config: {"primary": {"available": False}, "openclaw_backdoor": {}, "tags_ok": False},
    )
    monkeypatch.setattr(shepherd, "send_discord_alert", lambda *_args: (_ for _ in ()).throw(AssertionError("must not alert")))

    initial = shepherd.one_cycle(dry_run=True)
    assert initial["escalation"]["transition"] == "unchanged"
    assert initial["escalation"]["critical"] is True
