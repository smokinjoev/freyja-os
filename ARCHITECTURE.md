# Freyja-OS Architecture

**Version:** 0.1 Rev 1
**Status:** Rev 1 host-role baseline
**Primary owner:** Joe  
**Project:** Freyja-OS

## 1. Purpose

Freyja-OS is a personal AI orchestration platform designed to combine local models, cloud models, secure messaging, automation tools, memory, and distributed worker computers behind one consistent interface.

The system should:

- Prefer local inference when practical.
- Escalate difficult work to cloud models through OpenRouter.
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

The system should use local Ollama models for routine work and escalate to OpenRouter only when the task requires stronger reasoning, larger context, better tool use, or a specialized cloud model.

### 2.3 Secure Entry Points

Signal is the preferred remote interface. iMessage may be added as a secondary Apple-native interface. Telegram may remain available for testing, but it should not be treated as the primary secure control path.

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

The architecture assumes these systems may be reassigned as their capabilities are tested.

### 3.3 Rev 1 Authoritative Host Roles

- Mars: Freyja Director and control plane.
- Atlas: always-on infrastructure services and Signal connector.
- Hera: primary complex local_reasoning provider over Tailscale; not core always-on control-plane infrastructure.
- Iris: fast local inference tier; inference-focused and not a development host.

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
             Signal Bridge                      iMessage Bridge
             Primary Remote                     Secondary / Later
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

## 5.3 Iris — Local Inference Node

**Primary role:** Fast local LLM inference

Recommended responsibilities:

- Lower-latency Ollama models used by the Mars Director for quick local work
- Model compatibility and inference-health checks
- Stable fast-inference service for the Mars control plane

Iris should remain the fast local inference tier for Rev 1. It is
inference-focused, not the development, Director, complex reasoning, or
always-on Signal host.

## 5.4 Hera — Development and Benchmark Node

**Primary role:** Development, verification, inference benchmarking, and complex local reasoning

Recommended responsibilities:

- Development environment and repository work
- Cross-platform tests and pre-deployment verification
- Model benchmarking
- Performance comparison against Iris-hosted models
- Hosting the primary local `local_reasoning` model for complex coding,
  debugging, planning, architecture, difficult reasoning, and multi-step
  tool-selection requests
- Experimental inference workloads that must not affect Director or Signal availability

Hera provides high-quality local reasoning to Mars over Tailscale, but it is
deliberately separate from core always-on infrastructure. Rev 1 must not depend
on Hera for the Director, Signal connector, databases, or always-on control
path. If Hera is unavailable, routing must fail cleanly and use configured
fallback providers rather than inventing an answer.

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

Initial connectors:

1. Signal
2. Telegram for development and fallback
3. iMessage in a later phase
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
- `calendar.today_schedule`
- `calendar.find_time`
- `calendar.create_event`
- `homeassistant.call_service`
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
`family-member:<hash>` memory subjects across platforms while preserving
platform-scoped conversation IDs.

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
- Disabled group access
- Restricted bot commands
- Token stored in a secret manager or protected environment file
- No public webhook unless protected by authentication and network controls

The main issue is not that every Telegram bot is automatically public. The issue is that a poorly configured bot can accept messages from unauthorized users. Freyja must enforce explicit authorization at the gateway.

## 7.3 iMessage

iMessage integration is a later-phase feature because Apple does not provide a general-purpose official bot API.

Possible implementation paths:

- BlueBubbles server on macOS
- AppleScript or Shortcuts-based bridge
- macOS Messages database watcher with a controlled sender allowlist

Any iMessage bridge should be treated as a client adapter, not as the Director itself.

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
Hera local_reasoning model for complex local tasks
    -> configured OpenRouter fallback when policy and credentials allow
    -> explicit provider failure if no fallback is available
Iris fast local model for routine local tasks
    -> configured OpenRouter fallback when policy and credentials allow
    -> explicit provider failure if no fallback is available
```

OpenRouter fallback is available only when the Director has a valid API key,
approved model configuration, and routing policy budget headroom. If Hera or any
other provider is unavailable and no fallback is configured, the Director should
return a clear failure instead of fabricating an answer.

The system should not silently discard failed tool calls. Failures should be recorded and surfaced when they affect the result.

Each service should provide:

- Health endpoint
- Timeout
- Retry limit
- Circuit breaker or temporary disable behavior
- Clear error response

---

## 14. Repository Structure

Recommended initial repository structure:

```text
Freyja/
├── README.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── LICENSE
├── .gitignore
├── .env.example
├── docs/
│   ├── decisions/
│   ├── diagrams/
│   ├── operations/
│   └── security/
├── src/
│   └── freyja/
│       ├── api/
│       ├── director/
│       ├── gateway/
│       ├── models/
│       ├── providers/
│       ├── tools/
│       ├── memory/
│       ├── security/
│       └── observability/
├── connectors/
│   ├── signal/
│   ├── telegram/
│   └── imessage/
├── workers/
│   ├── speech/
│   ├── vision/
│   └── documents/
├── deploy/
│   ├── docker/
│   ├── compose/
│   └── systemd/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
└── scripts/
```

---

## 15. Initial API Contract

A normalized request should resemble:

```json
{
  "request_id": "uuid",
  "user_id": "joe",
  "source": "signal",
  "conversation_id": "string",
  "message": "user text",
  "attachments": [],
  "permissions": ["chat", "memory.read"],
  "timestamp": "ISO-8601"
}
```

A normalized response should resemble:

```json
{
  "request_id": "uuid",
  "status": "completed",
  "message": "assistant response",
  "provider": "ollama",
  "model": "model-name",
  "tool_calls": [],
  "estimated_cost_usd": 0.0,
  "latency_ms": 1200
}
```

---

## 16. Initial Deployment Target

The first working release should prove this path:

```text
Signal
  -> Gateway
  -> Director
  -> Local Ollama or OpenRouter
  -> Director
  -> Signal response
```

Minimum acceptance criteria:

- Only the authorized Signal account can issue requests
- Director can reach at least one local Ollama model
- Director can reach at least one OpenRouter model
- Routing can be selected manually and automatically
- Every request is logged with model, latency, and estimated cost
- Cloud use can be disabled globally
- System survives a service restart

---

## 17. Deferred Features

The following features are intentionally deferred until the core pipeline is stable:

- Autonomous multi-agent collaboration
- Avatar personality system
- Continuous microphone listening
- Advanced home automation
- Full iMessage support
- Multi-user support
- Self-modifying code
- Automatic privilege escalation
- Unrestricted shell access
- Financial transactions
- Public internet access to internal services

---

## 18. Definition of Freyja-OS v0.1

Freyja-OS v0.1 is complete when Joe can send an authorized Signal message from his phone, receive a response generated by either a local Ollama model or an OpenRouter model, and inspect a log showing how the request was routed, how long it took, and what it cost.

That release establishes the core platform. Memory, tools, voice, vision, iMessage, home automation, and distributed workers are added after this foundation is reliable.
