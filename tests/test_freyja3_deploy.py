from __future__ import annotations

from pathlib import Path


def test_machine_heartbeat_user_units_are_reproducible() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/user/freyja3-machine-heartbeat.service").read_text()
    timer = (root / "deploy/systemd/user/freyja3-machine-heartbeat.timer").read_text()

    assert "EnvironmentFile=%h/.config/freyja/freyja3-machine-heartbeat.env" in service
    assert "ExecStart=%h/freyja-os-freyja3/.heartbeat-venv/bin/freyja3-machine-heartbeat" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "WantedBy=timers.target" in timer


def test_hera_semantic_publisher_user_units_are_reproducible() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/user/freyja3-hera-semantic-publisher.service").read_text()
    timer = (root / "deploy/systemd/user/freyja3-hera-semantic-publisher.timer").read_text()

    assert "EnvironmentFile=%h/.config/freyja/freyja3-hera-semantic-publisher.env" in service
    assert "ExecStart=%h/freyja-os-freyja3/.heartbeat-venv/bin/freyja-hera-semantic-publisher" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "WantedBy=timers.target" in timer
