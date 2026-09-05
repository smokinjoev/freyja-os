# Open WebUI Home-Agent Runbook

Status date: 2026-09-04.

## Current Placement

Open WebUI is running as the Atlas household UI. Iris previously had a
duplicate local Open WebUI stack, but that copy is disabled and should stay off
unless deliberately re-enabled for recovery testing.

```text
browser/PWA -> Atlas Open WebUI :3001 -> model-proxy -> Vulcan Ollama/OpenAI-compatible endpoint
```

Current observation:

| Component | Value |
| --- | --- |
| Compose project | `freyja-open-webui-atlas` |
| Open WebUI URL | `http://100.119.235.114:3001` on tailnet |
| Iris duplicate Open WebUI | `http://100.115.228.56:3001`, intentionally stopped |
| Open WebUI version | `0.11.3` |
| Open WebUI image | `ghcr.io/open-webui/open-webui:main` |
| Open WebUI data volume | `freyja-open-webui-atlas_open-webui` mounted at `/app/backend/data` |
| Model proxy image | `python:3.12-alpine` |
| Model proxy source | `deploy/compose/open-webui/model-proxy.py` |
| Model proxy Freyja 5 upstream | `http://host.docker.internal:8500/v1` |
| Freyja 5 gateway URL | `http://127.0.0.1:8500` locally |
| Freyja 5 gateway container | `freyja5-gateway-1`, side-by-side with Open WebUI/Freyja 3 |
| Vulcan primary endpoint | `http://100.94.80.21:8088/v1` |
| Vulcan Ollama endpoint | `http://100.94.80.21:11434` |
| Iris fallback endpoint | `http://100.115.228.56:11434/v1` |

Nexus is not required for the current Open WebUI path.

Inference policy audit:

```bash
scripts/audit-open-webui-inference-policy.py \
  --output certification/reports/open-webui-inference-policy-audit.json
```

Latest audit:

```text
ok=true
model_profiles={fast_chat,strong_reasoning,vision_documents,coding}
nexus_not_required=true
unloads_other_primary_models=true
cloud_fallback_disabled_for_open_webui_path=true
```

## Recovery Checkpoints

Before home-agent changes, a source checkpoint patch was written under:

```text
.codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch
.codex-checkpoints/pre-open-webui-home-agent-status-20260904T133828-0400.txt
```

The Open WebUI configuration and data volume backup was captured under:

```text
logs/open-webui-diagnostics/home-agent-20260904T174214Z/
logs/open-webui-diagnostics/home-agent-20260904T174214Z/open-webui-data-volume.tgz
```

Broader redacted platform inventory:

```text
certification/reports/open-webui-home-agent-platform-inventory.json
```

Backup and rollback audit:

```bash
scripts/audit-open-webui-backup-rollback.py \
  --output certification/reports/open-webui-backup-rollback-audit.json
```

Latest audit:

```text
ok=true
tar_gzip_readable=true
contains_webui_db=true
sha256=44b3dd287665387a843e0068e1b69a1e459744b4a23f20cf6fcc311fa5187f21
archive_may_contain_private_content=true
archive_handling=treat_as_sensitive_do_not_commit_or_print_contents
```

Rollback procedure:

1. Stop the Open WebUI stack:

```bash
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml down
```

2. Restore source files if needed:

```bash
git apply .codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch
```

3. Restore the Open WebUI volume from the backup:

```bash
docker run --rm \
  -v freyja-open-webui-atlas_open-webui:/target \
  -v "$(pwd)/logs/open-webui-diagnostics/home-agent-20260904T174214Z:/backup:ro" \
  alpine:3.20 \
  sh -c 'rm -rf /target/* && tar -xzf /backup/open-webui-data-volume.tgz -C /target'
```

4. Start the stack:

```bash
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
```

5. Verify `http://100.119.235.114:3001/api/version` returns `0.11.3` or the intended restored version.

## Source-Controlled Agent Definitions

Open WebUI-facing definitions live at:

```text
config/open-webui-home-agents.yaml
config/freyja-channels.yaml
config/freyja-proactive.yaml
```

They define five importable/mirrorable agents:

| Agent | Owner | Model profile | Sensitive constraints |
| --- | --- | --- | --- |
| Freyja | household | `strong_reasoning` | confirms writes/destructive actions |
| Cloyd | Joe | `coding` | technical tools for Joe only |
| Benedict | Beth | `strong_reasoning` | local-only, `restricted:benedict`, no cloud fallback |
| Agent 44 | Liam | `fast_chat` | no admin, messaging, or device actions |
| Jenna | Jenna | `fast_chat` | no admin, messaging, or device actions |

