# Freyja 5.0 Msty Go -> Nexus -> Vulcan Integration

Last updated: 2026-09-05.

## Working Route

- Host agent plane: Iris / Msty Go.
- Gateway: Vulcan Msty Nexus at `http://100.94.80.21:3939`.
- Msty Go provider id: `vulcan-nexus`.
- Msty Go provider base URL on Iris: `http://100.94.80.21:3939/v1`.
- Freyja Msty Go agent model: `@preset/freyja-coder`.
- Nexus resolution: `@preset/freyja-coder` -> `vulcan-ollama/qwen3-coder-next:q4_K_M`.

`@preset/freyja-fast-local` remains the lightweight route and still resolves to
`vulcan-ollama/qwen2.5:7b`. Do not repurpose it for persistent Msty Go agents
with the full agent prompt and tool bundle.

## What Was Wrong

There were three independent issues:

1. Freyja was still configured on `@preset/freyja-fast-local`, whose underlying
   `qwen2.5:7b` model corrupts output under Msty Go's large system prompt and
   tool array.
2. Freyja's Msty Go bot capability flags did not expose Terminal/Web/Search
   consistently.
3. Freyja's own instruction metadata told the model to use only listed grants,
   but the list did not include terminal or web/search grants. That made the
   model refuse shell requests even after the UI showed Terminal access.

Direct Nexus tests proved `gpt-oss:20b`, `qwen2.5:32b-instruct`,
`qwen3:30b-a3b`, `qwen3-coder-next:q4_K_M`, and `gpt-oss:120b` can all emit an
OpenAI-compatible `tool_calls` response for a simple `shell` tool. The failure
was not Tailscale, Nexus auth, basic streaming, or Nexus tool-call translation.

As of 2026-09-02, `qwen3.5:122b-a10b` is being added as a strong-reasoning
candidate for comparison with `gpt-oss:120b`. The Ollama artifact is an 81 GB
pull on Vulcan and was started in the background with progress logged at:

```text
~/.freyja/logs/qwen3.5-122b-pull.log
```

Msty Go already has a `vulcan-nexus` custom model entry for
`vulcan-ollama/qwen3.5:122b-a10b`. Open WebUI's model proxy also allowlists
`qwen3.5:122b-a10b` and maps it to `vulcan-ollama/qwen3.5:122b-a10b`.
Treat it as pending live validation until `ollama list` on Vulcan shows the
model and Nexus `/v1/models` exposes it.

For the full Msty Go Freyja payload, `@preset/freyja-coder` was the first
existing local route verified to produce a real Msty Go tool request and
complete the tool loop.

## Msty Go Freyja Agent Settings

The live Msty Go database is:

`/Users/freyja/Library/Application Support/Msty Go/msty-go.db`

Before editing, a backup was created next to it using this prefix:

`msty-go.db.backup-before-freyja-agent-local-`

Freyja's bot row should have:

```text
id: freyja
provider_id: vulcan-nexus
model: @preset/freyja-coder
runtime_id: host
approval_mode: balanced
shell_access_enabled: 1
web_access_enabled: 1
search_lens_enabled: 1
container_network_enabled: 0
container_network_mode: off
```

Freyja's custom instructions now explicitly include Terminal/Web tool use:

```text
Terminal and Web access are granted for this agent. When the user asks you to
run a command, inspect files, search the web, or fetch a web page, call the
matching Msty Go tool instead of saying you lack access. For terminal commands
use the shell tool and provide the requested command as its command argument.
```

The Freyja metadata grant list now includes:

```json
[
  "terminal.run",
  "shell.exec",
  "web.search",
  "search_lens.read"
]
```

## Verification

Passed:

- Msty Go Freyja agent starts on `@preset/freyja-coder`.
- Msty Go UI shows `freyja-coder`, resolving through Nexus.
- Streaming chat path is active; Msty Go sends streaming OpenAI-compatible chat
  requests.
- Terminal tool call: Freyja requested approval for `pwd`, Msty Go executed it,
  and Freyja returned:

```text
/Users/freyja/Library/Application Support/Msty Go/workspaces/freyja
```

- Subsequent normal response after tool execution: `AFTER TOOL OK`.
- Web/fetch tool call: Freyja attempted `web_search`, received the expected
  local service error because Docker is not running for Msty Go's managed search
  container, then recovered with `web_fetch` and returned the Msty docs page
  title plus `https://docs.msty.ai`.

Failed or not adopted:

- `@preset/freyja-fast-local` / `qwen2.5:7b` is not suitable for the full Msty
  Go agent payload.
- For large general chat, prefer plain `vulcan-ollama/qwen2.5:72b` over
  `vulcan-ollama/qwen2.5vl:72b`. The plain 72B route returned normal visible
  assistant content in direct Nexus testing and was added to Msty Go as
  `Qwen 2.5 72B General Local` with chat/reasoning capability only.
- `vulcan-ollama/qwen2.5vl:72b` should be kept for vision/document work rather
  than normal daily chat defaults.
- `vulcan-ollama/gpt-oss:120b` is reachable, but it can emit useful text in a
  `reasoning` field while leaving assistant `content` empty or truncated under
  some settings. Do not use it as a default WebUI/Msty Go chat model until the
  response adapter reliably surfaces final answer content.
- `vulcan-ollama/qwen3.5:122b-a10b` is configured for testing only while the
  81 GB Vulcan pull completes. Use the same constrained reasoning tool policy
  as `gpt-oss:120b` and `qwen2.5:72b`: web/search, ask-user, task-management,
  and sub-agent/delegation tools only.
- `vulcan-ollama/gpt-oss:20b` can emit tool calls directly through Nexus, but
  under the full Freyja Msty Go prompt it repeatedly refused shell access rather
  than calling the tool.
- `@preset/freyja-agent-local` does not currently exist in Nexus; the gateway
  returns `MODEL_NOT_FOUND`.
- Msty Go managed `web_search` is unavailable until Docker Desktop is running
  or a web-search key is configured in Msty Go. `web_fetch` is working.

## Pattern for Other Agents

For Benedict, Cloyd, Jenna, and other persistent Msty Go agents:

1. Keep the provider on `vulcan-nexus`.
2. Use a semantic Nexus preset that maps to a model proven under the full Msty Go
   prompt and tool array. Until `@preset/freyja-agent-local` exists, use
   `@preset/freyja-coder` for tool-heavy local agents.
3. Keep lightweight chat routes such as `@preset/freyja-fast-local` for short
   non-agent interactions only.
4. Make the Msty Go capability flags and the instruction metadata grants agree.
   If Terminal/Web are enabled in the UI, the instruction grant list must include
   terminal and web grants and must tell the model to call Msty Go tools instead
   of refusing.
5. Leave approval mode at `balanced` unless a narrower or broader policy is
   intentionally chosen. Balanced approval correctly prompted before running
   `pwd`.

## Remaining Blockers

- Msty Go mobile beta access remains an external availability blocker. Freyja is
  configured with Mobile access, but broader mobile validation depends on the
  mobile beta path being available.
- A true Nexus semantic preset such as `@preset/freyja-agent-local` should be
  created through Nexus once a writable preset-management surface is available.
  The current gateway exposes `GET /v1/presets`; ad hoc `/api/*` preset routes
  were not available.

## 2026-09-02 Autonomous Agent Plane Update

Iris is confirmed as the current canonical Msty Go host:

```text
hostname: iris.lan
LAN addresses observed: 10.1.10.136, 10.1.10.59
Tailscale: 100.115.228.56
Msty Go database: /Users/freyja/Library/Application Support/Msty Go/msty-go.db
```

Vulcan inference is reachable directly from Iris:

```text
Vulcan Nexus: http://100.94.80.21:3939
Msty Go provider endpoint: http://100.94.80.21:3939/v1
Vulcan Ollama: http://100.94.80.21:11434
LAN fallback: http://10.1.10.114:3939
```

