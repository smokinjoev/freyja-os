# Freyja-OS Architecture

**Version:** 0.2 Rev 2  
**Status:** Rev 2 authoritative architecture baseline  
**Primary owner:** Joe  
**Project:** Freyja-OS

## 1. Purpose

Freyja-OS is a local-first household intelligence system. It combines persistent identity and memory, secure communications, Apple-native services, home automation, replaceable local and cloud inference engines, and isolated worker capabilities behind one trusted Director.

Freyja is not a single model and is not tied to a single computer. Models, hosts, interfaces, and workers are replaceable resources. Identity, memory policy, authorization, routing policy, and audit remain stable as hardware and models change.

The core design rule is:

> Keep the control plane stable; swap inference engines and interfaces as needed.

---

## 2. Rev 2 Decisions

Rev 2 supersedes the Rev 1 host-role baseline.

### 2.1 Atlas is the control plane

Atlas is the authoritative always-on Freyja Director host.

Atlas owns:

- Director API
- request/session orchestration
- identity and principal resolution
- memory policy
- capability authorization
- inference routing policy
- provider health and failover state
- audit and request metadata
- Signal and other Linux-native connector services where practical
- shared infrastructure services

Inference hosts may recommend routes or tool choices, but they do not authorize privileged actions.

### 2.2 Iris is the Apple gateway and hot reflex/router node

Iris remains powered on and keeps a small approximately 7B local model resident.

Iris owns two distinct responsibilities:

1. **MacAgent / Apple-native capability gateway**
   - iMessage
   - Apple Calendar and Contacts adapters
   - Shortcuts and macOS automation
   - Apple-family integrations that require macOS
   - future HomePod-facing Apple hooks

2. **Always-hot low-latency inference**
   - request classification
   - routing recommendation
   - simple conversation
   - lightweight extraction/summarization
   - tool-selection hints
   - fast fallback responses where policy permits

The Iris 7B model is advisory. It may classify intent, complexity, sensitivity, or preferred execution tier, but Atlas Director remains authoritative for routing, permissions, and tool execution.

### 2.3 The new inference machine is the heavy local reasoning tier

The new inference machine is a replaceable compute resource, not a control-plane host.

Its responsibilities include:

- large local reasoning models
- advanced coding/debugging
- deep planning
- long-context work
- vision or multimodal inference when supported
- high-quality tool-planning inference when local execution is preferred
- benchmark and model-evaluation workloads

Director, identity, trusted memory policy, and capability authorization must not depend on this machine being online.

### 2.4 Hera becomes a presence/development node, not the permanent heavy reasoning authority

Hera may continue to provide development, benchmarking, experimental inference, and avatar/presence services. Rev 2 does not require Hera to host Freyja's primary complex reasoning model.

When deployed as the kitchen avatar, Hera is a Freyja Presence Node: microphones, speaker, display/avatar, wake word, local conversation cache, speech services, and optional small local model. It remains a client of Atlas Director.

### 2.5 Mars is no longer the primary Director host

Mars remains available as an immutable utility, fallback, monitoring, testing, or infrastructure node, but Rev 2 does not assign it the authoritative Director role.

---

## 3. Design Principles

### 3.1 One trusted Director

All meaningful requests converge on the Atlas Director before privileged action. Messaging connectors and inference nodes are not alternate Directors.

### 3.2 Models advise; policy authorizes

No LLM is a security boundary.

A model may propose:

- an inference tier
- an intent
- a tool call
- structured arguments
- a response

The Director and Capability Broker decide whether the request is authorized and executable.

### 3.3 Local first, not local only

Freyja prefers local processing when practical, especially for private household data. Cloud inference remains available when policy permits and stronger reasoning, specialized capability, or reliability justifies it.

Cloud providers receive the minimum context needed for the task.

### 3.4 Fast path before heavy reasoning

Simple requests should not wake a large model unnecessarily.

The system should prefer deterministic handlers, direct tools, memory lookup, or the resident Iris 7B model before escalating to heavy local or cloud inference.

### 3.5 Trust boundaries matter more than prompt discipline

External content such as web pages, email bodies, documents, and unknown messages is untrusted data. Untrusted content must not gain authority merely because an LLM interpreted it.

### 3.6 Replaceable components

Freyja must avoid hard dependencies on one model provider, model family, vector database, connector, or host.

---

## 4. High-Level Architecture

