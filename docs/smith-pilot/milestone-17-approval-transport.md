# Milestone 17: Persistent Agent Smith Approval Transport

## Overview

This milestone adds a persistent, auditable approval transport for Agent Smith
write-pilot actions.  It enables creating, reviewing, resolving, and resuming
approval-gated write-pilot requests without enabling Smith or performing any
live write.

The transport is intentionally conservative:

* approvals are explicit, request-specific, action-specific, path-specific, and
  single-use;
* content hashes and commit-message hashes are stored, never raw content,
  secrets, or environment values;
* all admin endpoints are loopback-only by default;
* Agent Smith and the write pilot remain disabled by default.

## Approval lifecycle

```text
pending → approved → consumed
pending → denied
pending → expired
pending → cancelled
```

1. A write-pilot run creates one pending approval record per gate
   (`path`, `content`, `stage`, `commit`).
2. The run halts at the first gate that is not yet approved and returns an
   `awaiting_*_approval` state plus the pending `approval_id`.
3. An operator inspects the pending approval and either approves or denies it.
4. The caller resumes the write-pilot run with the `request_id` and the
   `approval_id` for the next gate.
5. The runtime consumes each approved approval exactly once and continues until
   the next awaiting gate or successful completion.
6. Denied, expired, cancelled, mismatched, or already-consumed approvals cause
   the run to stop safely and roll back if a write has already occurred.

## Database schema

File: outside the repository under the user state directory, defaulting to
`~/.local/state/freyja/smith-approvals.sqlite3` on macOS/Linux
(`%LOCALAPPDATA%\freyja\smith-approvals.sqlite3` is recommended on Windows).
Configurable via `AGENT_SMITH_APPROVAL_DB_PATH`.

```sql
CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_path TEXT NOT NULL,
    content_hash TEXT,
    commit_message_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    denial_reason TEXT,
    consumed_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(request_id, action)
);

CREATE INDEX idx_approvals_request_id ON approvals(request_id);
CREATE INDEX idx_approvals_status ON approvals(status);
CREATE INDEX idx_approvals_expires_at ON approvals(expires_at);
```

* `status` is one of `pending`, `approved`, `denied`, `expired`, `consumed`,
  `cancelled`.
* `UNIQUE(request_id, action)` prevents duplicate pending approvals for the
  same gate.
* Conditional `UPDATE ... WHERE status = ?` statements prevent double approval,
  double denial, and double consumption.
* `PRAGMA journal_mode = WAL` is enabled for safe concurrent readers.
* The database file is created with mode `0o600` where the OS allows it.
* The parent state directory is created with mode `0o700` where the OS allows it.

## Runtime resume flow

1. `SmithRuntime.run_write_pilot_with_provider(...)` creates pending records and
   halts at the first unapproved gate.
2. `SmithRuntime.resume_write_pilot(request_id, approval_id, ...)` builds a
   gate-aware resume callback.
3. The callback queries the store by `(request_id, action)`:
   * already-consumed records for the gate return `approved=True` so the run
     can skip completed gates;
   * approved-but-not-yet-consumed records are consumed exactly once and return
     `approved=True`;
   * pending or missing records return `approved=False` and the run stops at
     the awaiting gate.
4. If any step after writing fails, the original file state is restored and
   the approved target is unstaged; unrelated working-tree state is untouched.

## API endpoints

All approval-admin endpoints require loopback origin unless
`AGENT_SMITH_APPROVAL_LOOPBACK_ONLY` is set to `false`.

| Method | Path | Behavior |
|--------|------|----------|
| POST | `/agents/smith/write-pilot` | Create a write-pilot request and pending approvals. Returns awaiting state and pending approval IDs. 404 if Smith disabled; 403 if write pilot disabled. |
| GET | `/agents/smith/approvals` | List pending approvals. |
| GET | `/agents/smith/approvals/{approval_id}` | Inspect one approval. 404 if unknown. |
| POST | `/agents/smith/approvals/{approval_id}/approve` | Approve a pending approval. 409 if already resolved. |
| POST | `/agents/smith/approvals/{approval_id}/deny` | Deny a pending approval with optional reason. 409 if already resolved. |
| POST | `/agents/smith/write-pilot/resume` | Resume a write-pilot run after an approval. 404/403 as above; 409 for payload mismatches; 409/410 for resolved/expired/mismatched approvals. |