The existing Nexus bearer token was reused from Msty Go/provider and launchd
configuration only in process memory. It was not printed into documentation or
committed.

Before material Msty Go database edits, a consistent SQLite backup was created:

```text
/Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-agent-plane-align-consistent-20260902-082334
```

Current Msty Go provider:

```text
id: vulcan-nexus
name: Vulcan Nexus
type: openai
base_url: http://100.94.80.21:3939/v1
api_key: configured
metadata: source=freyja5, semantic_gateway=msty-nexus, machine=vulcan
```

On 2026-09-05, a native Msty Go Cloyd chat initially returned a Nexus 401
because the Msty Go provider API key did not match the live Freyja 5
`NEXUS_API_KEY`. A DB backup was created before aligning only the
`vulcan-nexus` provider key:

```text
/Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-native-recall-token-align-20260905-140748
```

The five-agent audit verifies the provider key is configured and matches the
expected Nexus key when `NEXUS_API_KEY` is supplied to the audit process; the
key value is not written to the report.

Current canonical Msty Go agent rows:

| Agent | Bot id | Workspace | Msty Go model | Shell | Web/Search | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Freyja | `freyja` | Msty Go `workspaces/freyja` | `@preset/freyja-coder` | on | on/on | Proven first and kept as the baseline. |
| Cloyd | `cloyd-gibbler` | Msty Go `workspaces/cloyd-gibbler` | `@preset/freyja-coder` | on | on/on | Tool-heavy Joe/coding agent. Re-aligned from `@preset/freyja-fast-local` on 2026-09-05. |
| Benedict | `benedict` | Msty Go `workspaces/benedict` | `@preset/freyja-strong-local` | off | on/on | Beth personal agent. |
| Agent 44 | `agent-47` | Msty Go `workspaces/agent-47` | `@preset/freyja-fast-local` | off | on/on | Existing id preserved for compatibility; display name now Agent 44. |
| Jenna | `jennacide` | Msty Go `workspaces/jennacide` | `@preset/freyja-fast-local` | off | on/on | Jenna personal agent. |
| Benedict Paralegal | `benedict-paralegal` | Msty Go `workspaces/benedict-paralegal` | `@preset/benedict-paralegal-local` | off | off/off | Kept as an isolated local-only enclave path. |

On 2026-09-05, the live Msty Go database was backed up with prefix:

```text
msty-go.db.backup-before-five-agent-goal-
```

The five requested agents now share a Msty Go-owned memory pack:

```text
pack id: freyja5-shared-household
title: Freyja 5 Shared Household Memory
mounted bots: freyja, cloyd-gibbler, benedict, agent-47, jennacide
excluded: benedict-paralegal
```

The memory pack is intentionally initialized without private content. Its stored
privacy note limits it to authorized shared household memory for Freyja, Cloyd,
Benedict, Agent 44, and Jenna, and excludes Benedict restricted/paralegal
material.

A non-private canary revision was added for persistence and cross-agent recall
validation:

```text
revision: freyja5-shared-household-rev2-canary
saved_by: cloyd-gibbler
item id: five-agent-shared-canary-20260905
content: Five-agent shared memory canary saved on 2026-09-05 for persistence and cross-agent recall validation.
```

After a Freyja 5 OpenAI-compatible service restart, the current Msty Go memory
pack revision and search document were still readable through all five bot
mounts: `freyja`, `cloyd-gibbler`, `benedict`, `agent-47`, and `jennacide`.

Remote/channel state observed:

```text
Freyja: msty_mobile -> msty-mobile:all-devices; Telegram trigger freyja
Cloyd: Telegram trigger cloyd; existing WhatsApp binding retained as primary
Benedict: Telegram trigger benedict
Agent 44: Telegram trigger agent44
Jenna: Telegram trigger jenna
Benedict Paralegal: Telegram trigger paralegal, but treated as isolated
```

Live verification performed on 2026-09-02:

- `GET /v1/models` through `http://100.94.80.21:3939/v1` returned Nexus preset
  models using the configured bearer token.
