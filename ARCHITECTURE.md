# Freyja-OS Architecture

**Version:** 0.1 Rev 1
**Status:** Rev 1 family-assistant baseline with Hera/Iris/cloud fallback
**Primary owner:** Joe  
**Project:** Freyja-OS

## 1. Purpose

Freyja-OS is a personal AI orchestration platform designed to combine local models, cloud models, secure messaging, automation tools, memory, and distributed worker computers behind one consistent interface.

The system should:

- Preserve the "Cloyd parity" family-assistant experience: one capable assistant
  that knows the household context, uses tools, and answers naturally.
- Prefer local inference when practical.
- Escalate difficult work or failed local answers to approved cloud models.
- Remain usable from a phone through secure messaging.
- Reuse existing computers as specialized worker nodes.
- Keep model providers, messaging platforms, and tools replaceable.
- Avoid exposing individual agents directly to the public internet.
- Centralize policy, authentication, routing, logging, and cost controls.

Freyja-OS is not intended to be a collection of independent chatbots. It is a coordinated system with one primary Director and a set of controlled capabilities.

---

## 2. Design Principles

### 2.1 One Director

All user requests pass through the Freyja Director. The Director decides which model, tool, memory source, or worker node should handle the request.

No worker agent should independently accept arbitrary public commands.

### 2.2 Local First, Cloud When Necessary

The system should use local Ollama models for routine work and escalate only
when the task requires stronger reasoning, larger context, better tool use, or a
specialized cloud model. Routing policy must serve the family-assistant
experience first; cost optimization is secondary to useful, grounded answers.

### 2.3 Secure Entry Points

Signal is the preferred remote interface. Native iMessage is the Apple-native
secondary interface and HomePod/Shortcut entry path. Telegram may remain
available for testing, but it should not be treated as the primary secure
control path.

### 2.4 Capability Services, Not Uncontrolled Agents

Most system functions should be implemented as services with explicit inputs and outputs:

- Search
- Memory
- Home automation
- File operations
- Vision
- Speech-to-text
- Text-to-speech
- Code execution
- Notifications

The Director invokes these services through defined APIs or tool interfaces.

### 2.5 Least Privilege

Each service should receive only the permissions required for its function. Messaging connectors, file tools, shell tools, and home automation tools should be isolated and permission-scoped.

### 2.6 Replaceable Components

Freyja-OS should avoid hard dependencies on one model provider, vector database, messaging service, or orchestration framework.

---

## 3. Current Operating Constraints

### 3.1 Monthly Cloud Budget

Current recurring AI spending:

- ChatGPT Plus: approximately $20/month
- OpenRouter budget or credits: approximately $20/month
- Total recurring AI spend: approximately $40/month

ChatGPT Plus is used as an interactive engineering and planning environment. It does not replace an API account. OpenRouter is the primary cloud inference path for Freyja-OS.

### 3.2 Available Hardware

The current known hardware pool includes:

- Mac mini M4 with 24 GB unified memory
- Atlas Ryzen Linux server with 32 GB RAM
- NUCBox N105-class mini PC
- Raspberry Pi named Cloyd
- Two older 2011 Mac minis
- Several additional older PCs
- An avatar computer with display, speaker, camera, and local interaction capability
- Future high-capacity local inference PC, when purchased and installed

The architecture assumes existing systems may be reassigned as their
capabilities are tested. The future high-capacity PC is a new Layer 1 inference
node, not a Director replacement and not a public entry point.

### 3.3 Rev 1 Authoritative Host Roles

- Mars: Freyja Director and control plane.
- Atlas: always-on infrastructure services and Signal connector.
- Hera: primary local agent model provider over Tailscale for Rev 1; not core
  always-on control-plane infrastructure.
- Iris: always-on, kept-warm secondary local inference capacity;
  inference-focused and not a development host.
- Future inference PC: dedicated Layer 1 local heavy-inference node when
  available; it should implement the same private provider contract.
