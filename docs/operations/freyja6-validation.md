# Freyja 6.0 Validation Plan

Freyja 6.0 is an independent household agent platform. The first build target is
the smallest working end-to-end system: one Hermes agent named `freyja-test`,
one LiteLLM gateway, Vulcan as inference only, and Atlas as the control plane.

## Non-Negotiable Boundaries

- Do not dismantle Freyja 4/5, Msty Nexus, Msty Go, or OpenWebUI.
- Do not create Freyja, Cloyd, Benedict, Agent 44, or Jenna yet.
- Do not reuse existing Freyja bot credentials.
- Do not send private household data to cloud providers unless explicitly
  approved for that specific use.
- Keep inference, agents, memory, tools, messaging, and UI separable.

## Acceptance Checklist

1. Reply through the dedicated Discord test channel.
2. Survive restart with `freyja-test` identity and session intact.
3. Remember an intentionally stored fact through Hermes native memory.
4. Use Vulcan models through LiteLLM.
5. Switch between `vulcan-fast`, `vulcan-general`, and `vulcan-code`.
6. Read a file under the approved filesystem root.
7. Execute a safe terminal command.
8. Call an MCP tool.
9. Read the family calendar through the tool boundary.
10. Create an event from “Add basement cleanup this Saturday”.
11. Query Home Assistant through the tool boundary.
12. Invoke the coding workflow through OpenCode or the approved coding executor.
13. Return automatically after an Atlas reboot.

Generate status:

```bash
.venv/bin/python scripts/freyja6-acceptance-status.py
```

The status report writes
`certification/reports/freyja6-acceptance-status.json`. Missing live evidence is
reported as incomplete, not failed. Do not put credentials, bearer headers, bot
tokens, passwords, API keys, or private calendar details in the evidence file.

Use `docs/examples/freyja6-live-evidence.example.json` as the redacted evidence
shape. Each complete acceptance record must set `status` to `complete` and
include `captured_at` and `source`; `captured_at` must be an ISO timestamp, and
records without valid metadata remain partial. Records with present but weak
values, a non-complete status, or a `source` that does not match the expected
Freyja 6 validation helper list `semantic_failures` or remain partial. Calendar
write evidence must use a `YYYY-MM-DD` ISO
`event_date`; reboot return evidence must include an ISO start/end window whose
end is after its start, a running or healthy container status, and
`discord_reply_after_reboot_verification: "discord-api"` from the post-reboot
Discord API check. Trace evidence fields, including `litellm_request_id` and
`discord_reply_after_reboot`, must use the Freyja validation trace prefixes so
acceptance records can be correlated with logs. Tool acceptance values must stay
redacted and scoped: approved paths under `approved-files/`, MCP tool
`status.check`, calendar label `configured-calendar`, Home Assistant
`domain:<name>`, and an OpenCode result summary. The generated files under
`certification/reports/` are local evidence
artifacts and are ignored by git.

Run the ordered validation bundle when Atlas is ready:

```bash
.venv/bin/python scripts/freyja6-live-validation-bundle.py \
  --env-file deploy/compose/freyja6/.env \
  --live \
  --create-dirs
```

The bundle calls the individual validation helpers, redacts command secrets in
its own report, and writes
`certification/reports/freyja6-live-validation-bundle.json`. Use
`--calendar-write` only for the real calendar event test. Use
`--prepare-restart-evidence` before restarting Hermes or rebooting Atlas, then
use `--restart-evidence` only after restart or reboot evidence variables are
set. In live mode the calendar write and restart-evidence helpers are required
for a complete bundle: a run without `--calendar-write` or `--restart-evidence`
remains incomplete with required skips until the corresponding real evidence
has been captured. Bundle, acceptance-status, and preservation reports must keep
`schema_version: "1.0"` and their Freyja 6 `report_type`; migration readiness
rejects loose JSON that only claims success.
The bundle treats a helper as failed if either its exit code fails or its JSON
payload reports `ok: false`, `complete: false`, `ready: false`, or an
incomplete/failure status. It also validates its own step definitions before
running helpers; duplicate step IDs, missing IDs, non-boolean `required` or
`enabled` flags, or malformed command arrays produce a required
`bundle_contract` failure and stop the run before helper commands execute.
Bootstrap inside the bundle requires the real `deploy/compose/freyja6/.env`;
`.env.example` is only a template and is never used for host writes.

