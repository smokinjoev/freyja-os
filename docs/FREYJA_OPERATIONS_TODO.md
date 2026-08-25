# Freyja Operations TODO

## Rev 2 Triage

**Last reviewed:** 2026-08-24

This file is an operator backlog, not the Freyja 2.0 completion gate. Rev 2
release status is tracked in `docs/REV2_STATUS.md`, and the requirement matrix
is `docs/REV2_COMPLETION_AUDIT.md`.

Current code-side Rev 2 work has implemented and tested the Atlas Director,
Iris MacAgent boundary, provider registry, Iris classifier fallback behavior,
capability evidence, memory provenance, external-worker policy, certification
suite, canonical connector ingress, and strict readiness bundle. The active
release gates are now Signal onboarding/live smoke and a final readiness bundle
that includes the required operator reports, including `--require-smoke-report`,
`--require-signal-smoke-report`, and `--require-vulcan-report` where live
cutover is being certified. The current Vulcan readiness evidence proves the
`fast`, `reason`, `code`, and `vision` profiles are installed and reachable.

Items below that require logging into macOS accounts, changing Apple/iCloud
identity, joining machines to Tailscale, installing Linux on Odin, or sending
real messages are operator actions. They are intentionally not automated from
the repository and remain outside the code-only readiness proof unless the Rev 2
completion audit names them as final deployment evidence.

## Agent Roles

- [ ] Treat `freyja` as the family/household agent and shared issue-review coordinator.
- [ ] Treat `cloyd-gibbler` as Joe's private personal agent.
- [ ] Treat `benedict` as Beth's private personal agent.
- [ ] Keep `smith` as the maintenance agent: read-only diagnostics by default, writes only through approval gates.
- [ ] Keep private memories, accounts, and connector credentials scoped to each person's primary agent.
- [ ] Use Freyja for household status, shared home commands, family calendar views, and `/agents/family/issue-review`.

## Iris Account Migration

- [ ] Log in directly as the `freyja` macOS account on Iris.
- [ ] Promote `freyja` to macOS admin.
- [ ] Verify `freyja` can unlock admin prompts without Joe's account.
- [ ] Move Freyja-OS repo checkout, `.env` files, service state, logs, and runtime data under `freyja` ownership.
- [ ] Move or recreate SSH keys, deploy keys, and GitHub access needed for Freyja maintenance.
- [ ] Confirm Tailscale is logged in and reachable from the `freyja` account context.
- [ ] Confirm Ollama runs under the intended service/user context and can serve `qwen2.5:7b`.
- [ ] Confirm `qwen2.5:7b` warms with `keep_alive=-1` and remains resident.
- [ ] Reinstall or move LaunchAgents/services so they do not depend on Joe's home directory or keychain.
- [ ] Reboot Iris and verify Freyja services, Ollama, Tailscale, and local health checks recover automatically.

## Remove Joe Personal Data From Iris

- [ ] Back up Joe's user account data before destructive changes.
- [ ] Sign Joe out of iCloud, Messages, Mail, Calendar, Contacts, Safari, and browser profiles on Iris.
- [ ] Remove saved passwords, tokens, personal browser sessions, and account caches from Iris.
- [ ] Verify Freyja connectors no longer depend on Joe's personal keychain.
- [ ] Delete or archive Joe's local macOS account only after the `freyja` account passes reboot validation.

## Iris Admin Role

- [ ] Treat Iris as `host:iris` / `service:iris`, not `person:joe`.
- [ ] Keep Atlas Director authoritative for routing, tool authorization, and personal-data grants.
- [ ] Give Iris admin capability only for infrastructure operations: service restart, health inspection, model warmup, and local runtime maintenance.
- [ ] Keep the Iris 7B router in shadow mode until promotion criteria are met.
- [ ] Do not give Iris personal-data authority by default.

## Odin Linux Heavy Inference Node

- [ ] Install Linux on the new PC and give it the stable hostname `odin`.
- [ ] Join the tailnet and restrict inference endpoints to private network access.
- [ ] Install GPU drivers, container runtime if needed, and Ollama or the selected inference server.
- [ ] Install the heavy reasoning model and confirm it can remain resident if RAM/VRAM allows.
- [ ] Add health, tags/models, warmup, and residency checks equivalent to Iris.
- [ ] Configure Atlas `OLLAMA_REASONING_BASE_URL` to Odin's private Ollama endpoint.
- [ ] Verify Atlas `/local-reasoning/health` and `/local-reasoning/warm`.
- [ ] Confirm complex internal work routes to Odin through the `local_reasoning` provider.
- [ ] Keep private/sensitive prompts internal; never fall back to cloud for private data.
- [ ] Run router tests and certification gauntlets after Atlas can reach the node.

## Deployment Checks

- [ ] Validate Atlas Director compose config before restart.
- [ ] Capture `scripts/vulcan-operator.py readiness --output logs/vulcan-readiness.json`.
- [ ] Restart only the Director service unless another service truly changed.
- [ ] Verify `/health` and `/iris-router/health`.
- [ ] Run Iris shadow smoke and standard gauntlets.
- [ ] Record disagreement patterns, especially under-routing.