- OpenRouter and future Ollama Cloud: approved cloud escalation layers, not the
  default source of truth.

---

## 4. High-Level Architecture

```text
                         +----------------------+
                         |        User          |
                         | iPad / iPhone / Mac   |
                         +----------+-----------+
                                    |
                  +-----------------+-----------------+
                  |                                   |
             Signal Bridge                      iMessage / HomePod
             Primary Remote                     Secondary Apple Path
                  |                                   |
                  +-----------------+-----------------+
                                    |
                         +----------v-----------+
                         |   Freyja Gateway      |
                         | Auth / Rate Limits    |
                         | Session Handling      |
                         +----------+-----------+
                                    |
                         +----------v-----------+
                         |  Freyja Director      |
                         | Intent Classification |
                         | Policy Enforcement    |
                         | Model Routing         |
                         | Tool Orchestration    |
                         +---+---------+---------+
                             |         |
              +--------------+         +----------------+
              |                                         |
       +------v------+                           +------v------+
       | Local LLMs  |                           | Cloud LLMs  |
       | Ollama      |                           | OpenRouter  |
       +------+------+                           +------+------+
              |                                         |
              +------------------+----------------------+
                                 |
                        +--------v---------+
                        | Capability Layer |
                        +--------+---------+
                                 |
       +-------------------------+---------------------------+
       |             |              |             |          |
   Memory         Search         Automation      Files     Voice/Vision
       |             |              |             |          |
   PostgreSQL     Web/MCP       Home Assistant   Storage   Worker Nodes
   Vector Store
```

---

## 5. Node Roles

## 5.1 Mars — Director and Control Plane

**Primary role:** Freyja authority, routing, policy, and control plane

Recommended responsibilities:

- Freyja Director service
- Request routing
- Conversation state
- Policy and permission checks
- OpenRouter client
- Tool registry
- Session management
- Cost accounting
- Administrative interface

Mars is the logical center of Freyja-OS. It should remain the single authority
for deciding how requests are processed. Messaging connectors and worker nodes
must forward requests to Mars rather than making independent routing decisions.

## 5.2 Atlas Ryzen Server — Infrastructure and Signal Node

**Primary role:** Always-on backend services

Recommended responsibilities:

- PostgreSQL
- Redis or equivalent message/cache service
- Vector database, initially Qdrant or pgvector
- Always-on Signal REST wrapper and Freyja Signal connector
- Home Assistant
- Shared storage
- Backups
- Monitoring
- MCP servers
- Container hosting
- Internal DNS or service discovery

Atlas should provide reliable infrastructure and the always-on Signal path. It
should not host the Freyja Director in Rev 1 and should not become the primary
conversational reasoning authority.

Home Assistant should run as Home Assistant OS in a bridged VM on Atlas when
virtualization is available. This preserves managed MQTT, Matter, and Z-Wave
services while keeping device discovery on the home LAN. Mars accesses its API
over the private network and remains the authorization authority.

## 5.3 Iris — Always-Hot Secondary Local Inference Node

**Primary role:** kept-warm fast local fallback inference

Recommended responsibilities:

- Lower-latency Ollama models used after Hera failure or timeout
- Model compatibility and inference-health checks
- Stable fast-inference service for family-assistant continuity
- Warmup loop for the configured secondary local chat model
- Fast handling of ordinary household questions when selected by policy

Iris is the always-on local safety net for Rev 1. It is inference-focused, not
the development, Director, primary agent, or Signal host. The Director should
keep an Iris-capable model warm when Iris is configured as
`OLLAMA_FALLBACK_BASE_URL`, so the family-assistant path does not wait on a cold
model after Hera fails or times out.

## 5.4 Hera — Primary Local Agent and Benchmark Node

**Primary role:** primary local agent inference, development, verification, and benchmarking

Recommended responsibilities:

- Development environment and repository work
- Cross-platform tests and pre-deployment verification
- Model benchmarking
- Performance comparison against Iris-hosted models
- Hosting the primary local agent model (`qwen3:14b`) for routine chat,
  privacy-sensitive requests, and first-pass tool-selection requests