Use these definitions as the source of truth when creating Open WebUI Model/agent entries. Do not paste secrets into agent prompts, tools, or knowledge descriptions.

Generate reviewable Open WebUI import payloads from the source manifest:

```bash
scripts/export-open-webui-home-agents.py \
  --output certification/reports/open-webui-home-agents-import.json
```

The payload uses the live proxy model IDs while preserving the requested
friendly display names and agent IDs in metadata:

| Display agent | Open WebUI base model ID |
| --- | --- |
| Freyja | `agent/freyja` |
| Cloyd | `agent/cloyd-gibbler` |
| Benedict | `agent/benedict` |
| Agent 44 | `agent/agent-47` |
| Jenna | `agent/jennacide` |

Output artifact:

```text
certification/reports/open-webui-home-agents-import.json
```

The five agent rows have been prepared as importable Open WebUI model records
and were tested against the earlier local compose database with the guarded
offline importer. After Atlas was confirmed as the real Open WebUI host and
the Iris duplicate was stopped, authenticated Atlas activation remains the
source of truth for live model/resource presence.

Evidence artifact:

```text
certification/reports/open-webui-home-agents-offline-apply.json
```

Access metadata audit:

```bash
scripts/audit-open-webui-home-agent-access.py \
  --db /app/backend/data/webui.db \
  --output certification/reports/open-webui-home-agent-access-audit.json
```

Latest Iris-duplicate audit before the duplicate was stopped:

```text
ok=true
user_count=0
group_count=0
pending=["open_webui_users_missing","open_webui_groups_missing"]
```

Current Atlas public Open WebUI setup status:

```text
onboarding=false
auth_enabled=true
signup_enabled=false
login_form_enabled=true
```

Atlas has existing Open WebUI users and conversations. API key controls were
hidden because the Atlas Open WebUI config had `auth.enable_api_keys=false`.
Before changing that setting, the Atlas database was backed up inside the
container at:

```text
/app/backend/data/webui.db.backup-before-enable-api-keys-20260905T124926Z
```

`auth.enable_api_keys` is now enabled and the Atlas Open WebUI container was
restarted. Exact next action: refresh or sign back in to the existing Atlas
Open WebUI admin account at `http://100.119.235.114:3001`, open the user
profile/settings area, create an admin/service API key outside source control,
then rerun the authenticated post-auth activation and smoke checks.

Machine-readable readiness queue:

```bash
scripts/summarize-open-webui-home-agent-readiness.py
jq '.required_next_actions' \
  certification/reports/open-webui-home-agent-readiness-summary.json
```

Current operator sequence:

1. Use the existing Atlas Open WebUI admin account at `http://100.119.235.114:3001`.
2. Generate an admin or service-account API key and set `OPEN_WEBUI_API_KEY` outside source control.
3. Rerun the post-auth activation dry-run.
4. Run the five-agent authenticated chat smoke.
5. Configure Telegram with `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`, and `TELEGRAM_IDENTITY_MAP`; keep empty allowlists as deny-all.
6. Run the Telegram pilot dry-run before enabling long polling.
7. Configure Signal with `SIGNAL_REST_API_URL`, `SIGNAL_ACCOUNT_NUMBER`, `SIGNAL_ALLOWED_SENDERS`, and `SIGNAL_IDENTITY_MAP`; keep empty allowlists as deny-all.
8. Run the Signal pilot dry-run after `signal-cli-rest-api` registration is healthy.

Once real Open WebUI users exist, bind the imported models to groups with a
dry-run first:

```bash
scripts/bind-open-webui-home-agent-access.py \
  --output certification/reports/open-webui-home-agent-access-bind-dry-run.json
```

When the local `/app/backend/data/webui.db` path is not available, the dry-run
snapshots `webui.db`, `webui.db-wal`, and `webui.db-shm` from
`freyja-open-webui-atlas-open-webui-1`. It does not mutate the running database.

Current dry-run evidence:

```text
certification/reports/open-webui-home-agent-access-bind-dry-run.json
```

Latest live dry-run:

```text
ready=false
missing_users=["beth","jenna","joe","liam"]
grant_insert_count=10
mode=dry-run
```