- Direct authenticated completion through `@preset/freyja-coder` returned
  `IRIS_TO_VULCAN_OK` from `qwen3-coder-next:q4_K_M`.
- Direct authenticated completions through `@preset/freyja-coder`,
  `@preset/freyja-strong-local`, `@preset/freyja-fast-local`, and
  `@preset/benedict-paralegal-local` all returned
  `DIRECT_PROVIDER_ROW_OK` after the Msty Go provider row was moved to direct
  Vulcan Nexus.
- Freyja 5 OpenAI-compatible LaunchAgent on `127.0.0.1:8503` listed:
  `agent/freyja`, `agent/cloyd-gibbler`, `agent/benedict`,
  `agent/benedict-paralegal`, `agent/agent-47`, and `agent/jennacide`.
- Live `POST /v1/chat/completions` calls to those six model ids returned
  `LIVE_AGENT_OK` with `egress_state=local-only`.
- Benedict Paralegal accepted only the isolated `user=paralegal` context for
  the private route and denied a Beth-context request with HTTP 403.

Live verification performed on 2026-09-05:

- Msty Go database contains provider `vulcan-nexus` with base URL
  `http://100.94.80.21:3939/v1` and an API key configured.
- Msty Go database contains the five requested bot rows: `freyja`,
  `cloyd-gibbler`, `benedict`, `agent-47`, and `jennacide`.
- Msty Go database contains shared memory pack `freyja5-shared-household`
  mounted to those five bots.
- Freyja 5 OpenAI-compatible LaunchAgent on `127.0.0.1:8503` is running.
- `GET /v1/models` on `127.0.0.1:8503` lists the five agent model ids:
  `agent/freyja`, `agent/cloyd-gibbler`, `agent/benedict`,
  `agent/agent-47`, and `agent/jennacide`.
- Live `POST /v1/chat/completions` calls to those five model ids succeeded
  with `provider=nexus`, `egress_state=local-only`, and Nexus endpoint metadata.
- Distinct scoped OpenAI-compatible gateway endpoints were added to the existing
  Freyja 5 service. Each endpoint exposes only its own agent model and rewrites
  chat requests to that model before using the existing deterministic gateway
  and Nexus-backed runtime:

| Agent | Models endpoint | Chat endpoint | Forced model |
| --- | --- | --- | --- |
| Freyja | `/agents/freyja/v1/models` | `/agents/freyja/v1/chat/completions` | `agent/freyja` |
| Cloyd | `/agents/cloyd/v1/models` | `/agents/cloyd/v1/chat/completions` | `agent/cloyd-gibbler` |
| Benedict | `/agents/benedict/v1/models` | `/agents/benedict/v1/chat/completions` | `agent/benedict` |
| Agent 44 | `/agents/agent-44/v1/models` | `/agents/agent-44/v1/chat/completions` | `agent/agent-47` |
| Jenna | `/agents/jenna/v1/models` | `/agents/jenna/v1/chat/completions` | `agent/jennacide` |

- Live scoped endpoint smoke calls to all five `/agents/{agent}/v1/models` and
  `/agents/{agent}/v1/chat/completions` endpoints succeeded after restarting
  `com.freyja-os.freyja5-openai`. The request body intentionally used
  `agent/freyja` for every chat call; each scoped endpoint forced its own model
  and returned `provider=nexus` plus `egress_state=local-only`.
- Focused tests for scoped endpoints, existing Open WebUI agent smoke,
  Freyja 5 completion audit, readiness summary, and channel deployment pass:
  29 tests passed with one upstream Starlette deprecation warning.
- Telegram Msty Go bindings now exist for all five requested agents on channel
  `telegram-freyja-home`. Freyja and Cloyd were added as secondary bindings so
  Freyja's existing Msty mobile primary binding and Cloyd's existing WhatsApp
  primary binding were preserved.
- Msty Go app restart validation passed. After quitting and reopening Msty Go,
  the live SQLite store still contained provider `vulcan-nexus`, all five bot
  rows, the five Telegram bindings, and the `freyja5-shared-household` memory
  pack mounted to all five bots with current revision
  `freyja5-shared-household-rev2-canary`.