```text
                    Household / Users
                           |
          +----------------+----------------+----------------+
          |                |                |                |
       Signal           Gmail           iMessage         Voice/Avatar
          |                |                |                |
          |                |           Iris MacAgent       Hera Presence
          |                |                |                |
          +----------------+----------------+----------------+
                           |
                    +------v------+
                    |    ATLAS    |
                    |  DIRECTOR   |
                    +------+------+ 
                           |
         +-----------------+------------------+
         |                 |                  |
   Identity/Memory   Capability Broker   Inference Router
         |                 |                  |
         |        +--------+--------+         |
         |        |        |        |         |
         |     Calendar   Home    Files       |
         |               Assistant            |
         |                                     |
         +------------------+------------------+
                            |
              +-------------+-------------+
              |             |             |
            IRIS       NEW INFERENCE     CLOUD
          hot 7B          MACHINE       PROVIDERS
        router/reflex    heavy local    escalation
              |          reasoning
              |
          MacAgent
        Apple services
```

---

## 5. Node Roles

## 5.1 Atlas — Director and trusted control plane

**Primary role:** authority, orchestration, policy, and shared services.

Responsibilities:

- Freyja Director
- Gateway-facing route API
- Identity Service
- memory coordination and policy
- Capability Broker
- inference/provider registry
- routing and failover policy
- tool registry
- conversation/session state
- cost accounting
- audit metadata
- health aggregation
- Signal connector and supporting Linux services where practical
- PostgreSQL/Redis/vector services as deployed
- Home Assistant integration boundary

Atlas should remain usable even when every optional inference node is unavailable.

## 5.2 Iris — MacAgent and always-hot router/reflex node

**Primary role:** Apple-native capabilities plus low-latency local intelligence.

Responsibilities:

- MacAgent
- iMessage bridge
- Apple Calendar/Contacts provider adapters
- Shortcuts/macOS automation
- other Apple-native services
- resident approximately 7B Ollama model
- structured route classification
- low-cost local chat/extraction
- provider health endpoint

The resident model should remain loaded across requests. Director should treat Iris as the preferred first inference hop for tasks that actually require model classification but do not justify heavy reasoning.

Iris must not grant itself permissions or directly bypass the Atlas Capability Broker.

## 5.3 New inference machine — heavy local compute

**Primary role:** high-capability local inference.

Responsibilities:

- large reasoning model(s)
- coding models
- long-context inference
- optional vision/multimodal workloads
- model benchmarking
- speculative or experimental inference backends

The machine exposes one or more authenticated provider endpoints to Atlas over the private network/Tailscale.

No user-facing connector should depend directly on it.

## 5.4 Hera — presence, avatar, development, and experimental compute

**Primary role:** human-facing embodied interface and development/benchmark node.

Possible responsibilities:

- wake word
- microphone/camera input
- speaker/TTS
- avatar rendering
- local speech-to-text
- local short-lived conversation cache
- small local model when useful
- development and pre-deployment verification
- experimental inference

Hera is a body/interface for Freyja, not an independent Freyja authority.

## 5.5 Mars — utility/fallback node

**Primary role:** immutable utility host.

Possible responsibilities:

- monitoring
- health checks
- low-risk worker services
- fallback infrastructure
- test/staging services
- backup queue or connector support

Mars is not the Rev 2 authoritative Director host.

---

## 6. Director Responsibilities

The Director is responsible for turning an authenticated request into an authorized execution plan.

Responsibilities:

- accept normalized requests
- resolve the acting principal
- identify relevant household/person scope
- select deterministic handling, tool execution, memory lookup, or inference
- request route classification from Iris when useful
- select an inference tier/provider
- enforce privacy and cloud-use policy
- authorize capabilities
- manage retries and failover
- record latency/provider/tool metadata
- return a final response to the originating connector

The Director should not require a large model merely to decide which model to use.

---

## 7. Tiered Inference Routing

Rev 2 defines explicit inference tiers.

### Tier 0 — deterministic/direct

Use no generative model when a direct capability or deterministic parser can reliably satisfy the request.

Examples:

- health/status checks
- exact device commands
- known Home Assistant entity operations
- simple database lookups
- connector administration

### Tier 1 — Iris hot 7B reflex/router

Use the resident Iris model for:

- intent classification
- complexity scoring
- task-type classification
- lightweight chat
- extraction and short summarization
- simple tool-selection recommendations

Expected output for routing should be structured and bounded, for example:

```json
{
  "task_type": "coding",
  "complexity": 4,
  "sensitivity": "private",
  "needs_tools": false,
  "preferred_tier": 3,
  "confidence": 0.93
}
```

This response is a recommendation, not authorization.