Only after the dry-run shows `ready=true`, apply with an explicit writable
`--db` and `--apply`; the binder creates a database backup before writing. Apply
mode does not use a container snapshot.

After Joe signs in or provides an authenticated Open WebUI owner/admin session,
the dry-run post-auth activation sequence can inspect a temporary snapshot of
the live Open WebUI container database:

```bash
scripts/activate-open-webui-home-agent-post-auth.py \
  --resources-json certification/reports/open-webui-home-resources-export.json
```

The dry-run snapshots `webui.db`, `webui.db-wal`, and `webui.db-shm` from
`freyja-open-webui-atlas-open-webui-1` when the local default DB path is not
available. It does not mutate the running container database.

If the Open WebUI database has exactly one user after first-account onboarding,
the activation dry-run resolves that user as the resource owner automatically.
Use `--owner-user-id <id>` when multiple users exist or when applying against an
explicit writable database.

Current dry-run evidence:

```text
certification/reports/open-webui-home-agent-post-auth-activation.json
```

Latest dry-run:

```text
ready=false
dry_run_snapshot.container="freyja-open-webui-atlas-open-webui-1"
access.missing_models=[]
access.missing_users=["beth","jenna","joe","liam"]
resources.reason="missing or ambiguous Open WebUI owner user"
next_actions=[
  "Create/sign in Open WebUI users for: beth, jenna, joe, liam.",
  "Complete first-account onboarding, or pass --owner-user-id when multiple Open WebUI users exist."
]
```

Only run with `--apply` after the dry-run shows `ready=true`. Apply mode does
not use the container snapshot path; run it where `/app/backend/data/webui.db`
is the real writable Open WebUI database, or pass an explicit writable `--db`
path. Apply mode creates
database backups before writing access grants and resource rows. Apply mode
exits nonzero when the plan is not ready or no write was applied, so shell
automation can fail closed.
When the dry-run shows `ready=true`, follow the report's `next_actions`: rerun
with `--apply`, then run the authenticated five-agent chat smoke with
`OPEN_WEBUI_API_KEY` set.

Live database state after import:

| Open WebUI model ID | Display name |
| --- | --- |
| `agent/freyja` | Freyja |
| `agent/cloyd-gibbler` | Cloyd |
| `agent/benedict` | Benedict |
| `agent/agent-47` | Agent 44 |
| `agent/jennacide` | Jenna |

## Scoped Memory Service

The additive home-memory API is mounted in the Freyja FastAPI app at:

```text
/freyja-home-memory
```

Deployment note: the side-by-side Freyja 5 gateway is started with
`deploy/compose/freyja5/compose.yaml`. The container sets `REPOSITORY_ROOT=/app`
so source-controlled config files resolve from `/app/config` after package
installation.

Operations:

| Operation | Endpoint |
| --- | --- |
| `search` | `GET /freyja-home-memory/search?scope=<scope>&q=<query>` |
| `remember` | `POST /freyja-home-memory/remember` |
| `update` | `POST /freyja-home-memory/update` |
| `forget` | `DELETE /freyja-home-memory/forget/{scope}/{record_id}` |
| `record-decision` | `POST /freyja-home-memory/record-decision` |
| `recent-events` | `GET /freyja-home-memory/recent-events?scope=<scope>` |

Records include scope, owner, provenance, created/updated timestamps, sensitivity, and operation metadata. Current enforced scopes include:

```text
personal:joe
personal:beth
personal:liam
personal:jenna
household
project:freyja-os
restricted:benedict
```

Benedict can read `personal:beth` and `restricted:benedict`, but can only write `restricted:benedict`. Joe cannot read Beth/Benedict scopes, Beth cannot read Joe's personal scope, and child agents cannot access administrative scopes.

## Open WebUI Resources

Knowledge, native memory, and tool/resource policy live at:

```text
config/open-webui-home-resources.yaml
```

Export reviewable Open WebUI resource payloads with:

```bash
scripts/export-open-webui-home-resources.py \
  --output certification/reports/open-webui-home-resources-export.json
```

The export contains:

- `Freyja Household` Knowledge for stable household/device/procedure information.
- `Freyja Projects` Knowledge for Freyja OS architecture and runbooks.
- `Benedict Restricted` Knowledge for Beth-authorized local paralegal material only.
- Native Open WebUI per-user memory policy for Joe, Beth, Liam, and Jenna.
- Narrow MCP/OpenAPI tool boundaries for Iris, Home Assistant, weather, household files, infrastructure health, PDF/image analysis, and `freyja-home-memory`.
- Atlas-side `/open-webui-tools` policy gateway for Open WebUI tool calls.
- Secret-free `/open-webui-tools` OpenAPI schema export for Open WebUI tool import.

