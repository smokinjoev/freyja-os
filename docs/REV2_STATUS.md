# Rev 2 Status

**Date:** 2026-08-25  
**Status:** local implementation candidate; completion audit still active; live account/device onboarding still external

This document is the current evidence trail for `docs/REV2_IMPLEMENTATION_PLAN.md`.
The requirement-by-requirement matrix is `docs/REV2_COMPLETION_AUDIT.md`.
The implementation plan is retained as the original scope; this file records
the current state of that scope.

## Implemented Candidate Scope

- Atlas is documented as the authoritative Director/control plane. Mars remains
  a utility or fallback node, not the current Director target.
- Provider profiles and readiness are modeled through the inference registry.
  Legacy Ollama settings are still accepted through a compatibility profile.
- `/providers/health` exposes Rev 2 provider profile readiness, locality, tier,
  and Iris residency evidence.
- Iris route classification uses a strict structured contract and is advisory.
  Low confidence, unavailable, malformed, or policy-disallowed recommendations
  fall back to Director routing.
- Routing decisions and runtime evidence include provider profile ID, locality,
  selected tier, classifier provider/model/confidence/latency/target/complexity/error,
  provider readiness, time to first token, and normalized provider latency fields.
- MacAgent is modeled as an authenticated Iris boundary. Atlas remains
  responsible for identity, authorization, approval, memory policy, and final
  dispatch decisions.
- Capability evidence records actor, capability, permission, risk, approval
  policy, connector trust, principal/person scope, and approval state.
- External-content workers return structured observations and are prevented by
  default from invoking authoritative memory writes, message send, home control,
  administrative configuration, or privileged execution.
- Shared memory records provenance and trust metadata without a database schema
  migration. Untrusted external observations are not authoritative facts.
- The Rev 2 certification suite covers the 15 required release cases and its
  route requests are validated as executable production route requests after
  certification fixtures are stripped. Every Rev 2 expectation key must be
  declared by the verifier support contract.
- `freyja-certify rev2-readiness` records the live Rev 2 operational evidence
  that unit tests cannot prove: provider-profile health, Iris classifier
  availability, MacAgent authentication and capabilities, and a passing
  timestamped `rev2-vertical-spine` report. It can also bind a benchmark report
  and expected latency-winning target to the readiness artifact before Stage 3
  cutover. The CLI readiness path fails if any final cutover artifact is
  omitted. Connector production-check reports can be attached to prove live
  connector smoke readiness, connector token configuration, and Atlas Director
  targeting. A memory provenance audit report can be attached to prove existing
  shared-memory rows normalize under Rev 2 provenance rules. Approval exercise
  reports can be attached to prove consequential actions deny without approval
  and allow only after Director authorization.
- Heavy local reasoning is treated as an optional provider tier unless the
  readiness command is given `--required-provider-profile heavy_local`.
- Freyja 2.0 live evidence now binds iMessage/terminal route equivalence to the
  QA and iterative-coding suites. The current bundle reports every local gate
  passing with no action items:
  `certification/reports/freyja-live-evidence-summary.json`.

## Verification Evidence

- Focused Rev 2 certification/readiness checks: `30 passed, 1 warning`
- Full project suite after one-command final-handoff consolidation:
  `1100 passed, 2 skipped, 1 warning`
- Local one-command selected-connector readiness bundle: `passed`
- Live local Rev 2 entrypoint check: `freyja.atlas_app:app` starts and serves
  `/health`, `/providers/health`, `/iris-router/health`, `/macagent/health`,
  and `/road` on `127.0.0.1:8767`.
- LaunchAgent readiness bundle with MacAgent and iMessage preflight:
  `certification/reports/20260824T164147.173324Z0000-rev2-readiness.json`
  passed against the actual unattended Director port `127.0.0.1:8000`. The run
  used authenticated Director probes, authenticated MacAgent LaunchAgent health,
  live provider health, memory and approval reports, and read-only iMessage
  production preflight evidence. MacAgent native operation handlers are also
  wired for Apple Calendar, iMessage, Contacts, and Shortcuts, with write/send
  operations requiring Director approval.
