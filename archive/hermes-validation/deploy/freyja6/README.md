# Freyja 6.0 Validation Stack

This compose target is a new side-by-side Freyja 6.0 validation stack for Atlas.
It does not replace Freyja 4/5, Msty Nexus, Msty Go, or OpenWebUI.

Initial flow:

```text
Discord test channel -> Hermes freyja-test -> LiteLLM -> Vulcan
```

Only one agent is defined in Phase 1: `freyja-test`.

## Version Pins

The `.env.example` pins:

- LiteLLM Proxy: `ghcr.io/berriai/litellm:v1.89.0`
- Hermes Agent: `v2026.9.14`, tagged locally as
  `hermes-agent-local:v2026.9.14` after the Atlas install/build is verified

Keep these fixed during validation. Upgrade only after recording new acceptance
test evidence. The validation helpers reject nearby drift as well as `latest` or
`main`: LiteLLM must match the listed image exactly, and the Hermes image tag
must exactly match `HERMES_AGENT_VERSION`.

## Start On Atlas

```bash
cp deploy/compose/freyja6/.env.example deploy/compose/freyja6/.env
$EDITOR deploy/compose/freyja6/.env
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
.venv/bin/python scripts/freyja6-atlas-preflight.py --env-file deploy/compose/freyja6/.env --create-dirs --check-images --check-vulcan
.venv/bin/python scripts/freyja6-bootstrap-atlas.py --env-file deploy/compose/freyja6/.env
docker compose --env-file deploy/compose/freyja6/.env -f deploy/compose/freyja6/compose.yaml up -d
.venv/bin/python scripts/freyja6-stack-status.py --env-file deploy/compose/freyja6/.env
```

Use a new Discord bot token and one dedicated test channel. Do not reuse or edit
existing Freyja bot credentials.
The copied `.env` must replace placeholders and set `FREYJA6_APPROVED_FILES_ROOT`,
`FREYJA6_LOG_ROOT`, and `FREYJA6_HERMES_DATA` to explicit Freyja-6-scoped host
paths before bootstrap; `.env.example` is never used for host writes.

Set `HERMES_AGENT_SOURCE` to the verified Hermes Agent checkout on Atlas before
running the image helper. The helper builds and tags only
`HERMES_AGENT_IMAGE`, preserving the pinned `HERMES_AGENT_VERSION`.

Configure the Freyja Core MCP service with an agent-token mapping for the new
test agent, for example:

```bash
export FREYJA_MCP_AGENT_TOKENS_JSON='{"redacted-freyja6-core-token":"freyja-test"}'
```

Use that same redacted token value as `FREYJA6_CORE_MCP_TOKEN` in the Freyja 6
`.env`. Use a separate token for `FREYJA6_TERMINAL_MCP_TOKEN`.

## Required Evidence Before Migration

`freyja-test` must pass the Freyja 6 acceptance suite repeatedly before any
existing user, channel, capability, or agent migrates.

Generate the current acceptance status without live credentials:

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
.venv/bin/python scripts/freyja6-acceptance-status.py
.venv/bin/python scripts/freyja6-migration-readiness.py
```

`freyja6-migration-readiness.py` must remain `not_ready` until preservation
passes, all acceptance items are complete, and at least three complete live
bundle reports exist. Readiness only trusts typed Freyja 6 artifacts:
acceptance status, preservation audit, and live validation bundle reports must
keep `schema_version: "1.0"` and their expected `report_type`, and bundle runs
must be live, complete, and free of required failures or skips.

Record only redacted IDs, trace IDs, summaries, `captured_at`, and `source` in
`certification/reports/freyja6-live-evidence.json`. Acceptance evidence without
`captured_at` and `source` remains partial. Use
`docs/examples/freyja6-live-evidence.example.json` as the shape guide.

To run the validation helpers as one ordered bundle, use:

```bash
.venv/bin/python scripts/freyja6-live-validation-bundle.py \
  --env-file deploy/compose/freyja6/.env \
  --live \
  --create-dirs
