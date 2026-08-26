from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

from freyja.foundation_models import SemanticEvent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a Hera semantic perception event to Freyja 3.")
    parser.add_argument("--url", default=os.environ.get("FREYJA3_EVENT_URL", "http://127.0.0.1:8300/events/semantic"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--event-type", default=os.environ.get("FREYJA3_EVENT_TYPE", ""))
    parser.add_argument("--room", default=os.environ.get("FREYJA3_EVENT_ROOM"))
    parser.add_argument("--subject", default=os.environ.get("FREYJA3_EVENT_SUBJECT"))
    parser.add_argument("--confidence", type=float, default=_env_float("FREYJA3_EVENT_CONFIDENCE"))
    parser.add_argument("--metadata-json", default=os.environ.get("FREYJA3_EVENT_METADATA_JSON", "{}"))
    parser.add_argument("--source-machine-id", default=os.environ.get("FREYJA3_SOURCE_MACHINE_ID", "hera"))
    parser.add_argument(
        "--auto-sensor-status",
        action="store_true",
        default=_env_bool("FREYJA3_AUTO_SENSOR_STATUS"),
        help="Probe Hera camera/audio/NPU state and publish a bounded semantic status event.",
    )
    args = parser.parse_args(argv)

    if args.auto_sensor_status:
        probed_event_type, probed_confidence, probed_metadata = _probe_sensor_status()
        args.event_type = args.event_type or probed_event_type
        args.confidence = args.confidence if args.confidence is not None else probed_confidence
        args.metadata_json = json.dumps({**probed_metadata, **_json_object_or_empty(args.metadata_json)})

    if not args.event_type:
        print("event type is required", file=sys.stderr)
        return 2
    if args.confidence is None:
        print("confidence is required", file=sys.stderr)
        return 2

    try:
        metadata = json.loads(args.metadata_json)
    except json.JSONDecodeError as exc:
        print(f"invalid metadata json: {exc}", file=sys.stderr)
        return 2
    if not isinstance(metadata, dict):
        print("metadata json must decode to an object", file=sys.stderr)
        return 2

    event = SemanticEvent(
        source_machine_id=args.source_machine_id,
        event_type=args.event_type,
        room=args.room,
        subject=args.subject,
        confidence=args.confidence,
        metadata=metadata,
    )
    headers = {"x-freyja-security-domain": "system"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(args.url, headers=headers, json=event.model_dump(mode="json"))
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1
    print(response.text)
    return 0


def _env_float(name: str) -> float | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _env_bool(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _json_object_or_empty(raw: str) -> dict:
    try:
        decoded = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _probe_sensor_status() -> tuple[str, float, dict]:
    video_devices = sorted(str(path) for pattern in ("/dev/video*", "/dev/v4l/by-id/*", "/dev/v4l/by-path/*") for path in Path("/").glob(pattern.removeprefix("/")))
    audio_sources = _command_lines(["pactl", "list", "short", "sources"])
    if not audio_sources:
        audio_sources = [
            line
            for line in _command_lines(["pw-cli", "list-objects", "Node"])
            if "media.class = \"Audio/Source\"" in line or "node.name =" in line or "node.description =" in line
        ][:30]
    npu_devices = _command_lines(["sh", "-c", "lspci 2>/dev/null | grep -Ei 'neural|npu|accelerator' || true"])
    metadata = {
        "camera_devices": video_devices,
        "camera_device_count": len(video_devices),
        "audio_sources": audio_sources[:20],
        "audio_source_count": len(audio_sources),
        "npu_devices": npu_devices[:10],
        "npu_detected": bool(npu_devices),
        "probe": "hera_semantic_publisher.auto_sensor_status",
    }
    if video_devices:
        return "camera_available", 1.0, metadata
    metadata["reason"] = "no_video_device_visible"
    return "camera_unavailable", 1.0, metadata


def _command_lines(command: list[str]) -> list[str]:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