Iris remote capability contract:

- Read-only remote actions: `calendar.read`, `reminders.read`.
- Approval-required remote actions: `calendar.create`, `reminders.create`, `imessage.send.approved`, `shortcuts.run`.
- HomePod-related flows must enter through an approved Apple Shortcut; there is no separate direct HomePod control path.
- Iris Apple actions require an active macOS user session and are restricted to Tailnet or Atlas-mediated access.
- Children receive no Iris Apple operations.

The stopped Iris duplicate's local Open WebUI resource tables were empty:

```text
knowledge=0
knowledge_file=0
tool=0
function=0
memory=0
```

Evidence artifact from the obsolete local duplicate:

```text
certification/reports/open-webui-home-resources-live-counts.json
```

Repeatable local count command, valid only on the actual Open WebUI host:

```bash
scripts/count-open-webui-home-resources-live.py
```

Prepare the offline resource rows with a dry-run first:

```bash
scripts/apply-open-webui-home-resources-offline.py \
  --import-json certification/reports/open-webui-home-resources-export.json
```

When the local `/app/backend/data/webui.db` path is not available, the dry-run
snapshots `webui.db`, `webui.db-wal`, and `webui.db-shm` from
`freyja-open-webui-atlas-open-webui-1`. It does not mutate the running database.

Current dry-run evidence:

```text
certification/reports/open-webui-home-resources-offline-dry-run.json
```

Latest live dry-run:

```text
ready=false
applied=false
dry_run_snapshot.container="freyja-open-webui-atlas-open-webui-1"
reason="missing or ambiguous Open WebUI owner user"
knowledge_count=3
tool_count=6
memory_policy_count=4
```

Only after a real owner user exists, apply with an explicit writable `--db` and
`--apply`. Add `--owner-user-id <id>` when multiple users exist or when you need
to force a specific owner.
The importer creates a database backup before writing and touches only
`knowledge`, `tool`, and `memory`.

This is expected until a real owner user or authenticated Open WebUI admin session exists. The source/export artifacts are safe for source control and contain no secrets or private content.

## Channel Service Boundary

`freyja-channels` policy lives at:

```text
config/freyja-channels.yaml
```

The deterministic channel service implementation lives at:

```text
src/freyja/channels.py
src/freyja/channel_transports.py
```

Readiness check:

```bash
scripts/check-freyja-channels-readiness.py \
  --output certification/reports/freyja-channels-readiness.json
```

Latest readiness:

```text
deterministic_gateway_only=true
telegram.transport_adapter=TelegramLongPollingTransport
telegram.ready_for_live_round_trip=false
telegram.missing_configuration=["TELEGRAM_ALLOWED_USER_IDS","TELEGRAM_BOT_TOKEN","TELEGRAM_IDENTITY_MAP","OPEN_WEBUI_API_KEY"]
signal.transport_adapter=SignalCliRestTransport
signal.ready_for_live_round_trip=false
signal.missing_configuration=["SIGNAL_ALLOWED_SENDERS","SIGNAL_ACCOUNT_NUMBER","SIGNAL_IDENTITY_MAP","OPEN_WEBUI_API_KEY","SIGNAL_REST_API_URL"]
telegram.next_actions=[
  "Create or choose the Telegram bot and set TELEGRAM_BOT_TOKEN outside source control.",
  "Set TELEGRAM_ALLOWED_USER_IDS with reviewed family sender IDs; keep an empty allowlist as deny-all.",
  "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
  "Set OPEN_WEBUI_API_KEY outside source control.",
  "Run scripts/run-freyja-channels-telegram-pilot.py --dry-run before enabling the long-polling pilot."
]
signal.next_actions=[
  "Set SIGNAL_REST_API_URL for the existing signal-cli-rest-api endpoint.",
  "Set SIGNAL_ACCOUNT_NUMBER for the registered dedicated Signal account.",
  "Set SIGNAL_ALLOWED_SENDERS with reviewed E.164 family senders; keep an empty allowlist as deny-all.",
  "Map every allowed Signal sender to an approved Freyja identity in SIGNAL_IDENTITY_MAP.",
  "Set OPEN_WEBUI_API_KEY outside source control.",
  "Run scripts/run-freyja-channels-signal-pilot.py --dry-run after signal-cli-rest-api registration is healthy."
]
thread_persistence_store.path="data/freyja-channels/threads.json"
audit_store.path="data/freyja-channels/audit.jsonl"
audit_store.denied_attempts_logged=true
audit_store.response_failures_logged=true
open_webui_client.endpoint="http://127.0.0.1:3001/openai/v1/chat/completions"
open_webui_client.api_key_configured=false
whatsapp.status=disabled
```

