from __future__ import annotations

from datetime import UTC, datetime

from connectors.gmail.models import GmailMessage
from connectors.gmail.reminders import EmailReminderScanner, ReminderExtractor, ReminderStore
from freyja.tools.email_reminders import register_email_reminder_tools
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry
from connectors.signal.reminder_notifier import EmailReminderNotifier
from connectors.signal.reminder_feedback import ReminderFeedbackProcessor


def _message(*, message_id: str = "message-1", subject: str = "School form", text: str = "") -> GmailMessage:
    return GmailMessage(
        message_id=message_id,
        thread_id="thread-1",
        sender="school@example.com",
        recipients=["joe@example.com"],
        subject=subject,
        text=text,
        received_at=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )


def test_extractor_finds_explicit_action_and_deadline() -> None:
    extractor = ReminderExtractor(timezone="America/New_York")

    reminders = extractor.extract(
        _message(text="Please submit the permission form by October 23 at 4:30 PM."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )

    assert len(reminders) == 1
    assert reminders[0].summary == "School form"
    assert reminders[0].due_at.isoformat() == "2026-10-23T16:30:00-04:00"
    assert "submit the permission form" in reminders[0].evidence


def test_extractor_ignores_dates_without_an_action() -> None:
    extractor = ReminderExtractor()

    reminders = extractor.extract(
        _message(subject="Newsletter", text="Our office opened on October 23, 2020."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )

    assert reminders == []


def test_store_deduplicates_and_tracks_review_status(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    candidate = ReminderExtractor().extract(
        _message(text="Reminder: renew the registration by 2026-10-25."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]

    assert store.add(candidate) is True
    assert store.add(candidate) is False
    assert [item["candidate_id"] for item in store.list_pending()] == [candidate.candidate_id]
    assert store.set_status(candidate.candidate_id, "dismissed") is True
    assert store.list_pending() == []


def test_store_resolves_completed_reminder_with_note(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    candidate = ReminderExtractor().extract(
        _message(text="Please pay the invoice by tomorrow at 9 AM."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]
    store.add(candidate)

    assert store.resolve(candidate.candidate_id, note="Joe said the bill was paid.") is True
    assert store.list_pending() == []
    assert store.resolve(candidate.candidate_id) is False


def test_store_suppression_blocks_future_matching_candidates(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    store.add_suppression("card member newsletter", reason="Owner said never remind")
    candidate = ReminderExtractor().extract(
        _message(subject="Your Card Member Newsletter", text="Reminder: review this by 2026-10-25."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]

    assert store.is_suppressed(candidate) is True
    assert store.add(candidate) is False
    assert store.list_pending() == []


def test_scanner_reports_new_and_existing_candidates(tmp_path) -> None:
    class FakeInbox:
        def fetch_recent(self, *, since, limit, unread_only=False):
            return [_message(text="Please pay the invoice by tomorrow at 9 AM.")]

    scanner = EmailReminderScanner(FakeInbox(), ReminderStore(tmp_path / "reminders.sqlite3"))
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)

    first = scanner.scan(now=now)
    second = scanner.scan(now=now)

    assert first == {"messages_scanned": 1, "candidates_found": 1, "candidates_added": 1}
    assert second == {"messages_scanned": 1, "candidates_found": 1, "candidates_added": 0}


def test_relative_due_date_is_stable_across_daily_scans(tmp_path) -> None:
    message = _message(text="Please complete AP testing tomorrow at 9 AM.")

    class FakeInbox:
        def fetch_recent(self, *, since, limit, unread_only=False):
            return [message]

    store = ReminderStore(tmp_path / "reminders.sqlite3")
    scanner = EmailReminderScanner(FakeInbox(), store)
    first = scanner.scan(now=datetime(2026, 10, 18, 12, tzinfo=UTC))
    second = scanner.scan(now=datetime(2026, 10, 21, 12, tzinfo=UTC))

    assert first["candidates_added"] == 1
    assert second["candidates_added"] == 0
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0]["due_at"] == "2026-10-19T09:00:00-04:00"


def test_resolving_candidate_closes_legacy_duplicates(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    extractor = ReminderExtractor()
    message = _message(subject="WFHS - AP Testing Update", text="Please complete AP testing tomorrow at 9 AM.")
    first = extractor.extract(message)[0]
    store.add(first)
    with store._connect() as connection:
        connection.execute(
            """INSERT INTO reminder_candidates
            (candidate_id, message_id, thread_id, sender, subject, summary, due_at,
             received_at, evidence, status, created_at)
            SELECT 'legacy-duplicate', message_id, thread_id, sender, subject, summary,
             '2026-10-20T09:00:00-04:00', received_at, evidence, 'pending', created_at
            FROM reminder_candidates WHERE candidate_id = ?""",
            (first.candidate_id,),
        )

    assert store.resolve(first.candidate_id, note="AP testing is complete") is True
    assert store.list_pending() == []


async def test_reminder_tool_rejects_a_different_person(monkeypatch, tmp_path) -> None:
    from freyja.tools import email_reminders

    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_inbox_owner", "joe")
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_reminder_store_path", str(tmp_path / "reminders.sqlite3"))
    registry = ToolRegistry(audit_enabled=False)
    register_email_reminder_tools(registry)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="email_reminder_candidates",
            metadata={"director_authorized": True, "person": {"person_id": "beth"}},
        )
    )

    assert result.success is True
    assert result.output["count"] == 0
    assert "inbox owner" in result.output["error"]


async def test_reminder_resolve_tool_stops_future_reminders(monkeypatch, tmp_path) -> None:
    from freyja.tools import email_reminders

    path = tmp_path / "reminders.sqlite3"
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_inbox_owner", "joe")
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_reminder_store_path", str(path))
    store = ReminderStore(path)
    candidate = ReminderExtractor().extract(
        _message(text="Please pay the invoice by tomorrow at 9 AM."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]
    store.add(candidate)
    registry = ToolRegistry(audit_enabled=False)
    register_email_reminder_tools(registry)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="email_reminder_resolve",
            arguments={"candidate_id": candidate.candidate_id, "status": "completed", "note": "Bill paid"},
            metadata={"director_authorized": True, "person": {"person_id": "joe"}},
        )
    )

    assert result.success is True
    assert result.output["resolved"] is True
    assert store.list_pending() == []


async def test_reminder_feedback_tool_updates_batch_and_learns_suppression(monkeypatch, tmp_path) -> None:
    from freyja.tools import email_reminders

    path = tmp_path / "reminders.sqlite3"
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_inbox_owner", "joe")
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_reminder_store_path", str(path))
    store = ReminderStore(path)
    candidate = ReminderExtractor().extract(
        _message(text="Please pay the invoice by tomorrow at 9 AM."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]
    store.add(candidate)
    registry = ToolRegistry(audit_enabled=False)
    register_email_reminder_tools(registry)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="email_reminder_apply_feedback",
            arguments={
                "updates": [{"candidate_id": candidate.candidate_id, "status": "completed", "note": "Paid"}],
                "suppress_subject_patterns": ["card member newsletter"],
                "reason": "Owner does not want these reminders",
            },
            metadata={"director_authorized": True, "person": {"person_id": "joe"}},
        )
    )

    assert result.success is True
    assert result.output["updated"] == 1
    assert result.output["suppressed"] == 1
    assert store.list_pending() == []
    assert store.list_suppressions()[0]["pattern"] == "card member newsletter"


async def test_mark_junk_moves_only_the_identified_message_and_dismisses_candidate(monkeypatch, tmp_path) -> None:
    from freyja.tools import email_reminders

    path = tmp_path / "reminders.sqlite3"
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_inbox_owner", "joe")
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_reminder_store_path", str(path))
    monkeypatch.setattr(email_reminders.gmail_settings, "gmail_inbox_actions_enabled", True)
    candidate = ReminderExtractor().extract(
        _message(message_id="source-message@example.com", text="Please pay the invoice by tomorrow at 9 AM."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]
    store = ReminderStore(path)
    store.add(candidate)
    moved_ids = []

    class FakeActions:
        def __init__(self, **_kwargs):
            pass

        def move_to_spam(self, message_id):
            moved_ids.append(message_id)
            return True, ""

    monkeypatch.setattr(email_reminders, "GmailInboxActions", FakeActions)
    registry = ToolRegistry(audit_enabled=False)
    register_email_reminder_tools(registry)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="email_reminder_mark_junk",
            arguments={"candidate_id": candidate.candidate_id},
            metadata={"director_authorized": True, "person": {"person_id": "joe"}},
        )
    )

    assert result.success is True
    assert result.output["moved"] is True
    assert moved_ids == ["source-message@example.com"]
    assert store.list_pending() == []


async def test_signal_notifier_sends_one_digest_and_marks_candidates(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    extractor = ReminderExtractor()
    for index, text in enumerate((
        "Please submit the form by 2026-10-25.",
        "Reminder: renew the registration by 2026-10-26.",
    )):
        store.add(extractor.extract(_message(message_id=f"message-{index}", text=text),
                                    now=datetime(2026, 10, 18, 12, tzinfo=UTC))[0])

    class FakeTransport:
        def __init__(self):
            self.responses = []

        async def send(self, response):
            self.responses.append(response)

    transport = FakeTransport()
    notifier = EmailReminderNotifier(store=store, transport=transport, recipient="+15551234567")

    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    first = await notifier.dispatch_pending()
    second = await notifier.dispatch_pending()

    assert first == {"sent": True, "candidate_count": 2, "marked_notified": 2}
    assert second == {"sent": False, "candidate_count": 0, "marked_notified": 0}
    assert len(transport.responses) == 1
    assert transport.responses[0].recipient == "+15551234567"
    assert "Want me to help with any of these?" in transport.responses[0].text


async def test_signal_failure_leaves_candidates_unnotified(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    candidate = ReminderExtractor().extract(
        _message(text="Please pay the invoice by tomorrow at 9 AM."),
        now=datetime(2026, 10, 18, 12, tzinfo=UTC),
    )[0]
    store.add(candidate)

    class FailingTransport:
        async def send(self, response):
            raise RuntimeError("delivery unavailable")

    notifier = EmailReminderNotifier(store=store, transport=FailingTransport(), recipient="+15551234567")

    import pytest
    with pytest.raises(RuntimeError, match="delivery unavailable"):
        await notifier.dispatch_pending()

    assert [item["candidate_id"] for item in store.list_unnotified()] == [candidate.candidate_id]


def test_signal_feedback_applies_multiple_updates_and_learns(tmp_path) -> None:
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    extractor = ReminderExtractor()
    messages = (
        _message(message_id="dumpster", subject="North Point Dumpster: Pick Up Reminder", text="Reminder: pickup by 2026-10-25."),
        _message(message_id="ap", subject="WFHS - AP Testing Update", text="Please complete AP testing by 2026-10-26."),
        _message(message_id="card", subject="Your Card Member newsletter", text="Reminder: review by 2026-10-27."),
        GmailMessage(message_id="ebay", thread_id="ebay", sender="ebay@ebay.com", recipients=["joe@example.com"],
                     subject="Action needed: Update account details", text="Please update account details by 2026-10-28.",
                     received_at=datetime(2026, 10, 18, 12, tzinfo=UTC)),
    )
    for message in messages:
        store.add(extractor.extract(message, now=datetime(2026, 10, 18, 12, tzinfo=UTC))[0])

    result = ReminderFeedbackProcessor(store).apply(
        "Dumpster is picked up. AP testing is taken care of. "
        "I don’t need reminders of a card member newsletter ever. And I took care of the eBay issue"
    )

    assert result.handled is True
    assert len(result.updated) == 4
    assert {item["status"] for item in result.updated} == {"completed", "dismissed"}
    assert result.unmatched == []
    assert result.suppressions == ["card member newsletter"]
    assert len(store.list_pending()) == 0