- Running explicit deep-reasoning experiments, such as larger local models, only
  when they do not starve avatar or interactive workloads
- Experimental inference workloads that must not affect Director or Signal availability

Hera provides high-quality local reasoning to Mars over Tailscale, but it is
deliberately separate from core always-on infrastructure. Rev 1 must not depend
on Hera for the Director, Signal connector, databases, or always-on control
path. If Hera is unavailable or exceeds the local agent turn timeout, routing
falls through to Iris and then to approved cloud fallback when policy,
credentials, and budget allow. If no fallback is available, Freyja must return a
clear provider failure rather than inventing an answer.

## 5.4.1 Future High-Capacity Inference PC — Layer 1 Local Brain

**Primary role:** dedicated heavy local inference once the new PC exists

The new PC belongs in the architecture as the future Layer 1 local inference
machine. It should run larger local models behind the same private Ollama,
vLLM, llama.cpp server, or OpenAI-compatible provider boundary used by Hera and
Iris.

Responsibilities:

- Heavy local reasoning and coding tasks that exceed Hera or Iris.
- Long-context local model serving where hardware allows.
- Benchmarking against Hera, Iris, OpenRouter, and Ollama Cloud.
- Private-network-only provider endpoint for Mars.

Non-responsibilities:

- It should not host the Director by default.
- It should not host Signal or iMessage connectors.
- It should not become a public remote-control endpoint.
- It should not own memory or home-automation policy.

When installed, the expected high-level stack becomes:

```text
Mars Director/control plane
    -> Hera primary Rev 1 local agent / deep-thought experiments
    -> Iris kept-warm fast local fallback
    -> New PC Layer 1 heavy local inference
    -> Ollama Cloud / OpenRouter cloud escalation
```

## 5.5 NUCBox — Utility Node

**Primary role:** Low-power always-on gateway

Recommended responsibilities:

- Optional fallback messaging bridge
- Telegram bridge for testing
- Reverse proxy restricted to the local network or VPN
- Health monitoring
- Lightweight worker services
- Optional low-resource Ollama model
- Queue consumer for background utilities

The NUCBox is a suitable place for services that must remain online continuously but do not require high compute performance.

## 5.6 Raspberry Pi “Cloyd” — Edge Automation Node

**Primary role:** Sensor and local automation edge node

Recommended responsibilities:

- GPIO and sensor interfaces
- Local device control
- Wake-word or room-presence services
- MQTT client or broker support
- Home Assistant satellite functions
- Local fallback automations

Cloyd should not host the central Director.

## 5.7 Avatar Computer — Human Interface Node

**Primary role:** Local embodied interface

Recommended responsibilities:

- Camera capture
- Microphone input
- Speaker output
- Avatar rendering
- Wake-word detection
- Speech-to-text client
- Text-to-speech client
- WebSocket connection to the Director

The avatar computer should function as a client and presentation device, not an independent authority.

## 5.8 Older Computers — Worker Pool

Older systems should be assigned one function at a time based on operating system, CPU, GPU, memory, and reliability.

Possible roles:

- Whisper transcription worker
- Vision worker
- Document conversion worker
- Web scraping worker
- Backup server
- Test environment
- Build runner
- Monitoring station
- Experimental model host

Worker nodes should communicate through authenticated internal APIs or a queue. They should not receive unrestricted remote shell commands from messaging platforms.

---

## 6. Core Software Components

## 6.1 Freyja Gateway

The Gateway receives messages from external interfaces and converts them into a common internal request format.

Responsibilities:

- Identify the user and source platform
- Validate sender allowlists
- Reject unknown or unauthorized senders
- Normalize attachments and text
- Apply rate limits
- Create a request ID
- Forward requests to the Director
- Return formatted responses

Current and initial connectors:

1. Signal
2. Telegram for development and fallback
3. Native iMessage for Apple/HomePod entry
4. Optional web interface