Before any live validation or migration discussion, confirm Freyja 6 remains
side-by-side, does not reuse legacy credentials or host mounts, and the existing
rollback systems are still represented:

```bash
.venv/bin/python scripts/freyja6-preservation-audit.py
.venv/bin/python scripts/freyja6-env-audit.py
.venv/bin/python scripts/freyja6-hermes-contract.py
.venv/bin/python scripts/freyja6-model-privacy-audit.py
.venv/bin/python scripts/freyja6-gateway-isolation-audit.py
.venv/bin/python scripts/freyja6-memory-boundary-audit.py
.venv/bin/python scripts/freyja6-messaging-gateway-audit.py
.venv/bin/python scripts/freyja6-terminal-safety-audit.py
.venv/bin/python scripts/freyja6-filesystem-boundary-audit.py
.venv/bin/python scripts/freyja6-mcp-boundary-audit.py
.venv/bin/python scripts/freyja6-coding-workflow-audit.py
.venv/bin/python scripts/freyja6-schedule-boundary-audit.py
.venv/bin/python scripts/freyja6-calendar-boundary-audit.py
.venv/bin/python scripts/freyja6-home-assistant-boundary-audit.py
.venv/bin/python scripts/freyja6-migration-readiness.py
```

The migration readiness gate must remain `not_ready` until preservation passes,
all acceptance items are complete, and at least three complete live bundle
reports with `complete: true`, `status: complete`, no required failures or
skips, `schema_version: "1.0"`, `report_type` set to
`"freyja6-live-validation-bundle"`, and distinct valid ISO run timestamps are
present. The acceptance-status and preservation inputs must also be typed
Freyja 6 reports with passing evidence/preservation contracts. Installation
success alone is not migration approval.
The model privacy audit must pass before any live validation that can touch
private household data; it proves Hermes routes through LiteLLM and LiteLLM
exposes only the local Vulcan aliases unless explicit cloud approval is added
later.
The gateway isolation audit keeps future family agents as reservations only and
checks that their eventual credentials, memory, MCP tokens, and Discord channel
boundaries will not collide.
The memory boundary audit proves Phase 1 uses Hermes-native private local memory
only, keeps shared household memory disabled for `freyja-test`, and rejects
cloud or experimental memory providers during validation. Future-agent memory
reservations must also stay separate from the live `freyja-test` memory root.
The messaging gateway audit proves Phase 1 has exactly one live Discord gateway
surface, with credentials supplied only by `FREYJA6_DISCORD_BOT_TOKEN` and the
test channel supplied only by `FREYJA6_DISCORD_CHANNEL_ID`.
The terminal safety audit proves terminal execution is MCP-mediated through
`freyja-terminal`, limited to the non-mutating validation allowlist, and backed
by a bounded terminal MCP server with narrow agent modes, bridge execution,
bearer auth, and send/read size limits.
The filesystem boundary audit proves Hermes sees only `/workspace/approved` as
a read-only mount sourced from `FREYJA6_APPROVED_FILES_ROOT`, while the repo
mount at `/workspace/repo` also remains read-only.
The MCP boundary audit proves calendar, Home Assistant, coding, and memory tools
are mediated through `freyja-core-gateway`, while destructive calendar deletion
and non-declared surfaces stay outside the `freyja-test` policy.
The coding workflow audit proves the approved coding executor remains OpenCode
through Freyja Core MCP instead of direct autonomous shell execution.
The schedule boundary audit proves only `freyja-test` validation cron tasks are
configured and mounted read-only before any scheduler smoke writes evidence.
The calendar boundary audit proves read/date-resolution/create tools are
available through Freyja Core MCP, the basement-cleanup write smoke is explicitly
approved, and delete remains outside the `freyja-test` policy.
The Home Assistant boundary audit proves Phase 1 exposes only read/list tools
through Freyja Core MCP and rejects any device-control surface for `freyja-test`.
The environment audit and scaffold verifier also pin runtime images exactly:
LiteLLM must remain `ghcr.io/berriai/litellm:v1.89.0`, and the
`HERMES_AGENT_IMAGE` tag must exactly match `HERMES_AGENT_VERSION`. The three
Vulcan aliases (`fast`, `general`, and `code`) must point at distinct configured
local model names so the model-switch acceptance test proves a real gateway
switch.