- Existing repo Telegram LaunchAgent `com.freyja-os.telegram-gateway` was
  installed into `~/Library/LaunchAgents`, loaded, and observed running.
  Safe heartbeat files for the Freyja and Benedict Telegram runner instances
  reported `enabled=true`, `token_configured=true`, `allowed_user_count=1`, and
  `last_poll_status=ok`.
- Signal support remains limited. The live Msty Go database has no Signal
  channel, channel preset, or bot binding rows. The existing repo
  `signal-cli-rest-api` container is healthy inside the compose network, but no
  host port is published and the Signal pilot could not reach the REST API from
  this Iris-local path. `SIGNAL_ALLOWED_SENDERS` also remains unset in the
  inspected Signal env file, so a live Signal round trip is not configured.
  Official Msty Go channel docs inspected on 2026-09-05 list Discord,
  Telegram, WhatsApp, and Msty Go mobile routes as supported platforms; Signal
  is not listed there, so no synthetic Msty Go Signal rows were added.
- Freyja's existing Apple services on Iris were checked without rebuilding
  them. `com.freyja-os.macagent` is loaded and running, authenticated health is
  OK, and it advertises Apple Messages, Calendar, Contacts, Mail, Music,
  Browser, and Shortcuts capabilities. Live read checks succeeded for Calendar,
  Messages, Contacts, Mail, and Music. Browser front-tab now returns a
  structured `status=unavailable` response instead of timing out the caller when
  Safari AppleScript hangs.
- `com.freyja-os.imessage-connector` is loaded and running from
  `/Users/freyja/freyja-os-imessage-runtime`. The monitored runtime files match
  this checkout, runtime imports pass, and polling fallback is active.
- Freyja 4.1 preservation audit still reports incomplete because the protected
  Open WebUI containers were not present/running in the local Docker state,
  although the protected legacy Freyja3 gateway endpoints responded and the
  Freyja 5 side-by-side gateway container was healthy.

Running service posture observed on Iris:

```text
com.freyja-os.director: freyja.atlas_app:app on 0.0.0.0:8000
com.freyja-os.freyja5-openai: freyja.main:app on 127.0.0.1:8503
side-by-side Freyja 5 test app: freyja.main:app on 0.0.0.0:8500
extra local Freyja test app: freyja.main:app on 127.0.0.1:8502
com.freyja-os.gateway-remote: 127.0.0.1:8010
com.freyja-os.macagent: 0.0.0.0:8765
com.freyja-os.imessage-connector: running
com.freyja-os.telegram-gateway: running
com.freyja-os.ollama: Iris Ollama on 100.115.228.56:11434
Msty Go app: running
Msty Go local Nexus debug proxy: 127.0.0.1:3940, bypassed by provider row
```

Machine-readable five-agent system audit:

```bash
scripts/five-agent-system-audit.py \
  --gateway-chat-timeout 90 \
  --output certification/reports/five-agent-system-audit.json
```

Latest local result on 2026-09-05: incomplete. Complete items: five Msty Go
agent rows, Vulcan Nexus provider routing, scoped gateway model and chat
endpoints with Nexus/local-only metadata,
shared Msty Go memory pack/mounts/canary, Telegram Msty Go bindings, Open WebUI
same-agent reachability through the authenticated five-agent chat smoke, and
Apple service preservation. Remaining audit gaps: Msty Go Signal bindings,
native Msty Go canary recall, and live Telegram/Signal round-trip evidence.
The audit now verifies the canary in both `memory_pack_revisions` and
`memory_pack_search_docs`; it still requires an actual Msty Go assistant
message containing the canary before marking native chat recall complete.
Current Msty Go Memory Bank docs inspected on 2026-09-05 describe attaching
memory packs to Conversations, Agents, Playbooks, and Scheduled jobs; the live
test covered both Agent and Conversation mounts.
Telegram/Signal round-trip status is read from
`certification/reports/freyja-channels-telegram-pilot.json` and
`certification/reports/freyja-channels-signal-pilot.json`.
Post-change Msty Go app restart persistence is recorded in
`certification/reports/five-agent-msty-go-restart-persistence.json`.