## 6.2 Freyja Director

The Director is the central orchestration service.

Responsibilities:

- Determine request intent
- Select local or cloud inference
- Select tools and worker services
- Track conversation context
- Enforce policy
- Manage retries and fallbacks
- Record costs and latency
- Format the final response

The Director should expose a stable internal API independent of any messaging platform.

Suggested initial implementation:

- Python 3.12+
- FastAPI
- Pydantic models
- Async HTTP clients
- Structured JSON logging
- Provider adapters for Ollama and OpenRouter

## 6.3 Model Router

The Model Router decides where inference should occur.

Rev 1 treats the model as the center of the assistant, not as an accessory
behind parser shortcuts. The default family-assistant route is:

```text
Hera qwen3:14b agent/tool loop
    -> Iris secondary local Ollama fallback when configured
    -> future new-PC Layer 1 heavy local inference when available
    -> approved OpenRouter/cloud finalization or fallback when policy allows
    -> explicit provider failure if no path is available
```

The router may still use deterministic preflights for table-stakes household
operations where failing into generic chat is worse than a narrow tool call.
Current examples are Home Assistant light/status questions and live weather
questions. Those paths still produce normal tool results and do not grant new
authority.

The optional Mars inference gateway exposes semantic tiers (`LOCAL`, `FREE`,
`FAST`, `REASONING`, `DEEP`, `FRONTIER`, `OLLAMA_CLOUD`) and maps them to
concrete providers. It is a provider-selection boundary, not a second Director.
`FRONTIER` requires explicit approval, sensitive prompts are kept local, and
cloud models must be allowlisted.

Initial routing criteria:

- Task complexity
- Required context length
- Tool-calling reliability
- Model availability
- Expected latency
- Privacy sensitivity
- Estimated token cost
- Current monthly budget usage

Example routing policy:

```text
Simple summarization, extraction, classification, or routine chat
    -> local Ollama

Private household information that can be handled locally
    -> local Ollama

Large context, difficult planning, advanced coding, or weak local result
    -> OpenRouter

Cloud provider unavailable or budget threshold reached
    -> local fallback with a limitation notice
```

## 6.4 Capability Registry

The Capability Registry contains the tools the Director is allowed to call.

Each capability should define:

- Name
- Description
- Input schema
- Output schema
- Authentication requirement
- Permission level
- Timeout
- Retry policy
- Host node
- Health status

Examples:

- `memory.search`
- `memory.write`
- `resolve_public_event`
- `calendar.today_schedule`
- `calendar.find_time`
- `calendar.create_event`
- `reminders.create`
- `homeassistant.call_service`
- `homeassistant.home_summary`
- `homeassistant.begin_pairing`
- `files.read`
- `files.write`
- `web.search`
- `speech.transcribe`
- `speech.synthesize`
- `vision.describe`
- `notifications.send`

## 6.5 Memory System

Memory should be divided into explicit categories.

### Short-Term Memory

- Current conversation
- Recent tool results
- Current task state
- Stored in Redis or process memory initially

### Long-Term Structured Memory

- User preferences
- Device inventory
- Project decisions
- Configuration records
- Stored in PostgreSQL

### Semantic Memory

- Architecture documents
- Notes
- Manuals
- Past conversations selected for indexing
- Stored in Qdrant or pgvector

Memory writes should be deliberate. Freyja should not automatically store every message as permanent memory.

## 6.5.1 Personal Intelligence Services

Personal Intelligence Services are domain services that reason over personal
state through the existing Director, Router, Memory, Tools, Certification, and
Benchmark architecture. They are not standalone applications.

The reference implementation is Family Calendar:

- `CalendarService` contains domain reasoning such as free/busy analysis,
  ranked time selection, conflict detection, travel buffers, and preference
  scoring.
- `CalendarProvider` defines the provider boundary for list/create/modify/delete
  operations.