### Tier 2 — stronger routine local inference

Use an appropriate local model for medium-complexity tasks that exceed the hot 7B model but do not require the largest reasoning model.

This tier may reside on Iris or another registered inference host depending on available memory, model quality, and latency.

### Tier 3 — heavy local reasoning

Use the new inference machine for:

- difficult reasoning
- coding/debugging
- long-context planning
- complex multi-step analysis
- strong local tool planning
- local multimodal work

### Tier 4 — cloud/frontier escalation

Use configured cloud providers only when policy permits and the task materially benefits from them.

Before cloud dispatch, Director minimizes and sanitizes context. Raw household memory should not be sent by default.

---

## 8. Provider and Health Registry

Director should maintain a live registry of inference resources rather than hard-coding one Ollama host.

Each provider registration should include:

- provider/host ID
- endpoint
- model name
- model family
- capability tags
- context window
- expected latency class
- tool-use support
- vision support
- privacy locality
- approximate cost
- health state
- model residency state when detectable
- current load when available
- fallback priority

Example capability tags:

- `router`
- `fast_chat`
- `coding`
- `reasoning`
- `vision`
- `long_context`
- `embeddings`
- `cloud_frontier`

Routing policy selects by required capability plus health, privacy, latency, and cost.

---

## 9. Latency and Model Residency

Cold-start delay is a system concern, not an operator inconvenience.

Rev 2 requirements:

- Iris keeps the primary 7B routing/reflex model resident.
- Director health checks should distinguish host availability from model readiness.
- Director should avoid escalating simple requests to a cold large model.
- Inference hosts may expose warm-up/readiness endpoints.
- Heavy models may be prewarmed when memory and power policy permit.
- Provider telemetry should record time-to-first-token separately from total latency when available.

A desired request flow is:

```text
request
  -> Atlas Director
  -> deterministic fast path if possible
  -> otherwise Iris hot 7B classification
  -> Atlas applies policy
  -> direct tool / Iris answer / heavy local / cloud escalation
```

---

## 10. Capability Broker

Rev 2 separates model reasoning from execution authority.

Every privileged tool should define:

- capability name
- authenticated principal requirements
- allowed subject/resource scope
- read/write/consequential classification
- required approval policy
- host/service endpoint
- input/output schema
- timeout/retry policy
- health state

Examples:

- `memory.read`
- `memory.write`
- `calendar.read`
- `calendar.write`
- `messages.send`
- `home.read`
- `home.control`
- `files.read`
- `files.write`
- `web.research`
- `code.execute`

An LLM requesting a tool does not imply permission to execute it.

---

## 11. Trust Domains and Untrusted Workers

External content is treated as untrusted data.

The target architecture separates:

1. **Trusted Core**
   - Director
   - Identity
   - memory policy
   - Capability Broker
   - authorization

2. **Trusted local capability services**
   - MacAgent
   - Home Assistant adapter
   - calendar providers
   - approved file services

3. **Untrusted-content workers**
   - web research
   - arbitrary email/document ingestion
   - scraping
   - external-content summarization

4. **Inference providers**
   - local models
   - cloud models

Untrusted-content workers should receive only capabilities needed for their task and should return structured results. They must not automatically inherit memory-write, messaging-send, home-control, or administrative capabilities.

---

## 12. Memory and Provenance

Long-term memory should preserve source and trust information.

Target memory metadata includes:

- memory ID
- subject/person ID
- scope
- content or structured fact
- source type
- source identifier
- observed timestamp
- created/updated timestamp
- confidence
- sensitivity
- trust level
- derivation/provenance links
- optional expiration

External content must not become authoritative household memory merely because a model summarized it.

Passive authorized sources, such as the family iMessage group, may create
memory candidates when source policy permits. These candidates should store
structured facts and provenance, not raw conversation transcripts. Ordinary
conversation, jokes, speculation, and transient chatter should remain
unpromoted unless later confirmed or explicitly useful.

Suggested progression:

```text
untrusted observation
      -> corroboration / trusted confirmation
      -> verified fact
      -> long-term authoritative memory
```

Memory scopes should support at minimum:

- private person scope
- shared household scope
- guest/session scope
- system/configuration scope

Structured memory candidates should include, where applicable:

- people involved
- event or fact type
- date/time
- location
- source connector and thread
- confidence
- tentative/confirmed/cancelled status
- expiration or relevance period
- relationship to an existing memory

