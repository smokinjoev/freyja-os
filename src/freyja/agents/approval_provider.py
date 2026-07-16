"""Persistent approval provider for Agent Smith write-pilot actions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any, Awaitable, Callable

from .approval_store import SmithApprovalStore
from .models import ApprovalCallback, ApprovalRecordStatus, ApprovalStoreError


class PersistentApprovalProvider:
    """Approval provider that persists requests to the SQLite approval store.

    The provider has two modes of use:

    1. ``request_approval`` creates a pending approval record and returns a
       token indicating the request is awaiting operator review.  It never
       blocks; the caller (the write-pilot runtime) treats an unresolved
       pending approval as a deny and stops in the awaiting state.

    2. ``resume_approval`` looks up a previously created pending or approved
       record, validates all guarded fields with constant-time comparison,
       consumes approved approvals exactly once, and returns an
       ``ApprovalCallback`` token.

    No proposed content, secrets, API keys, or environment values are stored.
    Only content hashes and commit-message hashes are recorded.
    """

    def __init__(self, store: SmithApprovalStore | None = None) -> None:
        self._store = store or SmithApprovalStore()
        self._store.initialize()

    @property
    def store(self) -> SmithApprovalStore:
        return self._store

    async def request_approval(
        self,
        approval_type: str,
        request_id: str,
        context: dict[str, Any],
    ) -> ApprovalCallback:
        """Create a pending approval and return a non-approved callback token."""
        target_path = context.get("target_path") or ""
        content = context.get("content")
        commit_message = context.get("commit_message")
        summary = context.get("summary") or f"{approval_type} approval for {request_id}"
        # Only path and content approvals validate the proposed payload.  Stage
        # and commit approvals reuse the hashes recorded for content approval.
        if approval_type == "path":
            record_content_hash = self._hash(content) if content is not None else None
            record_commit_message_hash = self._hash(commit_message) if commit_message is not None else None
        elif approval_type == "content":
            record_content_hash = self._hash(content) if content is not None else None
            record_commit_message_hash = self._hash(commit_message) if commit_message is not None else None
        else:
            record_content_hash = None
            record_commit_message_hash = None
        try:
            self._store.create(
                request_id=request_id,
                action=approval_type,
                target_path=target_path,
                content_hash=record_content_hash,
                commit_message_hash=record_commit_message_hash,
                summary=summary,
            )
        except ApprovalStoreError:
            # A record already exists for this gate; return an existing-await token.
            pass
        return ApprovalCallback(
            approval_type=approval_type,
            request_id=request_id,
            approved=False,
            target_path=target_path,
            commit_message=commit_message,
        )

    async def resume_approval(
        self,
        approval_id: str,
        approval_type: str,
        request_id: str,
        context: dict[str, Any],
        *,
        actor: str = "agent_smith",
    ) -> ApprovalCallback:
        """Resume using a specific approval record.

        Mostly kept for backwards compatibility; prefer
        ``resume_approval_for_request`` for gate-aware resume.
        """
        return await self.resume_approval_for_request(
            approval_type=approval_type,
            request_id=request_id,
            context=context,
            actor=actor,
            approval_id=approval_id,
        )

    async def resume_approval_for_request(
        self,
        approval_type: str,
        request_id: str,
        context: dict[str, Any],
        *,
        actor: str = "agent_smith",
        approval_id: str | None = None,
    ) -> ApprovalCallback:
        """Resume a write-pilot run by request and gate.

        For each gate the runtime requests, this method locates the matching
        approval record by ``(request_id, action)``.  If a record has already
        been consumed for this gate, it returns ``approved=True`` so the runtime
        can continue past already-completed gates.  If an approved-but-not-yet-
        consumed record matches the gate (and optionally the supplied
        ``approval_id``), it is consumed exactly once and ``approved=True`` is
        returned.  Otherwise ``approved=False`` is returned and the runtime stops
        at the awaiting gate.

        Changing request_id, action, target_path, content hash, or commit
        message invalidates the match and yields ``approved=False``.
        """
        target_path = context.get("target_path") or ""
        content = context.get("content")
        commit_message = context.get("commit_message")
        content_hash = self._hash(content) if content is not None else None
        commit_message_hash = self._hash(commit_message) if commit_message is not None else None

        all_records = self._store._list_by_request(request_id)
        gate_records = [r for r in all_records if r.action == approval_type]
        consumed = [r for r in gate_records if r.status == ApprovalRecordStatus.CONSUMED]
        if consumed:
            return ApprovalCallback(
                approval_type=approval_type,
                request_id=request_id,
                approved=True,
                target_path=target_path,
                commit_message=commit_message,
            )

        approved = [r for r in gate_records if r.status == ApprovalRecordStatus.APPROVED]
        if not approved:
            return ApprovalCallback(
                approval_type=approval_type,
                request_id=request_id,
                approved=False,
                target_path=target_path,
                commit_message=commit_message,
            )

        record = approved[0]
        if approval_id is not None and record.id != approval_id:
            return ApprovalCallback(
                approval_type=approval_type,
                request_id=request_id,
                approved=False,
                target_path=target_path,
                commit_message=commit_message,
            )

        try:
            consumed_record = self._store.consume(
                approval_id=record.id,
                request_id=request_id,
                action=approval_type,
                target_path=target_path,
                content_hash=content_hash,
                commit_message_hash=commit_message_hash,
                actor=actor,
            )
        except ApprovalStoreError:
            return ApprovalCallback(
                approval_type=approval_type,
                request_id=request_id,
                approved=False,
                target_path=target_path,
                commit_message=commit_message,
            )
        return ApprovalCallback(
            approval_type=approval_type,
            request_id=request_id,
            approved=consumed_record.status == ApprovalRecordStatus.CONSUMED,
            target_path=target_path,
            commit_message=commit_message,
        )

    async def approval_callback(
        self,
        approval_type: str,
        request_id: str,
        context: dict[str, Any],
    ) -> ApprovalCallback:
        """Legacy-compatible callback used by the runtime when no approval_id is supplied.

        This version only *creates* a pending approval; the runtime must later
        call ``resume_approval`` with the operator-supplied ``approval_id`` to
        consume it.  Without an approval_id this callback always returns
        ``approved=False`` so the run halts in the awaiting state.
        """
        return await self.request_approval(approval_type, request_id, context)

    @staticmethod
    def _hash(value: str) -> str:
        """Return a stable SHA-256 hash of ``value`` for comparison."""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def compare_tokens(a: str, b: str) -> bool:
        """Constant-time comparison for hashes/tokens."""
        return secrets.compare_digest(a, b)


def make_resume_callback(
    provider: PersistentApprovalProvider,
    approval_id: str | None = None,
    *,
    actor: str = "agent_smith",
) -> Callable[..., Awaitable[ApprovalCallback]]:
    """Factory for a runtime-compatible callback that resumes a stored approval."""

    async def callback(approval_type: str, request_id: str, context: dict[str, Any]) -> ApprovalCallback:
        return await provider.resume_approval_for_request(
            approval_type=approval_type,
            request_id=request_id,
            context=context,
            actor=actor,
            approval_id=approval_id,
        )

    return callback
