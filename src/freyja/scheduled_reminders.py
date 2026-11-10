"""Persistent storage for recurring reminders."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ScheduledReminder:
    reminder_id: str
    text: str
    start_date: date
    local_time: time
    interval_days: int
    timezone: str = "America/New_York"


class ScheduledReminderStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS scheduled_signal_reminders (
                    reminder_id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    local_time TEXT NOT NULL,
                    interval_days INTEGER NOT NULL,
                    timezone TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_sent_date TEXT,
                    created_at TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def upsert(self, reminder: ScheduledReminder) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO scheduled_signal_reminders
                (reminder_id, text, start_date, local_time, interval_days, timezone, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(reminder_id) DO UPDATE SET
                    text=excluded.text, start_date=excluded.start_date,
                    local_time=excluded.local_time, interval_days=excluded.interval_days,
                    timezone=excluded.timezone, enabled=1""",
                (
                    reminder.reminder_id, reminder.text, reminder.start_date.isoformat(),
                    reminder.local_time.isoformat(timespec="minutes"), max(1, reminder.interval_days),
                    reminder.timezone, datetime.now().astimezone().isoformat(),
                ),
            )

    def due(self, now: datetime) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scheduled_signal_reminders WHERE enabled = 1"
            ).fetchall()
        due: list[dict[str, object]] = []
        for row in rows:
            local_now = now.astimezone(ZoneInfo(row["timezone"]))
            start = date.fromisoformat(row["start_date"])
            scheduled_time = time.fromisoformat(row["local_time"])
            elapsed = (local_now.date() - start).days
            if elapsed < 0 or elapsed % int(row["interval_days"]) != 0:
                continue
            if local_now.time().replace(tzinfo=None) < scheduled_time:
                continue
            if row["last_sent_date"] == local_now.date().isoformat():
                continue
            due.append(dict(row) | {"send_date": local_now.date().isoformat()})
        return due

    def mark_sent(self, reminder_id: str, send_date: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE scheduled_signal_reminders SET last_sent_date = ?
                WHERE reminder_id = ? AND (last_sent_date IS NULL OR last_sent_date <> ?)""",
                (send_date, reminder_id, send_date),
            )
            return cursor.rowcount == 1
    def list_enabled(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM scheduled_signal_reminders
                WHERE enabled = 1 ORDER BY start_date, local_time, created_at"""
            ).fetchall()
        return [dict(row) for row in rows]

    def disable(self, reminder_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE scheduled_signal_reminders SET enabled = 0 WHERE reminder_id = ? AND enabled = 1",
                (reminder_id,),
            )
            return cursor.rowcount == 1
