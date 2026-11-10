"""Read-only inbox scanning and conservative reminder extraction."""

from __future__ import annotations

import hashlib
import imaplib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from connectors.gmail.models import GmailMessage
from connectors.gmail.sanitizer import sanitize_gmail_body

_ACTION_RE = re.compile(
    r"\b(?:action required|please|remember to|reminder|due|deadline|respond|reply|submit|renew|pay|complete|sign|schedule|register)\b",
    re.IGNORECASE,
)
_DATE_PATTERNS = (
    re.compile(r"\b(?P<year>20\d{2})-(?P<month>0?[1-9]|1[0-2])-(?P<day>0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12]\d|3[01])(?:/(?P<year>20\d{2}|\d{2}))?\b"),
    re.compile(
        r"\b(?P<month_name>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
        r"(?P<day>0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?(?:,?\s+(?P<year>20\d{2}))?\b",
        re.IGNORECASE,
    ),
)
_TIME_RE = re.compile(r"\b(?P<hour>0?[1-9]|1[0-2])(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)
_MONTHS = {name: number for number, names in enumerate(((), ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"))) for name in names}
_WEEKDAYS = {name: number for number, name in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}


@dataclass(frozen=True)
class ReminderCandidate:
    candidate_id: str
    message_id: str
    thread_id: str
    sender: str
    subject: str
    summary: str
    due_at: datetime
    received_at: datetime
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "subject": self.subject,
            "summary": self.summary,
            "due_at": self.due_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "evidence": self.evidence,
        }


class InboxSource(Protocol):
    def fetch_recent(self, *, since: date, limit: int, unread_only: bool = False) -> list[GmailMessage]: ...


class ImapGmailInbox:
    """Fetch Gmail messages without setting the Seen flag."""

    def __init__(self, *, host: str, port: int, username: str, password: str, folder: str = "INBOX") -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.folder = folder

    def fetch_recent(self, *, since: date, limit: int, unread_only: bool = False) -> list[GmailMessage]:
        if not self.username or not self.password:
            raise ValueError("Gmail IMAP username and app password are required")
        client = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            client.login(self.username, self.password)
            status, _ = client.select(self.folder, readonly=True)
            if status != "OK":
                raise RuntimeError(f"Could not open Gmail folder {self.folder!r}")
            criteria = ["UNSEEN"] if unread_only else []
            criteria.extend(["SINCE", since.strftime("%d-%b-%Y")])
            status, data = client.uid("search", None, *criteria)
            if status != "OK":
                raise RuntimeError("Gmail search failed")
            uids = data[0].split()[-max(1, limit):]
            messages: list[GmailMessage] = []
            for uid in uids:
                status, payload = client.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK" or not payload:
                    continue
                raw = next((part[1] for part in payload if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
                if raw:
                    messages.append(_parse_email(raw, fallback_id=uid.decode("ascii", errors="ignore")))
            return messages
        finally:
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass


class GmailInboxActions:
    """Perform the one narrowly-scoped mailbox action used by email review.

    Gmail's IMAP extension lets us label an exact message as Spam without
    deleting it.  Searching by RFC Message-ID first avoids acting on a vague
    subject or an entire conversation.
    """

    def __init__(self, *, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    def move_to_spam(self, message_id: str) -> tuple[bool, str]:
        if not self.username or not self.password:
            return False, "Gmail IMAP credentials are not configured."
        normalized_id = message_id.strip().strip("<>")
        if not normalized_id:
            return False, "The reminder does not contain a usable Gmail message ID."
        client = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            client.login(self.username, self.password)
            status, _ = client.select("INBOX", readonly=False)
            if status != "OK":
                return False, "Could not open the Gmail inbox."
            status, data = client.uid("search", None, "HEADER", "Message-ID", f"<{normalized_id}>")
            if status != "OK":
                return False, "Could not look up the Gmail message."
            matches = data[0].split() if data and data[0] else []
            if len(matches) != 1:
                return False, "I could not uniquely identify that Gmail message."
            # Gmail labels the message Spam and removes it from Inbox.  This is
            # reversible in Gmail and intentionally does not delete the message.
            status, _ = client.uid("store", matches[0], "+X-GM-LABELS", r"(\\Spam)")
            if status != "OK":
                return False, "Gmail did not accept the Spam move."
            return True, ""
        except (imaplib.IMAP4.error, OSError) as exc:
            return False, f"Gmail IMAP action failed: {type(exc).__name__}."
        finally:
            try:
                client.close()
            except (imaplib.IMAP4.error, OSError):
                pass
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass


class ReminderExtractor:
    def __init__(self, *, timezone: str = "America/New_York") -> None:
        self.timezone = ZoneInfo(timezone)

    def extract(self, message: GmailMessage, *, now: datetime | None = None) -> list[ReminderCandidate]:
        # Relative dates in an email ("tomorrow", "Friday") are relative to when
        # the email was sent, not to whichever day a recurring scan happens.
        reference = message.received_at.astimezone(self.timezone)
        body = sanitize_gmail_body(text=message.text, html=message.html)
        text = "\n".join(part for part in (message.subject.strip(), body) if part)
        candidates: list[ReminderCandidate] = []
        for sentence in _sentences(text):
            if not _ACTION_RE.search(sentence):
                continue
            due = _extract_due_at(sentence, reference, self.timezone)
            if due is None:
                continue
            summary = _summary(message.subject, sentence)
            digest = hashlib.sha256(
                f"{message.message_id}\0{summary}\0{' '.join(sentence.casefold().split())}".encode()
            ).hexdigest()[:24]
            candidates.append(
                ReminderCandidate(
                    candidate_id=digest,
                    message_id=message.message_id,
                    thread_id=message.thread_id,
                    sender=message.sender,
                    subject=message.subject,
                    summary=summary,
                    due_at=due,
                    received_at=message.received_at,
                    evidence=sentence[:500],
                )
            )
        return list({item.candidate_id: item for item in candidates}.values())


class ReminderStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS reminder_candidates (
                    candidate_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    sender TEXT NOT NULL, subject TEXT NOT NULL, summary TEXT NOT NULL,
                    due_at TEXT NOT NULL, received_at TEXT NOT NULL, evidence TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
                )"""
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(reminder_candidates)").fetchall()
            }
            if "notified_at" not in columns:
                connection.execute("ALTER TABLE reminder_candidates ADD COLUMN notified_at TEXT")
            if "resolved_at" not in columns:
                connection.execute("ALTER TABLE reminder_candidates ADD COLUMN resolved_at TEXT")
            if "resolution_note" not in columns:
                connection.execute("ALTER TABLE reminder_candidates ADD COLUMN resolution_note TEXT")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS reminder_suppressions (
                    pattern TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TEXT NOT NULL
                )"""
            )

    def add(self, candidate: ReminderCandidate) -> bool:
        if self.is_suppressed(candidate):
            return False
        with self._connect() as connection:
            existing = connection.execute(
                """SELECT 1 FROM reminder_candidates
                WHERE message_id = ? AND summary = ? AND evidence = ? LIMIT 1""",
                (candidate.message_id, candidate.summary, candidate.evidence),
            ).fetchone()
            if existing is not None:
                return False
            cursor = connection.execute(
                """INSERT OR IGNORE INTO reminder_candidates
                (candidate_id, message_id, thread_id, sender, subject, summary, due_at, received_at, evidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*candidate.to_dict().values(), datetime.now(UTC).isoformat()),
            )
            return cursor.rowcount == 1

    def add_suppression(self, pattern: str, *, reason: str = "") -> bool:
        normalized = " ".join(pattern.casefold().split())[:200]
        if len(normalized) < 3:
            raise ValueError("suppression pattern must contain at least 3 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO reminder_suppressions (pattern, reason, created_at)
                VALUES (?, ?, ?)""",
                (normalized, reason.strip()[:500], datetime.now(UTC).isoformat()),
            )
            return cursor.rowcount == 1

    def list_suppressions(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT pattern, reason, created_at FROM reminder_suppressions ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def is_suppressed(self, candidate: ReminderCandidate) -> bool:
        searchable = " ".join((candidate.sender, candidate.subject, candidate.summary)).casefold()
        return any(item["pattern"] in searchable for item in self.list_suppressions())

    def list_pending(self, *, limit: int = 50, due_before: datetime | None = None) -> list[dict[str, str]]:
        query = "SELECT * FROM reminder_candidates WHERE status = 'pending'"
        values: list[object] = []
        if due_before is not None:
            query += " AND due_at <= ?"
            values.append(due_before.isoformat())
        query += " ORDER BY due_at ASC LIMIT ?"
        values.append(max(1, min(limit, 200)))
        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def list_unnotified(self, *, limit: int = 50) -> list[dict[str, str | None]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM reminder_candidates
                WHERE status = 'pending' AND notified_at IS NULL
                ORDER BY due_at ASC LIMIT ?""",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def mark_notified(self, candidate_ids: list[str], *, notified_at: datetime | None = None) -> int:
        ids = list(dict.fromkeys(value for value in candidate_ids if value))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        timestamp = (notified_at or datetime.now(UTC)).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE reminder_candidates SET notified_at = ? "
                f"WHERE notified_at IS NULL AND candidate_id IN ({placeholders})",
                [timestamp, *ids],
            )
            return cursor.rowcount

    def set_status(self, candidate_id: str, status: str) -> bool:
        if status not in {"pending", "accepted", "completed", "dismissed"}:
            raise ValueError("status must be pending, accepted, completed, or dismissed")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE reminder_candidates SET status = ? WHERE candidate_id = ?",
                (status, candidate_id),
            )
            return cursor.rowcount == 1

    def resolve(self, candidate_id: str, *, status: str = "completed", note: str = "") -> bool:
        if status not in {"completed", "dismissed"}:
            raise ValueError("resolved reminder status must be completed or dismissed")
        with self._connect() as connection:
            target = connection.execute(
                "SELECT message_id, summary, evidence FROM reminder_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if target is None:
                return False
            cursor = connection.execute(
                """UPDATE reminder_candidates
                SET status = ?, resolved_at = ?, resolution_note = ?
                WHERE message_id = ? AND summary = ? AND evidence = ?
                AND status IN ('pending', 'accepted')""",
                (
                    status, datetime.now(UTC).isoformat(), note.strip()[:500],
                    target["message_id"], target["summary"], target["evidence"],
                ),
            )
            return cursor.rowcount >= 1


class EmailReminderScanner:
    def __init__(self, source: InboxSource, store: ReminderStore, extractor: ReminderExtractor | None = None) -> None:
        self.source = source
        self.store = store
        self.extractor = extractor or ReminderExtractor()

    def scan(self, *, lookback_days: int = 7, limit: int = 100, unread_only: bool = False, now: datetime | None = None) -> dict[str, object]:
        reference = now or datetime.now(UTC)
        messages = self.source.fetch_recent(
            since=reference.date() - timedelta(days=max(0, lookback_days)),
            limit=max(1, limit),
            unread_only=unread_only,
        )
        found = added = 0
        for message in messages:
            for candidate in self.extractor.extract(message, now=reference):
                found += 1
                added += int(self.store.add(candidate))
        return {"messages_scanned": len(messages), "candidates_found": found, "candidates_added": added}


def _parse_email(raw: bytes, *, fallback_id: str) -> GmailMessage:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    text, html = _message_bodies(message)
    received = parsedate_to_datetime(message.get("Date")) if message.get("Date") else datetime.now(UTC)
    if received.tzinfo is None:
        received = received.replace(tzinfo=UTC)
    message_id = str(message.get("Message-ID") or fallback_id).strip(" <>")
    thread_id = str(message.get("X-GM-THRID") or message.get("References") or message_id).split()[-1].strip(" <>")
    return GmailMessage(
        message_id=message_id,
        thread_id=thread_id,
        sender=parseaddr(str(message.get("From") or ""))[1],
        recipients=[address for _, address in [parseaddr(str(message.get("To") or ""))] if address],
        subject=str(message.get("Subject") or ""),
        text=text,
        html=html,
        received_at=received,
    )


def _message_bodies(message: Message) -> tuple[str, str | None]:
    plain: list[str] = []
    html: list[str] = []
    parts = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            continue
        if not isinstance(content, str):
            continue
        (plain if content_type == "text/plain" else html).append(content)
    return "\n".join(plain), "\n".join(html) or None


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?:\r?\n)+|(?<=[.!?])\s+", text) if part.strip()]


def _summary(subject: str, sentence: str) -> str:
    value = subject.strip() or sentence.strip()
    value = re.sub(r"^(?:re|fwd?):\s*", "", value, flags=re.IGNORECASE)
    return " ".join(value.split())[:160]


def _extract_due_at(text: str, reference: datetime, timezone: ZoneInfo) -> datetime | None:
    lowered = text.lower()
    target: date | None = None
    if "tomorrow" in lowered:
        target = reference.date() + timedelta(days=1)
    elif "today" in lowered or "tonight" in lowered:
        target = reference.date()
    else:
        weekday_match = re.search(r"\b(?:this |next )?(" + "|".join(_WEEKDAYS) + r")\b", lowered)
        if weekday_match:
            wanted = _WEEKDAYS[weekday_match.group(1)]
            days = (wanted - reference.weekday()) % 7
            if days == 0 or weekday_match.group(0).startswith("next "):
                days += 7
            target = reference.date() + timedelta(days=days)
    if target is None:
        for pattern in _DATE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            groups = match.groupdict()
            year_text = groups.get("year")
            year = int(year_text) if year_text else reference.year
            if year < 100:
                year += 2000
            month = int(groups["month"]) if groups.get("month") else _MONTHS[groups["month_name"].lower()]
            try:
                target = date(year, month, int(groups["day"]))
                if not year_text and target < reference.date() - timedelta(days=1):
                    target = target.replace(year=target.year + 1)
            except ValueError:
                return None
            break
    if target is None:
        return None
    hour, minute = (20, 0) if "tonight" in lowered else (9, 0)
    time_match = _TIME_RE.search(text)
    if time_match:
        hour = int(time_match.group("hour")) % 12
        if time_match.group("ampm").lower().startswith("p"):
            hour += 12
        minute = int(time_match.group("minute") or 0)
    return datetime.combine(target, time(hour, minute), tzinfo=timezone)