- `GoogleCalendarProvider` and `AppleCalendarProvider` plug into the service
  boundary. Live account access is deliberately outside tests and certification.
- Family members have calendars, availability rules, preferred working hours,
  meeting windows, travel buffers, timezones, and scheduling preferences.
- Director tools expose calendar capabilities to the model so runtime evidence,
  certification verifiers, and benchmark reports can observe real behavior.
- Memory preferences influence ranking but must not override explicit
  instructions from the current request.

Future services should follow the same pattern: domain service first, provider
adapters second, Director tools third, certification suites fourth.

## 6.5.2 Identity Service

The Identity Service is the authoritative source for people known to Freyja.
Its resolver consumes an identity-provider boundary. Rev 1 providers are the
deterministic in-memory seed and a versioned SQLite repository stored outside
the source tree. A small native Apple Contacts reader and an offline vCard
reader feed validated `Person` records into that repository. They are import
adapters, not a MacAgent service or a synchronization daemon. Future MacAgent
or Google adapters must implement this boundary rather than bypassing canonical
`Person` records.
Subsystems should resolve raw identifiers into a `Person` as early as practical
and pass canonical person context through the existing Director and tool path.

Core model:

- `Person`: canonical person ID, display name, preferred name, aliases,
  identities, and non-sensitive metadata.
- `Identity`: typed external identifier such as phone, email, Signal,
  iMessage, calendar, voice, avatar, or account identity.
- `Alias`: natural-language names such as Dad, Father, Joe, or Joseph.
- `Relationship`: directed relationship edge such as spouse or child.

Current integrations:

- Messaging connectors resolve configured Signal and iMessage senders to
  `Person` metadata while preserving legacy allowlists and platform-scoped
  conversation IDs.
- The Director extracts trusted `X-Freyja-Person-*` connector headers and
  forwards sanitized person context in tool metadata.
- Calendar tools default to the resolved person when no explicit members are
  provided, and `CalendarService` accepts person IDs or aliases.
- Memory remains scoped by existing principals, but known people use the stable
  family-member memory subject so preferences attach to a person rather than a
  raw contact identifier.

Identity is intentionally not a replacement router or message bus. It is a
shared resolver and query service used by existing Director, connector, memory,
and Personal Intelligence Service boundaries.

## 6.6 Queue and Event Bus

A queue is recommended once multiple nodes are active.

Initial options:

- Redis Streams
- NATS
- RabbitMQ

Redis Streams is sufficient for the first implementation because Redis may already be used for caching and session state.

Event examples:

- `request.received`
- `request.completed`
- `tool.started`
- `tool.failed`
- `worker.online`
- `worker.offline`
- `budget.threshold_reached`

## 6.7 Communications Connectors

Messaging platforms are connector adapters into the Director, not alternate
Directors. Signal, iMessage, and future platforms should:

- normalize inbound platform events into connector message models;
- enforce allowlists and platform policy in the gateway;
- map approved senders to stable memory principals;
- forward natural-language requests to `/route`;
- return safe outbound errors without leaking provider, token, or traceback
  details;
- use mocked transports for tests and certification.

Family members can be configured with aliases in allowlists, for example
`joe=+15551234567` or `beth=beth@example.com`. Aliases resolve to shared
Person-backed `family-member:<hash>` memory subjects across platforms while
preserving platform-scoped conversation IDs.

---

## 7. Messaging Security

## 7.1 Signal

Signal is the preferred remote control interface.

Implementation should use a dedicated Freyja Signal account or number rather than a personal primary account where possible.

Required controls:

- Sender allowlist
- One-user default policy
- No group processing in the first release
- Attachment size limits
- Command rate limits
- Administrative commands restricted to a separate allowlist
- No direct shell execution from arbitrary natural-language requests

Potential bridge technologies include `signal-cli` or a maintained REST wrapper around it. The selected bridge should run on an always-on Linux system when possible.

### Current Signal connector deployment