The Telegram pilot transport uses Bot API long polling and converts updates
into deterministic `ChannelMessage` records. The Signal transport uses the
existing `signal-cli-rest-api` pathway and converts received data-message
events into the same `ChannelMessage` shape. Both fail closed when credentials
or allowlists are absent.

The channel gateway persists hashed sender/agent thread mappings in
`data/freyja-channels/threads.json` and reuses them across service instances.
Audit events append to `data/freyja-channels/audit.jsonl`; raw senders and
message bodies are not logged. Denied attempts and Open WebUI response failures
are audited with only hashed sender, channel, routing, and error metadata.

The Open WebUI client maps permitted channel agents to the imported Open WebUI
model IDs and posts to `/openai/v1/chat/completions` only when
`OPEN_WEBUI_API_KEY` is configured.

Telegram pilot runner:

```bash
scripts/run-freyja-channels-telegram-pilot.py --dry-run \
  --output certification/reports/freyja-channels-telegram-pilot.json
```

The runner uses `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`,
`TELEGRAM_IDENTITY_MAP`, and `OPEN_WEBUI_API_KEY`. Its dry-run report records
only boolean readiness checks, including whether every allowlisted sender has
an identity mapping. In run mode it advances `data/freyja-channels/telegram.offset`
after each observed update and sends the Open WebUI response back with Telegram
`sendMessage`.

Signal pilot runner:

```bash
scripts/run-freyja-channels-signal-pilot.py --dry-run \
  --output certification/reports/freyja-channels-signal-pilot.json
```

The runner uses `SIGNAL_ACCOUNT_NUMBER`, `SIGNAL_REST_API_URL`,
`SIGNAL_ALLOWED_SENDERS`, `SIGNAL_IDENTITY_MAP`, and `OPEN_WEBUI_API_KEY`. Its
dry-run report records only boolean readiness checks, including whether every
allowlisted sender has an identity mapping. In run mode it receives messages
through the existing `signal-cli-rest-api` pathway, routes them through
`freyja-channels`, and sends the Open WebUI response back through Signal.

It remains deterministic:

```text
Telegram/Signal sender -> verified family identity -> permitted agent -> Open WebUI API -> response
```

It must not route models or contain independent agent intelligence. Empty allowlists are denied. WhatsApp stays documented and disabled until a secured public webhook is deliberately approved.

Build order remains:

1. Telegram pilot for Joe using long polling.
2. Signal through the existing `signal-cli-rest-api` stack.
3. WhatsApp disabled.

## Proactive Behavior

Proactive policy lives at:

```text
config/freyja-proactive.yaml
```

The disabled-by-default planner lives at:

```text
src/freyja/proactive.py
```

Readiness check:

```bash
scripts/check-freyja-proactive-readiness.py \
  --output certification/reports/freyja-proactive-readiness.json
```

Dry-run dispatch preview:

```bash
scripts/dry-run-freyja-proactive.py \
  --output certification/reports/freyja-proactive-dry-run.json
```

Latest readiness:

```text
candidate_count=27
ready_schedule_ids=[]
all_disabled_by_default=true
dry_run.dispatch_count=27
dry_run.would_send_count=0
```

Scheduled briefings, reminder follow-ups, calendar-conflict warnings, and
system-health notifications are defined there but disabled by default. They
must not be enabled until chat stability, recipient verification, destination
verification, per-schedule approval, and a dry run are complete.

## Verification

Consolidated final-deliverable artifacts:

```text
certification/reports/open-webui-home-agent-deliverable.json
certification/reports/open-webui-home-agent-deliverable.md
certification/reports/open-webui-home-agent-completion-audit.json
certification/reports/open-webui-home-agent-chat-smoke.json
certification/reports/freyja-proactive-dry-run.json
certification/reports/open-webui-tools-openapi.json
certification/reports/open-webui-backup-rollback-audit.json
certification/reports/open-webui-home-agent-secret-safety.json
```