```

Add `--calendar-write` only when ready to create the real validation calendar
event. Add `--prepare-restart-evidence` before restarting Hermes or rebooting
Atlas, then add `--restart-evidence` after the restart or Atlas reboot evidence
values are present in the Freyja 6 `.env`.

After `freyja-test` replies in the dedicated Discord channel, verify the prompt
and reply message IDs. The smoke records whether verification came from the
Discord API or the explicit manual confirmation path:

```bash
.venv/bin/python scripts/freyja6-discord-smoke.py \
  --channel-id "$FREYJA6_DISCORD_CHANNEL_ID" \
  --message-id "$FREYJA6_DISCORD_SMOKE_MESSAGE_ID" \
  --log-root /srv/freyja6/logs \
  --reply-id "$FREYJA6_DISCORD_SMOKE_REPLY_ID"
```

After LiteLLM is running, prove the gateway path and append redacted evidence:

```bash
.venv/bin/python scripts/freyja6-litellm-smoke.py \
  --base-url http://127.0.0.1:4600/v1 \
  --api-key "$LITELLM_MASTER_KEY" \
  --log-root /srv/freyja6/logs \
  --models vulcan-general vulcan-fast vulcan-code
```

After Freyja Core and MCP services are reachable, run the non-mutating tool smoke:

```bash
.venv/bin/python scripts/freyja6-tool-smoke.py \
  --log-root /srv/freyja6/logs \
  --approved-file /srv/freyja6/approved-files/smoke.txt
```

The ordered validation bundle also runs
`scripts/freyja6-home-assistant-boundary-audit.py`, which proves the
`freyja-test` Home Assistant path is read-only before any live state query is
accepted as evidence.

These smokes append structured model-call, tool-call, and acceptance JSONL
records in addition to updating the redacted evidence file.

Check that the configured validation schedules can write redacted log entries:

```bash
.venv/bin/python scripts/freyja6-schedule-smoke.py \
  --log-root /srv/freyja6/logs \
  --write-logs
```

After live smokes, audit that Freyja 6 logs are nonempty, parseable,
secret-free, and structured with `timestamp`, `event`, `trace_id`, `status`,
plus `tool`, `model`, or `acceptance_id` as appropriate. The audit expects
`tool_call`, `model_call`, and `acceptance` event names with known statuses:

```bash
.venv/bin/python scripts/freyja6-log-audit.py \
  --log-root /srv/freyja6/logs \
  --require-entries
```

The calendar write acceptance item is separate because it creates a real event:

```bash
.venv/bin/python scripts/freyja6-calendar-write-smoke.py \
  --calendar-id "$FREYJA6_CALENDAR_WRITE_CALENDAR_ID" \
  --log-root /srv/freyja6/logs \
  --approval CREATE_BASEMENT_CLEANUP_TEST_EVENT
```

For restart and Atlas reboot validation, seed the validation session and memory
fact, export the reported `identity_sha256_before` as
`FREYJA6_IDENTITY_SHA256_BEFORE`, then restart Hermes or reboot Atlas. After the
restart, record the post-restart session, memory fact, container status, and
Discord reply trace:

```bash
.venv/bin/python scripts/freyja6-prepare-restart-evidence.py \
  --session-id "$FREYJA6_RESTORED_SESSION_ID" \
  --stored-fact-label "$FREYJA6_MEMORY_FACT_LABEL"

.venv/bin/python scripts/freyja6-restart-evidence.py \
  --before-identity-sha256 "$FREYJA6_IDENTITY_SHA256_BEFORE" \
  --session-id "$FREYJA6_RESTORED_SESSION_ID" \
  --stored-fact-label "$FREYJA6_MEMORY_FACT_LABEL" \
  --log-root /srv/freyja6/logs \
  --container-status "running (healthy)" \
  --reboot-start "$FREYJA6_REBOOT_START" \
  --reboot-end "$FREYJA6_REBOOT_END" \
  --discord-reply-trace-id "$FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID" \
  --discord-reply-verification "$FREYJA6_DISCORD_REPLY_AFTER_REBOOT_VERIFICATION"
```

The post-restart collector validates the marker JSON written by
`freyja6-prepare-restart-evidence.py`; filenames or loose fact strings alone do
not satisfy the restart/session or memory acceptance items. Reboot return
evidence also requires the post-reboot Discord reply to be verified through the
Discord API.