Atlas is the always-on Signal connector host. Mars remains the Director and
control-plane host. The selected bridge is
`bbernhard/signal-cli-rest-api` running in `native` mode. Native mode supports
the HTTP receive endpoint, which the separate `SignalRestTransport` adapter
polls on a configurable interval. The adapter parses transport envelopes into
`InboundMessage` objects, calls `SignalGateway`, and delivers the returned
`OutboundResponse` through the wrapper's send endpoint.

The responsibility boundary is deliberate:

- `SignalRestTransport` owns the REST API, wire payload parsing, polling,
  outbound delivery, and recoverable transport errors.
- `SignalGateway` owns enablement, sender allowlisting, group rejection,
  message-size validation, attachment-only rejection, duplicate suppression,
  forwarding to the Mars Director, and safe error responses.

Transport code must not bypass or duplicate gateway policy. Unauthorized
senders and group messages remain rejected by the gateway.

Required deployment configuration includes:

- `SIGNAL_ENABLED`
- `SIGNAL_ACCOUNT_NUMBER`
- `SIGNAL_ALLOWED_SENDERS`
- `SIGNAL_REST_API_URL`
- `FREYJA_DIRECTOR_URL`
- `SIGNAL_POLL_INTERVAL_SECONDS`
- `SIGNAL_TRANSPORT_TIMEOUT_SECONDS`
- `SIGNAL_REQUEST_TIMEOUT_SECONDS`

Retry bounds and message limits are configured with
`SIGNAL_RECONNECT_MAX_SECONDS` and `SIGNAL_MAX_MESSAGE_CHARS`.

The Atlas Compose deployment places the REST wrapper only on a private Docker
network and publishes no REST API port. The connector has outbound access to
the private Mars Director endpoint. Signal account keys and registration state
live in a named volume rather than an image or Git. First-time account
registration or device linking is a manual operator action performed according
to the wrapper's upstream documentation; no account is registered by Freyja.

Create `deploy/compose/signal/.env` from its example, populate it locally, and
set its filesystem mode to `0600`. Detailed deployment steps are maintained in
`deploy/compose/signal/README.md`. The Compose model can be validated without
starting or pulling containers:

```bash
docker compose -f deploy/compose/signal/compose.yaml config
```

## 7.2 Telegram

Telegram may be retained for development because it is easy to integrate. It must include:

- Allowed user ID checks
- An explicit owner user ID distinct from the broader onboarding/diagnostic allowlist
- Disabled group access
- Restricted bot commands
- Token stored in a secret manager or protected environment file
- No public webhook unless protected by authentication and network controls

The main issue is not that every Telegram bot is automatically public. The issue is that a poorly configured bot can accept messages from unauthorized users. Freyja must enforce explicit authorization at the gateway.
An allowlisted Telegram user may use `/whoami` during onboarding, but only the
configured owner user ID may receive that person's trusted identity headers or
route ordinary messages to the personal agent.

## 7.3 iMessage

iMessage is the Apple-native secondary connector and the current HomePod voice
entry path. Apple still does not provide a general-purpose official bot API, so
the connector remains a macOS client adapter with explicit allowlists, bounded
message handling, duplicate suppression, and safe outbound behavior.

Implemented and supported path:

- Native Python iMessage connector on a signed-in macOS account.
- Optional HomePod/Siri Shortcut that sends `Freyja: <request>` by iMessage.
- Forgiving handling for question-like self-authored Shortcut messages.
- Tool-capable `/route` calls so Home Assistant and other Director tools can be
  used from iMessage.
- Separate short timeout for `imsg` commands so one stuck Messages chat cannot
  wedge the connector.

Any iMessage bridge should be treated as a client adapter, not as the Director
itself. Attachments, groups, and broad outbound messaging remain deferred.

---

## 8. Network Architecture

All Freyja services should communicate over a private network.

Preferred access methods:

1. Local LAN
2. Tailscale or another WireGuard-based private overlay network
3. Reverse proxy only when required

Recommended rules:

- No Ollama API exposed directly to the public internet
- No PostgreSQL, Redis, Qdrant, or Home Assistant ports exposed publicly
- Use host firewalls
- Use service-level API tokens
- Use TLS where practical
- Use separate credentials per service
- Restrict administrative APIs to the local network or VPN

Suggested internal service names:

```text
director.freyja.local
atlas.freyja.local
gateway.freyja.local
memory.freyja.local
homeassistant.freyja.local
worker-vision.freyja.local
worker-speech.freyja.local
```

---

## 9. Authentication and Authorization

The initial system may support one primary user, but it should still include an authorization model.

People, agents, connectors, and devices are separate principals. A trusted
device is related to a canonical person through a stable device ID and a
cryptographic credential fingerprint. Hostnames and IP addresses are not proof
of identity. Telegram authenticates a user ID rather than a physical device, so
its user-to-person mapping remains a connector rule instead of a device grant.

Personal-data grants carry person, acting agent, resource, account, and scope
facts only. Calendar and email permissions are derived again from server policy
at every authorization decision; callers cannot supply their own allowed-action
set. Cross-person private access is denied, availability-only grants cannot read
event details, and consequential email/calendar actions require approval.

Suggested roles:

- `owner`
- `trusted_user`
- `guest`
- `service`

Suggested permission groups:

- Chat only
- Read memory
- Write memory
- Read files
- Write files
- Home automation
- Administrative configuration
- Shell or code execution

High-risk actions should require explicit confirmation or a second authorization step.

Examples:

- Deleting files
- Unlocking doors
- Disabling alarms
- Sending email
- Spending money
- Running privileged shell commands

---

## 10. Secrets Management

Secrets should never be committed to GitHub.

Initial secrets include:

- OpenRouter API key
- Signal bridge credentials
- Telegram bot token
- Database passwords
- Home Assistant token
- Internal service tokens

Initial implementation may use `.env` files with strict filesystem permissions. A later version should migrate to Docker secrets, SOPS, 1Password CLI, Vault, or another dedicated secret system.

Repository requirements:

- Include `.env.example`
- Add `.env` and secret files to `.gitignore`
- Rotate any key accidentally committed
- Never place live keys in documentation or issue comments

---

## 11. Logging, Monitoring, and Audit

Each request should receive a unique request ID.

Minimum log fields:

- Timestamp
- Request ID
- User ID
- Source platform
- Selected model
- Provider
- Tool calls
- Latency
- Token use
- Estimated cost
- Outcome
- Error category

Sensitive content should not be logged by default. Logs should capture metadata and failure information while minimizing stored message content.

Initial monitoring:

- Service health endpoints
- Disk usage
- Memory usage
- CPU usage
- Ollama availability
- OpenRouter availability
- Queue depth
- Monthly cloud spend
- Worker heartbeat

---

## 12. Cost Controls

The Director should maintain a monthly OpenRouter budget.

Initial controls:

- Configurable monthly soft limit
- Configurable per-request maximum cost
- Model allowlist
- Daily cost summary
- Warning at 50%, 75%, and 90% of monthly budget
- Local fallback after the hard limit
- Manual override available only to the owner

The router should not automatically choose the most expensive available model. It should choose the least expensive model that is likely to complete the task reliably.

---

## 13. Reliability and Fallback Behavior

Expected fallback chain:

```text
Hera qwen3:14b local agent model for local-first tasks
    -> Iris secondary local Ollama model when configured
    -> future new-PC Layer 1 heavy local inference when available
    -> configured OpenRouter fallback when policy and credentials allow
    -> explicit provider failure if no fallback is available
```

OpenRouter fallback is available only when the Director has a valid API key,
approved model configuration, and routing policy budget headroom. If Hera or any
other provider is unavailable and no fallback is configured, the Director should
return a clear failure instead of fabricating an answer.

Local agent tool-loop turns are bounded by `OLLAMA_TOOL_CALL_TIMEOUT_SECONDS`.
This prevents a slow or wedged local model from blocking iMessage/HomePod or
Signal responses for minutes before Iris or cloud fallback can respond.