Regenerate them with:

```bash
scripts/build-open-webui-home-agent-bundle.py \
  --output-json certification/reports/open-webui-home-agent-deliverable.json \
  --output-md certification/reports/open-webui-home-agent-deliverable.md
```

Regenerate the requirement-by-requirement completion audit with:

```bash
scripts/audit-open-webui-home-agent-completion.py \
  --output certification/reports/open-webui-home-agent-completion-audit.json
```

Refresh all credential-free evidence in dependency order with:

```bash
scripts/refresh-open-webui-home-agent-evidence.py
```

This command snapshots the running Open WebUI database, refreshes live inventory,
model-proxy, agent import, access, resource, tool, channel, proactive,
Freyja 4.1 preservation, backup/rollback, secret-safety, readiness,
completion-audit, and final deliverable reports, and writes
`certification/reports/open-webui-home-agent-evidence-refresh.json`.
It treats the readiness summary's external-auth/credential pending exit as an
expected state, but fails on any credential-free evidence failure.

Latest completion audit:

```text
complete=false
status_counts={"complete":9,"auth_gated":3,"credential_gated":1,"partial":2}
```

Focused verification added on 2026-09-04:

```bash
.venv/bin/pytest -q \
  tests/test_home_memory.py \
  tests/test_open_webui_home_agents.py \
  tests/test_freyja_channels_policy.py \
  tests/test_freyja_proactive_policy.py \
  tests/test_open_webui_home_agent_verify.py
```

Result:

```text
117 passed, 1 warning
```

Full local test suite result:

```text
1566 passed, 1 skipped, 1 warning
```

Covered:

- required `freyja-home-memory` operations
- unauthorized personal-scope read denial
- Benedict restricted-scope write isolation
- complete five-agent Open WebUI definition inventory
- Benedict/child agent tool constraints
- deterministic `freyja-channels` policy
- deterministic `freyja-channels` service routing
- Telegram long-polling transport parser and fail-closed credential gate
- Signal REST transport parser and fail-closed registration gate
- Telegram/Signal fail-closed policy shape
- Telegram/Signal readiness reporting without secret values
- WhatsApp disabled policy
- proactive jobs defined but disabled by default
- proactive dry-run dispatches suppress all sends
- live verifier report shape
- authenticated chat smoke report shape
- Open WebUI tool gateway fail-closed authorization
- Open WebUI tool gateway OpenAPI export
- Open WebUI backup rollback integrity audit
- Open WebUI home-agent secret safety audit

Open WebUI tool gateway readiness:

```bash
scripts/check-open-webui-tools-gateway.py \
  --output certification/reports/open-webui-tools-gateway-readiness.json
```

OpenAPI schema export:

```bash
scripts/export-open-webui-tools-openapi.py \
  --output certification/reports/open-webui-tools-openapi.json
```

Latest result:

```text
ok=true
operation_count=20
execution_statuses.read_only="dry_run_available"
execution_statuses.confirmed_write="confirmed_not_configured"
live_side_effects_invoked=false
openapi.paths=["/open-webui-tools","/open-webui-tools/invoke"]
```

The Freyja 5 gateway was rebuilt and restarted after adding this route. Live
authenticated checks confirmed `/open-webui-tools` returns the policy catalog
and that Jenna receives `403` for `infrastructure.health`.

Live verifier:

```bash
scripts/open-webui-home-agent-verify.py \
  --model-proxy-url http://127.0.0.1:3001/openai \
  --output certification/reports/open-webui-home-agent-live.json
```

Latest result:

```text
ok=true
auth_required_checks_pending=["open_webui_authenticated_models"]
optional_checks_pending=[]
```

Current verifier defaults also probe the running model-proxy container directly,
so the latest `optional_checks_pending` value is `[]` when
`freyja-open-webui-atlas-model-proxy-1` is available. The separate in-network
model-proxy catalog report still records the proxy model inventory as
independent evidence.

Authenticated five-agent chat smoke:

```bash
OPEN_WEBUI_API_KEY=... scripts/smoke-open-webui-home-agent-chats.py \
  --output certification/reports/open-webui-home-agent-chat-smoke.json
```

Single readiness summary:

```bash
scripts/summarize-open-webui-home-agent-readiness.py
```

This command reads only existing secret-free reports and writes
`certification/reports/open-webui-home-agent-readiness-summary.json` plus a
Markdown summary. It exits nonzero until post-auth activation, five-agent chat
smoke, Telegram, and Signal are all ready.