## Communications Rollout

- [ ] Configure `GMAIL_IDENTITY` with Freyja's existing Gmail address.
- [ ] Configure `GMAIL_ALLOWED_SENDERS` with only approved work/corporate senders.
- [ ] Configure Gmail IMAP/SMTP transport credentials for Freyja's Gmail mailbox.
- [ ] Install and load `com.freyja-os.gmail-connector` with `scripts/install-gmail-connector.sh`.
- [ ] Confirm LaunchAgent state with `scripts/status-gmail-connector.sh`.
- [ ] Confirm `logs/gmail-connector.log` reports `Gmail connector started`.
- [ ] Smoke test an allowlisted Gmail message and confirm the reply stays in the same Gmail thread.
- [ ] Smoke test Gmail HTML input and confirm scripts, styles, remote images, and tracking URLs are not forwarded to Director.
- [ ] Confirm Gmail-originated consequential actions require approval through a trusted non-Gmail channel.
- [ ] Configure `IMESSAGE_FAMILY_CHAT_IDENTIFIERS` for the authorized family group only.
- [ ] Add Freyja's Apple identity to the family iMessage group from the `freyja` macOS account.
- [ ] Smoke test passive family iMessage observation and confirm no group reply is generated.
- [ ] Smoke test `Freyja, ...` and `@Freyja ...` invocations and confirm addressed messages route through Director.
- [ ] Review extracted family memory candidates before treating them as authoritative or calendar-worthy.

## Messaging BLOCKED_BY_USER Items

- BLOCKED_BY_USER - Signal - Atlas - live validation requires external Signal
  account/service setup. Code and mocked gateway/transport tests are complete
  for allowlisting, identity mapping, duplicate suppression, attachment
  metadata, image payload forwarding, missing-payload honesty, Director routing,
  retries/timeouts, and sanitized logs. Joe must start or repair
  `signal-cli-rest-api`, configure the linked `SIGNAL_ACCOUNT_NUMBER`, set a
  reviewed `SIGNAL_ALLOWED_SENDERS` allowlist, and set `SIGNAL_ENABLED=true`
  outside Git. Use `scripts/signal-operator.py onboarding-plan --number <account>`
  or the equivalent Compose `signal-operator onboarding-plan` command for a
  redacted setup checklist before changing state. Afterward run
  `scripts/run-signal-connector.py --once` and
  `scripts/messaging-production-check.py --connector signal`.
- BLOCKED_BY_USER - Gmail - Atlas - live validation requires Freyja Gmail
  account authorization/credentials outside Git. Code and mocked
  gateway/transport tests are complete for sender allowlisting, Gmail thread
  preservation, HTML sanitization, image attachment forwarding,
  payload-backed PDF text extraction, metadata-only PDF/image honesty, safe
  failure replies, loop prevention, and sanitized logs. Joe must configure
  `GMAIL_IDENTITY`,
  `GMAIL_ALLOWED_SENDERS`, `GMAIL_IMAP_USERNAME`, `GMAIL_IMAP_PASSWORD`,
  `GMAIL_SMTP_USERNAME`, and `GMAIL_SMTP_PASSWORD` outside Git, then install or
  restart the connector with `scripts/install-gmail-connector.sh`. Afterward run
  `scripts/status-gmail-connector.sh`,
  `scripts/messaging-production-check.py --connector gmail`, and send one
  allowlisted test email, then run
  `python3 -m pytest tests/test_gmail_gateway.py tests/test_gmail_transport.py tests/test_gmail_launchagent.py`.
- BLOCKED_BY_USER - iMessage - Iris - live validation can require macOS
  Messages/iCloud account state, Full Disk Access, Automation approval, and an
  approved outbound smoke. Code and mocked tests are complete for direct
  routing, self-message loop prevention, group passive observation, explicit
  group invocation, attachment metadata, missing-payload honesty, duplicate
  suppression, and MacAgent capability boundaries. Joe must verify the `freyja`
  macOS account is signed into Messages, grant required privacy prompts, set
  `IMESSAGE_FAMILY_CHAT_IDENTIFIERS`, and approve the final outbound smoke.
  Afterward run `scripts/rev2-readiness-bundle.py --imessage-live-smoke --yes`.
- BLOCKED_BY_USER - HomePod/Siri Shortcuts - Iris/Apple device - final live
  validation requires creating or approving a Shortcut on an Apple device.
  Server-side Director plumbing is complete at protected
  `POST /shortcuts/message`, reusing private Director routing and returning
  voice-friendly `spoken` text. Joe must create a Shortcut that accepts dictated
  text, POSTs JSON `{"prompt":"<dictated text>","conversation_id":"homepod"}`
  to the Atlas Director `/shortcuts/message` endpoint with
  `Authorization: Bearer <FREYJA_CONNECTOR_TOKEN>`, then speaks the `spoken`
  field from the JSON response. Afterward run
  `python3 -m pytest tests/test_health.py tests/test_voice_assistant_suite.py`
  and perform one HomePod spoken smoke request.