The resume endpoint validates the supplied payload against the persisted
approval context before invoking the runtime.  Mismatches in `request_id`,
`target_path`, proposed-content hash, or commit-message hash return HTTP 409
without exposing hashes, contents, or filesystem paths.

Validation responses never include proposed content, secrets, or unnecessary
filesystem details.

## Loopback-only administrative guard

By default `agent_smith_approval_loopback_only = True`.  The guard resolves
`request.client.host` with `ipaddress.ip_address(...).is_loopback` and rejects
any non-loopback address.  It accepts any valid loopback address in the
`127.0.0.0/8` range and `::1`.  It does not trust `X-Forwarded-For`,
`Forwarded`, hostnames, or the literal string `localhost`.  Malformed or
missing client addresses are denied.  Disabling the guard requires explicitly
setting `AGENT_SMITH_APPROVAL_LOOPBACK_ONLY=false`.

## Concurrency controls

* Database transactions wrap approve/deny/consume/cancel operations.
* Conditional `UPDATE ... WHERE status = ?` guarantees only one caller can
  transition a record from `pending` to `approved`, `denied`, or `consumed`.
* The store exposes `cleanup_expired()` to transition stale pending records to
  `expired`.
* `secrets.compare_digest` is used for hash/token comparisons.

## Expiration behavior

Approvals expire after `AGENT_SMITH_APPROVAL_TTL_SECONDS` (default 900).
Attempting to approve or consume an expired pending approval transitions it to
`expired` and returns HTTP `410 Gone` where appropriate.

## Recovery behavior

* If a write-pilot run is interrupted, resuming with the next approved
  `approval_id` skips already-consumed gates and continues from the awaiting
  gate.
* If an approval is denied after a write, the file is rolled back and the
  target is unstaged, but the reported state remains at the awaiting gate where
  the denial occurred.
* Audit records are sanitized; proposed content and secrets are never persisted.

## Operator procedure

1. Verify `agent_smith_enabled` and `agent_smith_write_pilot_enabled` are both
   `True` in `src/freyja/config.py` (or via environment, but do not do this for
   a live pilot until all gates are validated).
2. POST `/agents/smith/write-pilot` with the planned change.
3. Inspect pending approvals with GET `/agents/smith/approvals`.
4. Approve each gate only after reviewing the exact target path, content hash,
   and commit message.
5. Resume the run with POST `/agents/smith/write-pilot/resume` after each
   approval.
6. Verify the repository state independently before treating the pilot as
   complete.

## Conditions required before live activation

* Agent Smith read-only and dry-run modes must be verified in production.
* A production authentication mechanism must replace or supplement the loopback
  guard.
* Audit log delivery, backup, and retention must be operational.
* Operator runbooks must exist for denial, expiration, rollback, and incident
  response.
* The write-pilot sandbox must be configured and protected.
* All stakeholders must sign off on the approval workflow and threat model.

## Threat model

| Threat | Control |
|--------|---------|
| Approval reuse | `request_id`/`action` uniqueness and single-use `consumed` status. |
| Cross-request approval | `consume` validates `request_id`, `action`, `target_path`, hashes. |
| Tampered content/commit | content and commit-message hashes compared with constant-time digest. |
| Secret leakage | proposed content, API keys, and env values never stored in the approval DB or audit records. |
| Unauthorized admin access | loopback-only guard; no forwarded-header trust. |
| Concurrent double-approval | conditional SQL updates and transactions. |
| Expired approvals | TTL and explicit expiration handling. |
| Sandbox escape | unchanged Milestone 16 path validation; repo root resolved before containment checks. |

## Files introduced or changed

* `src/freyja/agents/approval_store.py` — SQLite store.
* `src/freyja/agents/approval_provider.py` — persistent provider and resume callback.
* `src/freyja/agents/models.py` — `ApprovalRecord`, `ApprovalRecordStatus`,
  `ApprovalStoreError`, `WritePilotResultWithApprovals`.
* `src/freyja/agents/runtime.py` — provider-aware runtime and resume methods.
* `src/freyja/agents/__init__.py` — exports.
* `src/freyja/main.py` — new API endpoints and loopback guard.
* `src/freyja/config.py` — new settings.
* `tests/test_agent_smith_approval_store.py` — store/provider/runtime tests.
* `tests/test_agent_smith_write_pilot.py` — additional endpoint tests.
* `docs/smith-pilot/milestone-17-approval-transport.md` — this document.
