from __future__ import annotations

import argparse
import json
import time

from connectors.gmail.config import settings
from connectors.gmail.reminders import EmailReminderScanner, ImapGmailInbox, ReminderExtractor, ReminderStore


def scan_once() -> dict[str, object]:
    if not settings.gmail_inbox_monitor_enabled:
        raise RuntimeError("GMAIL_INBOX_MONITOR_ENABLED is false")
    source = ImapGmailInbox(
        host=settings.gmail_imap_host,
        port=settings.gmail_imap_port,
        username=settings.gmail_imap_username,
        password=settings.gmail_inbox_password,
        folder=settings.gmail_inbox_folder,
    )
    scanner = EmailReminderScanner(
        source,
        ReminderStore(settings.gmail_reminder_store_path),
        ReminderExtractor(),
    )
    return scanner.scan(
        lookback_days=settings.gmail_inbox_lookback_days,
        limit=settings.gmail_inbox_max_messages,
        unread_only=settings.gmail_inbox_unread_only,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan Gmail for reminder candidates.")
    parser.add_argument("--watch", action="store_true", help="Repeat at the configured interval.")
    args = parser.parse_args(argv)
    while True:
        print(json.dumps(scan_once(), sort_keys=True), flush=True)
        if not args.watch:
            return 0
        time.sleep(max(60, settings.gmail_inbox_poll_interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
