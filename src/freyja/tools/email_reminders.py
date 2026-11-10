from __future__ import annotations

import asyncio
from datetime import datetime

from connectors.gmail.config import settings as gmail_settings
from connectors.gmail.reminders import GmailInboxActions, ReminderStore
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


async def _list_email_reminders(request: ToolExecutionRequest) -> dict:
    person = request.metadata.get("person") if isinstance(request.metadata.get("person"), dict) else {}
    person_id = str(person.get("person_id") or "").strip().lower()
    owner = gmail_settings.gmail_inbox_owner.strip().lower()
    if not owner or person_id != owner:
        return {"reminders": [], "count": 0, "error": "Email reminder access is limited to the inbox owner."}
    args = request.arguments or {}
    limit = int(args.get("limit", 20))
    due_before = datetime.fromisoformat(args["due_before"]) if args.get("due_before") else None
    reminders = ReminderStore(gmail_settings.gmail_reminder_store_path).list_pending(
        limit=limit,
        due_before=due_before,
    )
    return {"reminders": reminders, "count": len(reminders)}


def _is_inbox_owner(request: ToolExecutionRequest) -> bool:
    person = request.metadata.get("person") if isinstance(request.metadata.get("person"), dict) else {}
    person_id = str(person.get("person_id") or "").strip().lower()
    owner = gmail_settings.gmail_inbox_owner.strip().lower()
    return bool(owner and person_id == owner)


async def _resolve_email_reminder(request: ToolExecutionRequest) -> dict:
    if not _is_inbox_owner(request):
        return {"resolved": False, "error": "Email reminder access is limited to the inbox owner."}
    args = request.arguments or {}
    candidate_id = str(args.get("candidate_id") or "").strip()
    status = str(args.get("status") or "completed").strip().lower()
    note = str(args.get("note") or "").strip()
    resolved = ReminderStore(gmail_settings.gmail_reminder_store_path).resolve(
        candidate_id,
        status=status,
        note=note,
    )
    return {
        "resolved": resolved,
        "candidate_id": candidate_id,
        "status": status if resolved else None,
        "message": "I will no longer remind you about this." if resolved else "That active reminder was not found.",
    }


async def _apply_email_reminder_feedback(request: ToolExecutionRequest) -> dict:
    if not _is_inbox_owner(request):
        return {"updated": 0, "suppressed": 0, "error": "Email reminder access is limited to the inbox owner."}
    args = request.arguments or {}
    store = ReminderStore(gmail_settings.gmail_reminder_store_path)
    results = []
    for update in args.get("updates", []):
        candidate_id = str(update.get("candidate_id") or "").strip()
        status = str(update.get("status") or "completed").strip().lower()
        note = str(update.get("note") or "").strip()
        resolved = store.resolve(candidate_id, status=status, note=note)
        results.append({"candidate_id": candidate_id, "status": status, "resolved": resolved})
    suppressions = []
    reason = str(args.get("reason") or "Inbox owner feedback").strip()
    for pattern in args.get("suppress_subject_patterns", []):
        normalized = str(pattern).strip()
        if normalized:
            suppressions.append({"pattern": normalized, "added": store.add_suppression(normalized, reason=reason)})
    return {
        "updated": sum(1 for item in results if item["resolved"]),
        "results": results,
        "suppressed": sum(1 for item in suppressions if item["added"]),
        "suppressions": suppressions,
    }


async def _mark_email_reminder_junk(request: ToolExecutionRequest) -> dict:
    """Move one confirmed reminder source message to Gmail Spam, never delete."""
    if not _is_inbox_owner(request):
        return {"moved": False, "error": "Email reminder access is limited to the inbox owner."}
    if not gmail_settings.gmail_inbox_actions_enabled:
        return {"moved": False, "error": "Gmail mailbox actions are disabled."}
    candidate_id = str((request.arguments or {}).get("candidate_id") or "").strip()
    store = ReminderStore(gmail_settings.gmail_reminder_store_path)
    candidate = next(
        (item for item in store.list_pending(limit=200) if item["candidate_id"] == candidate_id),
        None,
    )
    if candidate is None:
        return {"moved": False, "error": "That active email reminder was not found."}
    moved, error = await asyncio.to_thread(
        GmailInboxActions(
            host=gmail_settings.gmail_imap_host,
            port=gmail_settings.gmail_imap_port,
            username=gmail_settings.gmail_imap_username,
            password=gmail_settings.gmail_inbox_password,
        ).move_to_spam,
        str(candidate["message_id"]),
    )
    if not moved:
        return {"moved": False, "candidate_id": candidate_id, "error": error}
    store.resolve(candidate_id, status="dismissed", note="Inbox owner marked this email as junk.")
    return {
        "moved": True,
        "candidate_id": candidate_id,
        "message": "Moved the exact email to Gmail Spam and dismissed its reminder.",
    }


def register_email_reminder_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="email_reminder_candidates",
            description="List pending reminder candidates extracted from the account owner's email inbox.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "due_before": {"type": "string", "description": "Optional ISO datetime cutoff."},
                },
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.READ_ONLY,
            required_permission="personal:email.read",
            tags=["email", "reminders", "read-only"],
        ),
        _list_email_reminders,
    )
    registry.register(
        ToolDefinition(
            name="email_reminder_resolve",
            description=(
                "Mark one active email reminder completed or dismissed after the inbox owner says "
                "they handled it, paid it, finished it, or no longer want reminders. First use "
                "email_reminder_candidates to identify the matching candidate_id."
            ),
            input_schema={
                "type": "object",
                "required": ["candidate_id", "status"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["completed", "dismissed"]},
                    "note": {"type": "string", "description": "What the owner said was done or dismissed."},
                },
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            required_permission="personal:email.write",
            tags=["email", "reminders", "write"],
        ),
        _resolve_email_reminder,
    )
    registry.register(
        ToolDefinition(
            name="email_reminder_apply_feedback",
            description=(
                "Apply the inbox owner's feedback to several active email reminders at once. "
                "Use candidate IDs from email_reminder_candidates. Mark handled items completed, "
                "unwanted items dismissed, and save narrow subject phrases in "
                "suppress_subject_patterns only when the owner says never or always."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["candidate_id", "status"],
                            "properties": {
                                "candidate_id": {"type": "string"},
                                "status": {"type": "string", "enum": ["completed", "dismissed"]},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "suppress_subject_patterns": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            required_permission="personal:email.write",
            tags=["email", "reminders", "feedback", "write"],
        ),
        _apply_email_reminder_feedback,
    )
    registry.register(
        ToolDefinition(
            name="email_reminder_mark_junk",
            description=(
                "Move one exact pending email-reminder source message to Gmail Spam after the inbox owner "
                "explicitly calls it junk or spam. First use email_reminder_candidates to identify the candidate. "
                "This never deletes mail or creates a broad sender rule."
            ),
            input_schema={
                "type": "object",
                "required": ["candidate_id"],
                "properties": {"candidate_id": {"type": "string"}},
            },
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            required_permission="personal:email.write",
            confirmation_policy="explicit_owner_request_required",
            tags=["email", "gmail", "spam", "junk", "write"],
        ),
        _mark_email_reminder_junk,
    )