Without an API key the smoke runner writes a pending, secret-free report:

```text
status="pending"
reason="OPEN_WEBUI_API_KEY not supplied"
```

When an authenticated Open WebUI admin/session token is available, the runner
posts one short non-private completion request through `/openai/v1/chat/completions`
for each imported agent model and records only status, timing, expected Vulcan
profile, and response presence.

The verifier also checks that the protected fallback tag exists and that the
side-by-side services present before this work are still running:

```text
freyja-4.1-baseline-before-5.0-20260831-161448
freyja-open-webui-atlas-open-webui-1
freyja-open-webui-atlas-model-proxy-1
freyja3-agent-gateway-1
freyja3-litellm-1
```

Live checks completed:

- Docker stack observed running.
- Open WebUI `/api/version` returned `0.11.3`.
- Open WebUI unauthenticated `/api/config` returned auth enabled.
- Open WebUI data volume backup succeeded.
- Open WebUI backup archive integrity audit succeeded and confirmed `webui.db` is present without extracting or printing database contents.
- Freyja 5 side-by-side gateway deployed on `http://127.0.0.1:8500`.
- Freyja 5 `/health` returned healthy.
- Freyja 5 `/v1/models` returned Open WebUI-visible agent model entries.
- Open WebUI `model-proxy` `/v1/models` returned all six Freyja agent model IDs from inside the compose network.

Repeatable model-proxy catalog command:

```bash
scripts/check-open-webui-model-proxy-catalog.py
```
- Freyja 5 `/freyja-home-memory/operations` returned all six required operations.
- Live HTTP scope test: Joe wrote/read `personal:joe`; Beth read of `personal:joe` returned `403`.
- `certification/reports/open-webui-home-agent-live.json` records repeatable live verification evidence without secrets.
- `certification/reports/open-webui-model-proxy-catalog.json` records the model-proxy catalog evidence without secrets.
- `certification/reports/open-webui-home-agents-import.json` records reviewable Open WebUI model import payloads without secrets.
- `certification/reports/open-webui-home-agents-offline-apply.json` records sanitized evidence that the five agent model rows exist in Open WebUI's database.
- `certification/reports/open-webui-home-agent-access-audit.json` records sanitized evidence that the imported agent rows contain the intended read-group metadata.
- `certification/reports/open-webui-home-agent-access-bind-dry-run.json` records the current no-write access-binding plan and missing real users.
- `certification/reports/open-webui-home-resources-export.json` records reviewable Knowledge, native-memory, and tool resource payloads without secrets or private content.
- `certification/reports/open-webui-home-resources-live-counts.json` records sanitized live Open WebUI Knowledge/tool/native-memory table counts.
- `certification/reports/open-webui-home-resources-offline-dry-run.json` records the no-write resource importer plan and owner-user blocker.
- `certification/reports/open-webui-home-agent-deliverable.json` and `.md` consolidate endpoint map, rollback pointers, verification status, blockers, artifacts, and exact next action.
- `certification/reports/open-webui-backup-rollback-audit.json` records backup tar integrity, checksum, `webui.db` presence, rollback-doc coverage, and the verified `deploy/compose/open-webui/compose.yaml` rollback compose path without private content.
- `certification/reports/open-webui-home-agent-secret-safety.json` records scoped secret-pattern and private-content flag checks for the current home-agent artifact set.
- `certification/reports/open-webui-home-agent-completion-audit.json` records requirement-by-requirement completion status from current evidence.
- `certification/reports/open-webui-home-agent-platform-inventory.json` records host roles, endpoint map, running Atlas services, and credential locations without secret values.
- `certification/reports/open-webui-home-agent-post-auth-activation.json` records the current dry-run post-auth activation plan.
- `certification/reports/open-webui-inference-policy-audit.json` records local-default Vulcan inference, model profile, guard, and unload policy evidence.
- `certification/reports/freyja-channels-readiness.json` records deterministic channel readiness, file-backed thread persistence, and audit-log redaction without sender values or tokens.
- `certification/reports/freyja-proactive-readiness.json` records disabled-by-default proactive schedule readiness with no message bodies.
- `certification/reports/freyja41-preservation-audit.json` records Freyja 4.1 preservation evidence: baseline tag, rollback artifacts, side-by-side Freyja 5, protected running services, `freyja3-agent-gateway` root identity on `http://127.0.0.1:8300/`, health on `http://127.0.0.1:8300/health`, inference health on `http://127.0.0.1:8300/freyja3/inference/health`, and `freyja3-litellm` reachability/auth boundary on `http://127.0.0.1:4001/health`.