Important caveat: the `127.0.0.1:3940` local debug proxy is still running, but
the canonical Msty Go provider row no longer depends on it. Leave it alone
during this build unless it is intentionally retired later.

Recovery commands:

```bash
launchctl kickstart -k gui/$(id -u)/com.freyja-os.freyja5-openai
launchctl kickstart -k gui/$(id -u)/com.freyja-os.gateway-remote
launchctl kickstart -k gui/$(id -u)/com.freyja-os.macagent
launchctl kickstart -k gui/$(id -u)/com.freyja-os.imessage-connector
launchctl kickstart -k gui/$(id -u)/com.freyja-os.telegram-gateway
```

Remaining blockers:

- Confirm Msty Go continues to use the direct `http://100.94.80.21:3939/v1`
  provider after reboot. App restart persistence is complete after the
  provider-key alignment and conversation-memory mount changes: the provider
  key match, five agent rows, shared memory bot mounts, recall conversation
  mounts, and recall-attempt messages survived a Msty Go quit/reopen cycle.
- Complete native Msty Go mobile validation beyond Freyja's observed
  `msty_mobile:all-devices` binding.
- Decide whether Cloyd/Benedict/Agent 44/Jenna should receive native Msty
  mobile bindings, Telegram bindings, both, or another Msty-native channel.
- Complete Telegram live round-trip validation from an allowed sender. The
  LaunchAgent is running and polling, but the repo channel pilot still needs
  identity-map/API-key readiness or a Msty-native live message proof. The
  current Telegram pilot report has `live_round_trip_complete=false` and
  `handled=0`.
- Configure or validate Signal through Msty Go. Current limitation: no Signal
  integration rows exist in the inspected Msty Go database, and the existing
  repo Signal adapter is blocked by missing sender allowlist/identity mapping
  plus an unreachable host-side Signal REST URL. The current official Msty Go
  channel documentation does not list Signal as a supported channel platform.
  The current Signal pilot report has `live_round_trip_complete=false`,
  `handled=0`, and failure reason `signal_live_run_failed`.
- Open WebUI same-agent reachability is complete via
  `certification/reports/open-webui-home-agent-chat-smoke.json`: all five
  `agent/...` model ids returned HTTP 200 with responses. The broader Open
  WebUI completion audit remains incomplete only because Telegram/Signal
  round-trip verification is still pending.
- Prove memory save/recall across a new session and a service restart. The
  shared memory pack exists, is mounted, contains a non-private canary, and
  survived both a Freyja service restart and an Msty Go app restart. The canary
  is also present in Msty Go's `memory_pack_search_docs` index. Native Msty Go
  chat recall through the UI/API was attempted through Cloyd in Msty Go. After
  the provider key was aligned, Cloyd replied `NOT FOUND`. The Cloyd and Freyja
  recall conversations were then mounted directly to the shared memory pack
  after this backup:

  ```text
  /Users/freyja/Library/Application Support/Msty Go/msty-go.db.backup-before-conversation-memory-mount-20260905-142030
  ```

  Msty Go showed `Memory used: 1` in the Cloyd conversation, but a mounted retry
  still replied `NOT FOUND`. A second native recall attempt through Freyja
  stalled and was stopped, producing `Request canceled`. No Msty Go assistant
  conversation message containing the canary was found in the live database.
- Keep Benedict Paralegal separate unless Beth's dedicated machine becomes the
  canonical enclave host.
- Run live Apple Calendar/iMessage/Shortcuts/MCP validations on Iris without
  changing the current working connectors. Calendar, Messages, Contacts, Mail,
  Music, and Browser read endpoints are now reachable; Safari front-tab content
  remains unavailable when Safari AppleScript hangs, and approved write paths
  were intentionally not exercised without explicit operator approval.
