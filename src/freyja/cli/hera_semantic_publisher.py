from __future__ import annotations

import argparse
import os
import sys

import httpx

from freyja.foundation_models import SemanticEvent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a Hera semantic perception event to Freyja 3.")
    parser.add_argument("--url", default=os.environ.get("FREYJA3_EVENT_URL", "http://127.0.0.1:8300/events/semantic"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--event-type", required=True)
    parser.add_argument("--room")
    parser.add_argument("--subject")
    parser.add_argument("--confidence", type=float, required=True)
    parser.add_argument("--source-machine-id", default=os.environ.get("FREYJA3_SOURCE_MACHINE_ID", "hera"))
    args = parser.parse_args(argv)

    event = SemanticEvent(
        source_machine_id=args.source_machine_id,
        event_type=args.event_type,
        room=args.room,
        subject=args.subject,
        confidence=args.confidence,
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


if __name__ == "__main__":
    raise SystemExit(main())