New information should update or invalidate prior candidates when appropriate,
for example a delayed flight arrival or a cancelled family plan. Memory
extraction and calendar modification remain separate capabilities: confirmed
events may become calendar candidates, but calendar writes require their own
confidence and permission rules.

Apple Calendar writes use the same Director tool path as every other
consequential action:

```text
Family/Gmail/iMessage request
      -> Atlas Director
      -> Capability Broker approval check
      -> calendar_create_event / calendar_modify_event / calendar_delete_event
      -> AppleCalendarProvider on Iris
      -> EventKit calendar store under Freyja's Apple identity
```

The live Apple provider is opt-in with `CALENDAR_DEFAULT_PROVIDER=apple` and
`APPLE_CALENDAR_ENABLED=true`. Calendar aliases map canonical Freyja people
such as `joe`, `beth`, and `family` onto Apple calendar names such as `Family`.
Read operations may run for authorized household principals. Writes require a
canonical household principal, Director authorization, and explicit approval;
conversation-derived memory candidates do not bypass that approval boundary.

---

## 13. Communications and MacAgent

Messaging platforms remain connector adapters into Director.

### Signal

Signal is the preferred protected remote interface. The connector authenticates senders, normalizes messages, resolves the sender to an agent/person context, marks the route request private, and forwards it to Atlas Director. Atlas remains authoritative for routing and tool authorization.

Current Signal agent mapping:

- `family` -> Freyja / `person:family`
- `joe` -> Cloyd Gibbler / `person:joe`
- `beth` -> Benedict / `person:beth`

Signal logs and Director headers must not contain raw phone numbers.

### iMessage

iMessage is now an active Apple-native integration path rather than a merely deferred concept.

Direct addressed iMessage conversations remain a conventional connector path:

```text
iMessage
  -> MacAgent on Iris
  -> identity resolution
  -> Atlas Director
  -> authorized execution/inference
  -> MacAgent
  -> iMessage response
```

MacAgent is not an alternate Director.

The authorized family iMessage group is also a passive context source. In its
default observe state, Freyja reads permitted group messages, extracts bounded
household logistics locally on Iris, and stores structured memory candidates
without replying. Freyja enters normal conversational behavior only when
explicitly addressed by an invocation such as `Freyja, ...` or `@Freyja ...`.

Passive family extraction should prefer local processing and should identify
useful logistics such as events, appointments, travel timing, locations,
celebrations, gift ideas, and changes or cancellations. Raw family conversation
should remain local unless a specific task requires cloud reasoning and policy
permits escalation.

Operating states:

- `Observe` - read authorized family conversation, extract context, maintain
  candidates/memories, and remain silent.
- `Addressed` - when explicitly invoked, route through normal Director
  behavior and reply to the group.
- `Ambiguous / High Impact` - preserve tentative context or request
  clarification; do not act automatically.

### Gmail

Gmail is a first-class communication connector for corporate/work environments
where preferred messaging services may be blocked. It uses Freyja's existing
Gmail identity and preserves Gmail threads as Freyja conversation threads.

The preferred architecture is:

```text
Work Email
  -> Freyja Gmail
  -> Gmail IMAP/SMTP transport
  -> Gmail gateway
  -> sender allowlist
  -> HTML/external-content sanitization
  -> Atlas Director
  -> authorized execution/inference/memory
  -> Gmail reply in the same thread
```

The Gmail transport owns mailbox polling, unread-message acknowledgement, and
SMTP delivery with `In-Reply-To` / `References` headers. The Gmail gateway owns
authorization, sanitization, Director routing, conversation-thread mapping, and
safe error responses.

Gmail is not an approval channel for consequential actions. Normal questions,
research, memory access, and status requests may route normally after sender
authorization, but consequential actions require approval through a trusted
non-Gmail channel. Attachments are untrusted input and should be passed only as
metadata unless a separate safe attachment reader is explicitly invoked.

### Telegram

Telegram is not the primary protected connector. It may remain available for testing only, subject to explicit allowlists and identity mapping, and should not be used for sensitive/private household operations.

---

## 14. Household Identity Model

Freyja is designed for a household, not only one user.

Identity should support:

- canonical Person records
- platform identities
- aliases
- family relationships
- devices
- private memory scope
- household-shared memory scope
- per-capability authorization

A family member's authenticated identity must be resolved before private memory or consequential capabilities are accessed.

---

## 15. Network Architecture

Core services communicate over LAN or Tailscale/private overlay networking.

Rules:

- no Ollama endpoint exposed to the public internet
- no database or Home Assistant service exposed publicly unless explicitly fronted by an approved gateway
- per-service credentials where practical
- host firewalling
- administrative interfaces restricted to private networks
- inference hosts treated as registered internal services, not trusted merely by hostname

---

## 16. Reliability and Fallback

The system should fail by capability, not fail as a whole.

Illustrative routing fallback:

```text
Tier 0 deterministic path
    -> execute or explicit capability failure

Iris hot 7B
    -> alternate local model if configured
    -> heavy local inference if appropriate
    -> cloud only if policy permits

Heavy local inference machine
    -> alternate local provider
    -> cloud if policy permits
    -> explicit provider failure
```

If the new inference machine is offline, Freyja must still retain messaging, memory, Apple integration, Home Assistant, and basic conversational capability.

---

## 17. Observability

Each request should record at minimum:

- request ID
- authenticated principal/person
- source connector
- route classification
- selected tier
- selected provider/model
- provider health state
- model readiness/residency state when available
- capability requests and authorization outcomes
- time to first token when available
- total latency
- token/cost metadata
- fallback events
- final outcome

Sensitive content should not be logged by default.

---

## 18. Rev 2 Implementation Sequence

Rev 2 should be implemented incrementally without breaking existing connectors.

### Phase A — host-role/config cleanup

- make Atlas the documented Director target everywhere
- remove stale Mars-as-Director assumptions from deployment docs/config examples
- document Iris MacAgent and inference endpoints
- register the new inference machine as a provider host rather than a control-plane host

### Phase B — provider registry and health

- add provider capability metadata
- add health/readiness checks
- record model residency/readiness when possible
- support multiple local inference hosts cleanly

### Phase C — Iris route classifier

- define a strict structured classifier response
- keep the 7B model resident
- add confidence threshold and deterministic fallback rules
- benchmark classification latency and accuracy
- ensure Director treats classifier output as advisory

### Phase D — tiered routing

- implement Tier 0 through Tier 4 routing decisions
- add latency, privacy, health, and cost inputs
- prefer the least expensive/lowest-latency capable tier
- add clean failover

### Phase E — Capability Broker hardening

- move authorization decisions outside model output
- add principal/resource/action checks
- isolate consequential actions
- add audit events for allow/deny decisions

### Phase F — trust-aware memory/workers

- add provenance/trust metadata to memory
- prevent untrusted external content from directly creating authoritative memory
- isolate web/document/email workers from privileged capabilities

---

## 19. Rev 2 Certification Targets

Add certification coverage for:

- Iris classifier chooses the expected tier for representative prompts
- low-confidence classification fails safely
- classifier output cannot grant capabilities
- Atlas continues operating when Iris is offline
- Atlas continues operating when the heavy inference machine is offline
- heavy reasoning requests prefer the heavy local provider when healthy
- cloud fallback respects privacy and budget policy
- unknown principals cannot invoke private or consequential capabilities
- web/document content cannot directly authorize tools
- untrusted content cannot directly create authoritative long-term memory
- MacAgent requests pass through Atlas policy before consequential action
- provider cold/warm latency is measured separately
- Gmail preserves sender allowlists, sanitized body text, attachment distrust,
  and Gmail-thread conversation mapping
- family iMessage observation remains silent unless explicitly invoked and only
  writes structured memory candidates with provenance/confidence metadata

---

## 20. Rev 2 Architectural Invariants

These rules should remain true even as hardware changes:

1. Atlas Director is the authoritative control plane unless a future explicit architecture revision changes it.
2. No LLM is an authorization boundary.
3. Iris remains the Apple-native gateway while macOS capabilities are required there.
4. A small Iris model may recommend routing but never authorize privileged action.
5. Heavy inference machines are replaceable compute resources.
6. Connectors do not become alternate Directors.
7. Private memory and permissions are scoped to authenticated principals.
8. External content is untrusted until promoted through explicit trust/provenance rules.
9. Cloud models receive minimum necessary context.
10. Failure of a large model must not take down basic household control and communication.

---

## 21. Definition of the Rev 2 Target State

Rev 2 is operational when a household request can enter through Signal, Gmail,
iMessage/MacAgent, or a local presence node; be authenticated and normalized by
the appropriate connector; reach Atlas Director; use the resident Iris 7B model
for low-latency route classification when needed; execute directly, locally, on
the heavy inference machine, or in an approved cloud model according to policy;
invoke only authorized capabilities; and return a response with auditable route,
latency, provider, and authorization metadata. Authorized passive family context
streams may additionally create structured memory candidates without producing a
reply unless Freyja is explicitly addressed.