Blocked or still pending:

- Authenticated Open WebUI API tests for all five agents require Joe's Open WebUI API key or browser session.
- Telegram round trip requires Joe's bot token/allowlist to be configured outside source control.
- Signal round trip requires registered `signal-cli-rest-api` credentials.
- Open WebUI user/group assignment cannot be completed offline yet because the live database currently has `user_count=0` and `group_count=0`. Joe must create/sign in to Open WebUI or provide an admin API/browser session.
- Freyja 4.1 fallback preservation is verified through the protected legacy Freyja3 gateway contract on port `8300`; no separately named Freyja 4.1 endpoint is defined in current repo evidence.

## Requirement Matrix

| Requirement | Current evidence | Status |
| --- | --- | --- |
| Inspect repository, services, Docker stacks, endpoints, credential locations | Repo files, Docker `ps`, Open WebUI collector output, redacted env capture, platform inventory report | Complete for current known Atlas/Vulcan/Iris/Hera topology |
| Identify Open WebUI host and Vulcan path | `docs/operations/open-webui-atlas.md`, live containers, model-proxy env | Complete for current deployment |
| Back up Open WebUI data/config/version/image/volume | `logs/open-webui-diagnostics/home-agent-20260904T174214Z/`, `certification/reports/open-webui-backup-rollback-audit.json` | Complete for current deployment |
| Recoverable git checkpoint before changes | `.codex-checkpoints/pre-open-webui-home-agent-20260904T133828-0400.patch` | Complete |
| Keep secrets out of output/source | Redacted collector output, no-secret manifests, `certification/reports/open-webui-home-agent-secret-safety.json` | Complete for current home-agent artifact set; keep running before commits |
| Inference local by default through Vulcan | Open WebUI compose/model-proxy, Atlas docs, inference policy audit | Implemented and policy-audited; authenticated live chat response still needs Open WebUI API/session |
| Explicit model profiles | `config/open-webui-home-agents.yaml` | Complete as source-controlled definitions |
| Five Open WebUI agents | `config/open-webui-home-agents.yaml`, Freyja 5 `/v1/models`, model-proxy catalog report, import payload export, offline Open WebUI model-table import evidence, access metadata audit | Imported into Open WebUI model table with intended read-group metadata; authenticated API/UI verification and real user/group binding pending |
| Benedict local-only isolation | Agent manifest, home-memory tests, access metadata audit | Complete at source/API policy layer; real Open WebUI Beth group binding pending account creation/auth |
| Native per-user Open WebUI memory | `config/open-webui-home-resources.yaml`, resource export, resource importer dry-run | Source policy/import path prepared; live rows require owner user/authenticated import |
| Shared household Knowledge | `config/open-webui-home-resources.yaml`, resource export, resource importer dry-run | Source policy/import path prepared; live collection rows require owner user/authenticated import |
| Scoped `freyja-home-memory` service | `/freyja-home-memory` router, tests, live `8500` endpoint | Deployed in side-by-side Freyja 5 gateway |
| Tool boundaries | Agent manifest, resource manifest/export, resource importer dry-run, existing Freyja tools, model-proxy agent forwarding | Source policy/import path prepared; Open WebUI tool enablement pending owner user/auth |
| Messaging channels | Existing Telegram/Signal connectors, `config/freyja-channels.yaml`, `src/freyja/channels.py`, channel readiness report, file-backed thread persistence test | Deterministic gateway and restart-safe thread persistence implemented/tested; live Telegram/Signal round trips pending credentials |
| Proactive behavior disabled by default | `config/freyja-proactive.yaml`, `src/freyja/proactive.py`, proactive readiness report | Implemented/tested as disabled-by-default candidates; live sends pending chat/destination/recipient verification and approval |
| Repeatable verification | New and existing pytest coverage | Partial; live external tests pending credentials |
| No regression to Freyja 4.1 | Baseline tag, side-by-side protected service check in live verifier, `freyja41-preservation-audit.json`, protected legacy endpoint probes including `/freyja3/inference/health` | Complete: preservation invariants, protected legacy endpoint reachability, and legacy inference-health surface verified through the port `8300` Freyja3 gateway contract |
