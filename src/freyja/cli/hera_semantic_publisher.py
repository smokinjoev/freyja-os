from __future__ import annotations

import argparse
import json
import os
import sys

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
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    raise SystemExit(main())