## Discord Reply Smoke

After the compose stack is running, send a validation prompt in the dedicated
Discord test channel and capture the prompt message ID and the `freyja-test`
reply message ID. Verify the reply through the Discord API and record only
redacted channel and trace IDs:

```bash
.venv/bin/python scripts/freyja6-discord-smoke.py \
  --channel-id "$FREYJA6_DISCORD_CHANNEL_ID" \
  --message-id "$FREYJA6_DISCORD_SMOKE_MESSAGE_ID" \
  --log-root /srv/freyja6/logs \
  --reply-id "$FREYJA6_DISCORD_SMOKE_REPLY_ID"
```

If the API check was captured elsewhere, manual evidence recording requires the
explicit confirmation phrase:

```bash
.venv/bin/python scripts/freyja6-discord-smoke.py \
  --channel-id "$FREYJA6_DISCORD_CHANNEL_ID" \
  --message-trace-id "$FREYJA6_DISCORD_MESSAGE_TRACE_ID" \
  --reply-trace-id "$FREYJA6_DISCORD_REPLY_TRACE_ID" \
  --log-root /srv/freyja6/logs \
  --manual-confirmation DISCORD_REPLY_VERIFIED
```

The resulting `discord_reply` evidence includes `verification_method` and must
use distinct prompt and reply trace IDs with Freyja validation prefixes.
Evidence and logs are written only when the channel is redacted, the traces are
distinct validation traces, and verification is either `discord-api` with a bot
reply that references the prompt message, or `manual-confirmed`.

## LiteLLM/Vulcan Smoke

Before starting services on Atlas, run the read-only preflight against the real
`deploy/compose/freyja6/.env`. Add `--create-dirs` only after that file exists,
its placeholders are replaced, and you want preflight to create the Freyja 6
data roots:

Preflight refuses to create or approve broad/overlapping host roots; approved
files, logs, and Hermes data must be distinct absolute paths under a
Freyja 6-specific directory. `VULCAN_OLLAMA_BASE_URL` must point at the Vulcan
inference host on a private, tailnet, `.local`, or explicitly Vulcan-scoped
host, not Atlas loopback, a public endpoint, or Freyja 6 compose services.

```bash
.venv/bin/python scripts/freyja6-env-audit.py --env-file deploy/compose/freyja6/.env
.venv/bin/python scripts/freyja6-hermes-contract.py
.venv/bin/python scripts/freyja6-model-privacy-audit.py
.venv/bin/python scripts/freyja6-gateway-isolation-audit.py
.venv/bin/python scripts/freyja6-memory-boundary-audit.py
.venv/bin/python scripts/freyja6-messaging-gateway-audit.py
.venv/bin/python scripts/freyja6-terminal-safety-audit.py
.venv/bin/python scripts/freyja6-filesystem-boundary-audit.py
.venv/bin/python scripts/freyja6-mcp-boundary-audit.py
.venv/bin/python scripts/freyja6-coding-workflow-audit.py
.venv/bin/python scripts/freyja6-schedule-boundary-audit.py
.venv/bin/python scripts/freyja6-calendar-boundary-audit.py
.venv/bin/python scripts/freyja6-hermes-image.py --env-file deploy/compose/freyja6/.env --build
.venv/bin/python scripts/freyja6-atlas-preflight.py --env-file deploy/compose/freyja6/.env --check-images --check-vulcan
```

Then seed the `freyja-test` identity/personality file, private memory/session
directories, log files, and approved smoke file:

```bash
.venv/bin/python scripts/freyja6-bootstrap-atlas.py --env-file deploy/compose/freyja6/.env
```

After `docker compose up -d`, verify the Freyja 6 stack and expected log files:

```bash
.venv/bin/python scripts/freyja6-stack-status.py --env-file deploy/compose/freyja6/.env
```