- Current LaunchAgent status scripts: `scripts/status-director.sh` reports the
  Director LaunchAgent loaded/running on `127.0.0.1:8000`, `/health` reachable,
  and protected `/providers/health`, `/iris-router/health`, and
  `/macagent/health` checks `OK`; `scripts/status-macagent.sh` reports the
  MacAgent LaunchAgent loaded/running on `127.0.0.1:8765` with authenticated
  health `OK` and the Rev 2 Apple capability families advertised.
- Current iMessage production check:
  `certification/reports/messaging-production-check-imessage-launchagent.json`
  remains read-only and redacted. It reports connector prerequisites present,
  `imsg status` OK, the configured sender not locally known as an iMessage
  handle, and Messages AppleScript timing out.
- iMessage live-smoke dry-run: `scripts/imessage-operator.py live-smoke
  --dry-run` produced an allowlisted one-recipient JSON send plan and sent
  `0` messages. Report:
  `certification/reports/imessage-live-smoke-dry-run.json`.
- Strict readiness with smoke evidence:
  `certification/reports/20260824T165012.276395Z0000-rev2-readiness.json`
  failed only `imessage-live-smoke-report` because the smoke report is a dry-run
  and no real outbound message was sent.
- Strict final-smoke-required readiness:
  `certification/reports/20260824T165923.877188Z0000-rev2-readiness.json`
  passed provider, Iris, MacAgent, certification, latency, connector, memory,
  and approval checks against the running local LaunchAgents, recorded
  `director:health` as the expected latency winner, and failed only
  `imessage-live-smoke-report` because no sent smoke report was supplied.
- Approved iMessage live-smoke attempt:
  `certification/reports/imessage-live-smoke-sent.json` was written with
  `sent: 0`, `failed: 1`, and a timeout error. The iMessage smoke operator now
  resolves the configured `joe=` allowlist alias through authenticated MacAgent
  Contacts, finds Joseph Verant's locally known iMessage phone handle, and
  records that resolution in the smoke plan. The local `imsg send` transport
  still times out even for that locally known handle and for an existing chat id.
  Messages scripting was also checked as a potential fallback, but read-only
  service/chat queries time out in this session. The latest strict readiness
  report,
  `certification/reports/20260825T040632.268989Z0000-rev2-readiness.json`,
  passed every non-smoke check and failed only `imessage-live-smoke-report`
  because the local `imsg` send did not complete.
  Historical note: at this point the local Messages/`imsg` send transport must be corrected before a final live-smoke claim.
- Rev 2 preflight summary:
  `freyja-rev2-preflight-status` is the preferred operator command and reports
  the latest readiness artifact as `ready-for-final-smoke` with exit code `2`,
  meaning every non-smoke check passed and the only remaining proof is the
  approved sent iMessage smoke report. Its remaining-work lines and JSON
  `dry_run_command` and `final_command` fields include the complete
  `scripts/rev2-readiness-bundle.py --imessage-live-smoke` review command and
  the approval-only `--yes` command, populated from the latest readiness
  artifact. Source checkouts can use the equivalent
  `scripts/rev2-preflight-status.py` wrapper. Both support `--json` for
  monitor-friendly status output.
- Final operator handoff:
  `scripts/rev2-readiness-bundle.py --imessage-live-smoke` consolidates the
  last smoke-plus-readiness step. Without `--yes`, it dry-runs the iMessage
  smoke and stops before readiness. With `--yes`, it sends one allowlisted
  smoke, writes the sent report, attaches it as `--smoke-report`, and runs
  strict readiness.
- Package wheel build via `pip wheel . --no-deps`: `passed`
- Installed-wheel preflight console check:
  `freyja-rev2-preflight-status --json` reports both `dry_run_command` and
  `final_command` with shell-safe artifact quoting and exit code `2` for the
  ready-for-final-smoke state.
- Repository hygiene, compileall, and `git diff --check`: `passed`
- Ruff, mypy, and pyright were probed with the local virtual environment and
  are not installed there; no lint/typecheck result is claimed.