The system should not silently discard failed tool calls. Failures should be recorded and surfaced when they affect the result.

Each service should provide:

- Health endpoint
- Timeout
- Retry limit
- Circuit breaker or temporary disable behavior
- Clear error response

---

## 14. Repository Structure

Current repository structure:

```text
freyja-os/
├── README.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── SECURITY.md
├── CONTRIBUTING.md
├── .gitignore
├── .env.example
├── certification/
│   ├── cli.py
│   └── suites/
├── config/
├── docs/
│   ├── HOME_ASSISTANT.md
│   ├── HOMEPOD_SHORTCUTS.md
│   ├── IDENTITY_STORAGE.md
│   └── ...
├── src/
│   └── freyja/
│       ├── agents/
│       ├── calendar/
│       ├── homeassistant/
│       ├── identity/
│       ├── memory/
│       ├── reminders/
│       ├── tools/
│       ├── main.py
│       ├── router.py
│       ├── inference_gateway.py
│       ├── ollama_client.py
│       └── openrouter_client.py
├── connectors/
│   ├── signal/
│   ├── telegram/
│   └── imessage/
├── deploy/
│   ├── docker/
│   ├── compose/
│   └── homeassistant/
├── scripts/
├── tests/
└── data/        # runtime only; ignored
```

---

## 15. Current API Contract

The Director exposes the current family-assistant route at `/route`.
A normalized route request resembles:

```json
{
  "prompt": "How many lights are on at home?",
  "provider": "auto",
  "source": "imessage",
  "conversation_id": "string",
  "tools_required": true,
  "privacy": "household"
}
```

A route response includes the final answer, routing evidence, and tool evidence:

```json
{
  "response": "Home Assistant reports 1 visible light currently on...",
  "provider": "ollama",
  "model": "qwen3:14b",
  "routing": {
    "reason": "auto local-first route",
    "estimated_cost_usd": 0.0
  },
  "tool_results": []
}
```

Other supported internal surfaces include `/health`, `/control-plane/status`,
`/tools`, `/memory`, and `/inference-gateway/*`. Non-public endpoints require
`FREYJA_CONNECTOR_TOKEN` when configured.

---

## 16. Initial Deployment Target

The first working release should prove these paths:

```text
Signal
  -> Gateway
  -> Director
  -> Hera, Iris, new-PC Layer 1 when available, or approved cloud fallback
  -> Director
  -> Signal response

HomePod / Siri Shortcut
  -> iMessage
  -> iMessage connector
  -> Director
  -> Home Assistant or model/tool route
  -> iMessage response
```

Minimum acceptance criteria:

- Only the authorized Signal account can issue requests
- Director can reach Hera and any configured Iris/new-PC local inference endpoint
- Director can reach an approved cloud fallback when enabled
- Routing can be selected manually and automatically
- Every request is logged with model, latency, and estimated cost
- Cloud use can be disabled globally
- System survives a service restart

---

## 17. Deferred Features

The following features are intentionally deferred until the family-assistant
baseline is stable:

- Autonomous multi-agent collaboration
- Avatar personality system
- Continuous microphone listening
- Broad home automation beyond reviewed low-risk entities
- iMessage attachments, groups, and broad outbound messaging
- Multi-user support
- Self-modifying code
- Automatic privilege escalation
- Unrestricted shell access
- Financial transactions
- Public internet access to internal services

---

## 18. Definition of Freyja-OS v0.1

Freyja-OS v0.1 is complete when Joe can send an authorized message from a
phone or HomePod path, receive a useful family-assistant answer generated by
Hera, Iris, the future new-PC local layer, or an approved cloud fallback, and
inspect evidence showing routing, tool use, latency, and cost.

That release establishes the core platform. Memory, tools, voice, vision,
expanded home automation, and distributed workers deepen the assistant after
the family-facing experience is reliable.