Stack status must report only `litellm-db`, `litellm`, and
`hermes-freyja-test`; each must be running or healthy, and the expected log
paths must be real files. Any extra future-agent service is a Phase 1 failure.

After the Atlas compose stack is running, validate the gateway path:

```bash
.venv/bin/python scripts/freyja6-litellm-smoke.py \
  --base-url http://127.0.0.1:4600/v1 \
  --api-key "$LITELLM_MASTER_KEY" \
  --log-root /srv/freyja6/logs \
  --models vulcan-general vulcan-fast vulcan-code
```

`--base-url` must target the Atlas LiteLLM gateway on loopback, a private or
tailnet address, `.local`, or an explicitly LiteLLM-scoped host; do not point
the smoke at a public gateway.

This records redacted evidence for `litellm_to_vulcan` and `model_switch` and
appends structured model-call and acceptance JSONL records. Acceptance evidence
is written only for approved Vulcan aliases with successful status codes,
explicit matching response models, listed gateway aliases, and Freyja validation
trace IDs.

Then validate the non-mutating tool paths:

```bash
.venv/bin/python scripts/freyja6-tool-smoke.py \
  --log-root /srv/freyja6/logs \
  --approved-file /srv/freyja6/approved-files/smoke.txt
```

This can record redacted evidence for approved file read, safe terminal command,
MCP health/tool call, calendar read, Home Assistant read, and OpenCode status.
It also appends structured tool-call and acceptance JSONL records.
The approved file smoke refuses paths outside the Freyja 6 approved read-only
roots (`/srv/freyja6/approved-files` on Atlas or `/workspace/approved` inside
Hermes).
MCP health endpoints and core-mediated tool evidence must return explicit
`ok: true` payloads and report the expected tool names:
`status.check`, `calendar.list_events`, `home_assistant.list_states`, and
`opencode.status`, each with a Freyja validation trace. Home Assistant evidence
must stay domain-scoped, for example `domain:sensor`.

Validate the configured cron schedules and log writability:

```bash
.venv/bin/python scripts/freyja6-schedule-smoke.py \
  --log-root /srv/freyja6/logs \
  --write-logs
```

This appends one redacted JSONL scheduler smoke entry for each enabled
`freyja-test` validation schedule.

After live smokes have run, audit that the tool, model-call, and acceptance logs
contain parseable redacted JSONL entries with `timestamp`, `event`, `trace_id`,
`status`, and the relevant `tool`, `model`, or `acceptance_id` field. The event
names must be `tool_call`, `model_call`, and `acceptance`; timestamps must parse
as ISO timestamps, and trace IDs must use the Freyja validation trace prefixes.
Logged tool names, model aliases, and acceptance IDs must stay within the
approved Freyja 6 Phase 1 surfaces:

```bash
.venv/bin/python scripts/freyja6-log-audit.py \
  --log-root /srv/freyja6/logs \
  --require-entries
```

Run the calendar write smoke only when you are ready to create the validation
event:

```bash
.venv/bin/python scripts/freyja6-calendar-write-smoke.py \
  --calendar-id "$FREYJA6_CALENDAR_WRITE_CALENDAR_ID" \
  --log-root /srv/freyja6/logs \
  --approval CREATE_BASEMENT_CLEANUP_TEST_EVENT
```

This creates `Basement cleanup` from “Add basement cleanup this Saturday” and
records only the title, date, and redacted trace ID. Evidence is recorded only
after the Freyja Core response returns explicit `ok: true`, confirms the
`calendar.create_event` tool result,
uses a Freyja validation trace, and returns the created event payload with the
expected title on the resolved Saturday date.

## Restart And Reboot Evidence

Before restarting the `hermes-freyja-test` container or rebooting Atlas, seed
the validation session and memory fact:

```bash
.venv/bin/python scripts/freyja6-prepare-restart-evidence.py \
  --session-id "$FREYJA6_RESTORED_SESSION_ID" \
  --stored-fact-label "$FREYJA6_MEMORY_FACT_LABEL"
```

Export the reported `identity_sha256_before` as
`FREYJA6_IDENTITY_SHA256_BEFORE`, then restart Hermes or reboot Atlas. After the
restart, ask `freyja-test` to recall the validation fact and reply in the
dedicated Discord test channel. Then record only redacted persistence and return
evidence:

```bash
.venv/bin/python scripts/freyja6-restart-evidence.py \
  --before-identity-sha256 "$FREYJA6_IDENTITY_SHA256_BEFORE" \
  --session-id "$FREYJA6_RESTORED_SESSION_ID" \
  --stored-fact-label "$FREYJA6_MEMORY_FACT_LABEL" \
  --memory-recall-trace-id "$FREYJA6_MEMORY_RECALL_TRACE_ID" \
  --log-root /srv/freyja6/logs \
  --container-status "running (healthy)" \
  --reboot-start "$FREYJA6_REBOOT_START" \
  --reboot-end "$FREYJA6_REBOOT_END" \
  --discord-reply-trace-id "$FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID" \
  --discord-reply-verification "$FREYJA6_DISCORD_REPLY_AFTER_REBOOT_VERIFICATION"
```

This records `restart_identity_session`, `remember_fact`, and
`atlas_reboot_return` only when the post-restart identity hash matches the
operator-captured hash, the seeded session marker JSON still belongs to
`freyja-test`, the seeded memory fact JSON matches the requested label, the
post-restart memory recall has its own Freyja validation trace, the post-reboot
Discord reply trace uses a Freyja validation trace prefix, the post-reboot reply
was verified through the Discord API, and the container status is running or
healthy without negative markers such as `not running`, `not healthy`, or
`unhealthy`. A matching filename or loose fact string is not
enough.

## Tool Boundaries

`config/freyja6/tool-boundaries.yaml` is the current source of truth for the
Phase 1 tool surface. Configured now:

- approved filesystem root as a read-only bind mount
- terminal execution through `freyja-terminal`
- MCP discovery/calls through `freyja-core-gateway`
- calendar read/create/date helpers through `freyja-core-gateway`
- read-only Home Assistant state through `freyja-core-gateway`
- coding workflow through OpenCode via `freyja-core-gateway`

Still pending before full acceptance can pass:

- live evidence that the configured Calendar and Home Assistant MCP paths work
  from Atlas with household credentials

## Scheduled Validation

`config/freyja6/schedules.yaml` defines only `freyja-test` validation schedules:

- `freyja-test-health-heartbeat` every 15 minutes
- `freyja-test-daily-tool-smoke` daily at 07:17 America/New_York

These schedules write redacted status and trace evidence to the Freyja 6 log
root. They must not instantiate future family agents or migrate existing
channels.

`config/freyja6/future-agent-isolation.yaml` reserves the future family-agent
boundaries. It is not an activation file. During Phase 1 it must continue to
list only `freyja-test` as live while reserving separate identity, session,
private memory, credential, MCP token, and Discord channel env vars for Freyja,
Cloyd, Benedict, Agent 44, and Jenna. Freyja is the shared household
coordinator; each family member's named agent is a standalone personal runtime,
not a child of Freyja or another named agent. Benedict is Beth's agent. The
paralegal enclave remains agentless until separately activated. Reserved private
memory paths must not point at `/var/lib/hermes/agents/freyja-test/`.

## Migration Rule

Installation success is not migration success. Migration readiness requires at
least three complete live validation bundle runs on distinct dates, and each
bundle report must be internally complete (`schema_version: "1.0"`,
`report_type: "freyja6-live-validation-bundle"`, `complete: true`, `status:
complete`, and no required failures or skips). Each required live bundle step
must appear exactly once in `results`, be marked `required: true`, and have
`status: pass`; missing, duplicate, skipped, non-required, or unknown-status
required steps do not count toward repeated successful validation. Migration
readiness also rejects spoofed acceptance or preservation reports that do not
match the Freyja 6 report contracts. After that, activate one isolated runtime or channel at a time. Freyja may
be activated as the household coordinator. Cloyd, Benedict, Agent 44, and Jenna
must each be activated independently, with their own owner policy, memory,
credentials, Core token, and optional messaging channel:

```text
freyja-test -> Freyja (household coordinator)
freyja-test -> Cloyd | Benedict | Agent 44 | Jenna (independent personal agents)
```