- Freyja 2.0 live evidence bundle:
  `certification/reports/freyja-live-evidence-summary.json` reports `ok: true`,
  `all_gates_passed: true`, `ready_for_live_smoke: true`, iMessage runtime
  synced, terminal-equivalent route smoke passing, `freyja_qa_100` at `100.0%`
  with mean generation speed `31.238` tokens/sec, and
  `freyja_iterative_coding` at `100.0%` with mean generation speed `30.372`
  tokens/sec.
- Current iMessage approved smoke evidence:
  `certification/reports/imessage-live-smoke-sent.json` reports `status: sent`,
  `sent: 1`, `failed: 0`, and Joseph Verant resolved from the `joe` family
  member allowlist.
- Current Signal evidence:
  `certification/reports/freyja-live-signal-route-evidence.json` proves the
  Signal gateway targets Atlas Director and protected Rev 2 health checks pass,
  but live Signal smoke is blocked by external service/account setup:
  `SIGNAL_ENABLED=false`, no configured account number, no allowed sender, and
  `signal-cli-rest-api` unreachable at the configured REST URL.
- Current Vulcan profile evidence:
  `certification/reports/vulcan-readiness-latest.json` reports
  `ready_for_certification: true` for the `fast`, `reason`, `code`, and
  `vision` logical profiles after installing the configured local vision model.
- Messaging attachment hardening: Signal, iMessage, and Gmail now share a
  normalized message/attachment abstraction for text, thread/group metadata,
  attachment metadata, local references, and payload availability. Image
  requests route to the configured local `local_vision` profile instead of
  cloud by default. Missing image/PDF payloads are explicitly marked unavailable
  in Director prompts and are not sent as inspected images. Focused gateway,
  router, provider-health, MacAgent, and voice tests passed:
  `221 passed, 1 warning`.
- PDF/document handling: payload-backed PDF attachments now use bounded native
  PDF text extraction before Director dispatch. Extracted text is appended to
  the originating transport prompt with page metadata; missing or malformed PDF
  payloads produce explicit failure text instead of fabricated document
  descriptions. Focused media and gateway/transport tests passed:
  `73 passed, 1 warning`.
- Shortcut/HomePod ingress candidate: Director exposes protected
  `POST /shortcuts/message` for Siri Shortcuts/HomePod flows. It reuses normal
  private `RouteRequest` dispatch, preserves `shortcut-conv:<id>` continuity,
  supports tool execution, and returns concise `response`/`spoken` text.
- Gmail production check: `scripts/messaging-production-check.py --connector
  gmail` now reports sanitized Gmail readiness, including identity/allowlist,
  IMAP/SMTP credential presence, Director token, lifecycle tunables, and
  LaunchAgent loaded state. The current local report is not ready for live smoke
  because `com.freyja-os.gmail-connector` is not loaded; prior connector logs
  showed Gmail authentication failures, so restarting it remains blocked on
  reviewed working credentials.

## Still Not Claimed Complete

- Production deployment must rerun the selected-connector readiness bundle
  against the real Atlas/Iris hosts and real connector account state after any
  host or credential changes.
- Signal live smoke remains an external onboarding item: start or repair
  `signal-cli-rest-api`, configure the linked `SIGNAL_ACCOUNT_NUMBER`, set at
  least one reviewed `SIGNAL_ALLOWED_SENDERS` value, and enable
  `SIGNAL_ENABLED=true` only after that allowlist is reviewed.
- Gmail live smoke remains external until Joe configures Freyja Gmail IMAP/SMTP
  credentials and the reviewed sender allowlist outside Git.
- HomePod live smoke remains external until Joe creates or approves the Siri
  Shortcut on an Apple device and supplies the configured Director connector
  token to that Shortcut.
- Stage 3 default routing should only be enabled after certification reports and
  latency measurements prove an improvement in the target deployment.
- Heavy-local cutover depends on stable endpoint, model, and health checks for
  the selected inference machine.

## Completion Rule

Do not mark Freyja 2.0 complete from this status file alone. Completion requires
the active goal audit to verify each implementation-plan requirement against
current code, tests, certification reports, and deployment evidence.
