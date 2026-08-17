# Freyja-OS Architecture — Rev 2

**Version:** 2.0  
**Date:** August 17, 2026  
**Status:** Authoritative target architecture  
**Primary owner:** Joe  
**Project:** Freyja-OS

---

## 1. Mission

Freyja-OS is a private personal and family computing layer that connects people to models, software services, household systems, information, and computers through one consistent identity, policy, memory, and orchestration system.

Freyja is **not a model**.

Freyja is **not a chatbot running on one computer**.

Freyja is **not a collection of independent AI agents**.

Freyja is the durable orchestration and trust layer between users and computing resources.

The system must remain Freyja even if:

- every LLM is replaced;
- the primary inference computer is replaced;
- Ollama is replaced;
- a messaging provider is replaced;
- Home Assistant moves to another host;
- Iris fails;
- Hera is offline;
- cloud AI is unavailable.

The architecture therefore separates **authority from cognition** and **identity from hardware**.

---

## 2. Architectural Invariants

These rules define Freyja more strongly than any particular implementation.

### 2.1 There is one authority

The Freyja Director is the authoritative control plane.

Only the Director may make final decisions regarding:

- user identity;
- permissions;
- memory access;
- memory writes;
- model escalation;
- capability authorization;
- high-risk actions;
- tool execution policy;
- request lifecycle;
- audit records.

Models may recommend.

Workers may execute.

Interfaces may receive and display.

**The Director decides.**

### 2.2 No model is Freyja

A model is an interchangeable cognition engine.

Models do not own:

- identity;
- permissions;
- durable memory;
- conversation authority;
- tool credentials;
- infrastructure state.

A 7B local model, a large local model, or a cloud frontier model receives the minimum context and capabilities necessary to perform the assigned task.

Replacing a model must not require changing the rest of the system.

### 2.3 No physical machine is Freyja

Hosts provide resources.

Their roles may change.

The architecture must tolerate replacing Iris, Atlas, Hera, Mars, or the heavy inference node without redesigning Freyja.

### 2.4 Interfaces are clients

iMessage, Signal, voice, HomePods, Hera, future mobile applications, web interfaces, and other entry points are adapters into the same Freyja request pipeline.

No interface gets its own independent Freyja brain.

### 2.5 Agents are roles, not kingdoms

Specialized agents such as Agent Smith or Benedict are execution profiles operating under Director authority.

An agent profile may define:

- purpose;
- model preference;
- memory scope;
- permitted capabilities;
- execution limits;
- personality;
- scheduling policy.

It does not create a separate authority stack.

### 2.6 Memory has security domains

Reasoning logic and stored knowledge are separate.

The Freyja orchestration system can be reused without carrying Freyja's personal memory into another application.

Examples of separate domains:

- Joe personal;
- Beth personal;
- household shared;
- Freyja infrastructure;
- Logix Review projects;
- future legal work;
- other professional projects.

Cross-domain access must be explicit.

---

## 3. Architectural Planes

Freyja is divided into four logical planes.

```text
                    +--------------------------+
                    |     INTERFACE PLANE      |
                    |                          |
                    | iMessage  Signal  Voice  |
                    | Hera  HomePods  Future UI|
                    +------------+-------------+
                                 |
                                 v
                  +------------------------------+
                  |       CONTROL PLANE          |
                  |                              |
                  |        ATLAS DIRECTOR        |
                  |                              |
                  | Identity                     |
                  | Authorization                |
                  | Sessions / context           |
                  | Memory policy                |
                  | Routing authority            |
                  | Tool authorization           |
                  | Capability registry          |
                  | Audit / observability        |
                  | Certification hooks          |
                  +-------+-----------+----------+
                          |           |
                cognition|           |capabilities
                          |           |
             +------------v---+   +---v----------------+
             | COGNITION PLANE|   | CAPABILITY PLANE   |
             |                |   |                    |
             | Iris hot 7B    |   | Apple / MacAgent   |
             | Heavy local AI |   | Home Assistant     |
             | Cloud models   |   | Calendar           |
             | Future models  |   | Messaging          |
             |                |   | Search / web       |
             +----------------+   | Files              |
                                  | Code               |
                                  | Notifications      |
                                  | Speech / vision    |
                                  | Future services    |
                                  +--------------------+
```

Persistent data is deliberately separated from all four planes:

```text
                 +-------------------------+
                 |      DATA DOMAINS       |
                 |                         |
                 | Personal memory         |
                 | Household memory        |
                 | Infrastructure state    |
                 | Project stores          |
                 | Audit records           |
                 | Documents / embeddings  |
                 +-------------------------+
```

---

## 4. The Vertical Request Path

Every normal user interaction should pass vertically through the same architecture.

```text
USER
  |
  v
INTERFACE ADAPTER
  |
  v
IDENTITY RESOLUTION
  |
  v
CANONICAL REQUEST
  |
  v
DIRECTOR
  |
  +-- Context
  +-- Permissions
  +-- Memory scope
  +-- Risk classification
  +-- Request policy
  |
  v
ROUTING DECISION
  |
  +-- Deterministic / no LLM
  +-- Iris fast cognition
  +-- Heavy local cognition
  +-- Cloud cognition
  |
  v
PLAN / TOOL REQUESTS
  |
  v
DIRECTOR AUTHORIZATION
  |
  v
CAPABILITY EXECUTION
  |
  v
RESULT
  |
  v
DIRECTOR
  |
  +-- Validate result
  +-- Decide memory writes
  +-- Audit
  +-- Format response
  |
  v
INTERFACE ADAPTER
  |
  v
USER
```

This is the architectural spine of Freyja.

New features should attach to this spine rather than create alternative paths around it.

---

## 5. Control Plane — Atlas

Atlas is the durable control-plane host.

Atlas should be boring, predictable, recoverable, and always available.

Primary responsibilities:

- Freyja Director;
- canonical request API;
- principal/identity resolution;
- authorization;
- permission policy;
- conversation/session coordination;
- routing authority;
- capability registry;
- memory access policy;
- memory-write policy;
- service health registry;
- request audit;
- latency and cost telemetry;
- scheduled orchestration;
- certification result collection.

Atlas may also host durable supporting services where appropriate.

### Atlas does not need to

Atlas does not need to perform heavyweight inference.

Atlas does not need Apple's native APIs.

Atlas does not need to render avatars.

Atlas does not need direct physical-device access.

Atlas should continue functioning when cognition services are unavailable.

A user should be able to ask Freyja for system status and receive a meaningful answer even when every LLM is down.

---

## 6. Cognition Plane

Cognition is a resource pool under Director control.

It is divided by latency, cost, privacy, and capability rather than by artificial agent identities.

### Tier 0 — deterministic processing

No LLM should be used when normal software can reliably answer the request.

Examples:

- identity lookup;
- capability lookup;
- current service health;
- simple structured commands;
- permission validation;
- known Home Assistant entity status;
- exact memory retrieval;
- schedule lookup.

This is the fastest and most reliable route.

### Tier 1 — Iris fast cognition

Iris hosts an always-resident small local model, initially approximately 7B.

Its purpose is low-latency cognition.

Suitable work includes:

- intent classification;
- route recommendation;
- simple conversation;
- request decomposition;
- extraction;
- summarization;
- simple planning;
- tool-selection recommendations;
- privacy classification assistance;
- confidence estimates.

The model should remain loaded whenever practical to minimize first-request latency.

#### Critical boundary

Iris may advise Director routing.

Iris does **not** own routing authority.

Director can accept, modify, or reject Iris's recommendation.

If Iris becomes unavailable, Director continues operating with deterministic routing and other inference resources.

### Tier 2 — routine local cognition

A stronger routine local model may be used for medium-complexity tasks that exceed the fast 7B model but do not justify the largest local model.

Tier 2 is a logical capability tier, not a specific host.

### Tier 3 — heavy local inference

The dedicated inference machine provides computational horsepower.

Suitable workloads:

- difficult reasoning;
- coding;
- large-context analysis;
- complex planning;
- document analysis;
- vision;
- larger local models;
- sensitive workloads that should not leave the local environment.

The inference machine owns no durable Freyja state.

It should be replaceable without migrating identity or memory.

### Tier 4 — cloud inference

Cloud inference is another cognition provider.

It is used when policy permits and when it materially improves:

- reasoning quality;
- context capacity;
- coding ability;
- specialized capabilities;
- reliability.

Cloud routing remains subject to:

- privacy classification;
- user policy;
- model allowlists;
- cost controls;
- sanitized context;
- service availability.

Cloud should be escalation, not architectural dependency.

---

## 7. Routing Architecture

Routing has two layers.

### 7.1 Router Advisor

The Router Advisor may use Iris's resident model to classify a request and provide structured advice.

Example output:

```json
{
  "request_id": "uuid",
  "recommended_tier": "fast_local",
  "task_class": "home_status",
  "needs_tools": true,
  "privacy": "household",
  "complexity": 2,
  "confidence": 0.94,
  "candidate_model": "local-7b",
  "reason": "Simple household tool request"
}
```

The advisor cannot dispatch work itself.

### 7.2 Router Authority

The Director combines Router Advisor output with deterministic policy:

- user permissions;
- privacy requirements;
- model availability;
- tool requirements;
- historical certification results;
- model capability;
- context size;
- latency;
- cost;
- user override.

The Director produces the final route decision.

Every route decision should be observable.

---

## 8. Iris Shadow Mode

Iris routing should initially remain in shadow mode.

For each certification request:

1. existing production routing makes the real decision;
2. Iris independently produces its recommendation;
3. both decisions are recorded;
4. success, latency, escalation, cost, and tool correctness are compared.

Iris should gain authority only after measured performance justifies it.

Certification should answer:

- Did Iris choose the right execution tier?
- Did it correctly identify tool requirements?
- Did it correctly recognize privacy?
- Did it avoid unnecessary escalation?
- Did it produce useful confidence?
- Did it reduce time to first useful action?

No routing promotion should be based only on subjective conversational impressions.

---

## 9. Capability Plane

Capabilities are explicit services registered with Director.

Examples:

```text
apple.messages.read
apple.messages.send
apple.shortcuts.execute

homeassistant.state.read
homeassistant.service.call

calendar.search
calendar.create
calendar.update

memory.search
memory.write

files.read
files.write

web.search

code.repository_status
code.test
code.modify

notifications.send
speech.transcribe
speech.synthesize
vision.inspect
```

Every capability should define:

- stable name;
- input schema;
- output schema;
- host;
- service endpoint;
- authentication mechanism;
- permissions required;
- risk class;
- confirmation policy;
- timeout;
- retry behavior;
- health state;
- audit requirements.

Models never receive unrestricted machine access merely because they need a capability.

---

## 10. Iris as Apple Edge Node

Iris has unique architectural value because it is a Mac attached to the Apple ecosystem.

Primary Iris responsibilities:

- MacAgent;
- native Apple integration;
- iMessage bridge;
- Shortcuts integration;
- HomePod-related bridging where useful;
- Apple-local capabilities;
- resident fast 7B cognition;
- routing advice;
- optional lightweight local processing.

Iris should expose these functions as authenticated private services.

Director invokes them through capability contracts.

Iris must not become a second Director.

---

## 11. Hera as Embodiment Node

Hera is the primary in-room human interface and future kitchen avatar.

Hera responsibilities may include:

- microphone capture;
- wake word;
- voice activity detection;
- local interruption detection;
- speech preprocessing;
- display;
- avatar rendering;
- camera input;
- speaker output;
- low-latency TTS;
- optional small local interaction model.

Hera sends normalized interaction events to Freyja and presents Freyja responses.

Hera does not own durable personal memory or system authority.

Future room endpoints should use the same protocol.

---

## 12. Mars

Mars is a utility and resilience node.

Possible responsibilities:

- monitoring;
- backup services;
- development utilities;
- CI/testing;
- network utilities;
- secondary service hosting;
- experimental workloads.

Mars should not normally be in the critical interactive request path.

Loss of Mars should not prevent a normal Freyja conversation.

---

## 13. Cloyd and Other Edge Devices

Cloyd is not required as an AI agent.

Where useful, Cloyd and similar devices should become narrowly scoped edge capability nodes.

Examples:

- Zigbee;
- Bluetooth;
- GPIO;
- sensors;
- room presence;
- MQTT;
- device bridges.

If Home Assistant already performs a function reliably, Freyja should use Home Assistant rather than reproduce it.

---

## 14. Identity

Identity must be resolved before cognition.

A normalized principal should be independent of transport.

Example:

```text
Signal sender ID --+
Telegram user ID --+--> principal: joe
iMessage address --+
Hera voice/profile-+
```

A principal may have:

- aliases;
- authentication sources;
- roles;
- capability permissions;
- memory domains;
- confirmation policy;
- administrative privileges.

A model should not determine who the user is from conversational text.

---

## 15. Memory Architecture

Memory is a Director-governed capability.

Models may request memory retrieval or suggest a memory write.

Models do not directly own the persistent store.

Memory access is determined by:

```text
principal
+ memory domain
+ task
+ permission
+ policy
```

Recommended logical scopes include:

```text
personal:joe
personal:beth
family:shared
system:freyja
project:logix/<project>
project:legal/<matter>
conversation/<id>
```

The underlying database may change without changing this contract.

### 15.1 Memory provenance

Long-term memory should preserve source and trust information.

Target memory metadata includes:

- memory ID;
- subject/person ID;
- scope/domain;
- content or structured fact;
- source type;
- source identifier;
- observed timestamp;
- created/updated timestamp;
- confidence;
- sensitivity;
- trust level;
- derivation/provenance links;
- optional expiration.

External content must not become authoritative household memory merely because a model summarized it.

---

## 16. Brain vs. Memory

The reusable Freyja brain consists of:

- orchestration patterns;
- routing;
- tool execution;
- provider abstraction;
- context assembly;
- safety/policy logic;
- certification;
- observability.

It must not contain Joe's personal memory.

This allows the same brain architecture to power separate applications such as Logix Review while using isolated project-specific stores.

```text
             REUSABLE BRAIN
                  |
        +---------+---------+
        |         |         |
        v         v         v
     FREYJA     LOGIX      LEGAL
     memory     stores     stores
```

No application should inherit another application's memory merely because it reuses Freyja code.

---

## 17. Specialized Agents

Agents are profiles executed by the system.

Example:

```yaml
name: agent_smith
purpose: freyja infrastructure maintenance
memory_scope:
  - system:freyja
permissions:
  - repository.read
  - repository.write_restricted
  - test.run
  - director.health
preferred_cognition:
  - heavy_local
  - cloud_if_allowed
execution:
  scheduled: true
  interactive: true
```

Benedict may similarly describe a user-specific experience without becoming a second independent orchestration system.

This prevents agent proliferation from becoming infrastructure proliferation.

---

## 18. Canonical Internal Request

All interfaces should eventually normalize into one internal request shape.

Conceptually:

```json
{
  "request_id": "uuid",
  "principal_id": "joe",
  "source": "imessage",
  "conversation_id": "uuid",
  "message": "Are the downstairs lights on?",
  "attachments": [],
  "timestamp": "ISO-8601",
  "interface_context": {}
}
```

Identity and permissions are resolved by trusted system components, not supplied as authoritative claims by a model.

---

## 19. Canonical Internal Result

Results should carry execution metadata separately from conversational content.

Conceptually:

```json
{
  "request_id": "uuid",
  "status": "completed",
  "message": "The downstairs lights are off.",
  "route": {
    "tier": "fast_local",
    "provider": "iris",
    "model": "local-7b"
  },
  "tools": [
    "homeassistant.state.read"
  ],
  "latency_ms": 640,
  "memory_writes": [],
  "cost_usd": 0.0
}
```

---

## 20. Provider and Health Registry

Director should maintain a live registry of cognition resources rather than hard-coding one inference host.

Each provider registration should include:

- provider/host ID;
- endpoint;
- model name;
- model family;
- capability tags;
- context window;
- expected latency class;
- tool-use support;
- vision support;
- privacy locality;
- approximate cost;
- health state;
- model residency state when detectable;
- current load when available;
- fallback priority.

Example capability tags:

- `router`;
- `fast_chat`;
- `coding`;
- `reasoning`;
- `vision`;
- `long_context`;
- `embeddings`;
- `cloud_frontier`.

Routing policy selects by required capability plus health, privacy, latency, and cost.

---

## 21. Latency and Model Residency

Cold-start delay is a system concern, not an operator inconvenience.

Rev 2 requirements:

- Iris keeps the primary 7B routing/reflex model resident;
- Director health checks distinguish host availability from model readiness;
- Director avoids escalating simple requests to a cold large model;
- inference hosts may expose warm-up/readiness endpoints;
- heavy models may be prewarmed when memory and power policy permit;
- provider telemetry records time-to-first-token separately from total latency when available.

Desired request flow:

```text
request
  -> Atlas Director
  -> deterministic fast path if possible
  -> otherwise Iris hot 7B classification
  -> Atlas applies policy
  -> direct tool / Iris answer / heavy local / cloud escalation
```

---

## 22. Observability

Every significant request should produce an execution trace.

At minimum:

- request ID;
- principal;
- interface;
- routing advice;
- routing decision;
- provider/model;
- model latency;
- tool requests;
- tool authorization decisions;
- tool results;
- fallbacks;
- final status;
- total latency;
- cloud cost;
- errors.

Sensitive content should be minimized or redacted from operational logs.

---

## 23. Certification Is Part of the Architecture

Certification is not merely a test suite.

It is the system used to decide whether a component is trustworthy enough to receive authority.

The gauntlet should test increasing levels of complexity:

```text
Level 0  - deterministic
Level 1  - simple conversation
Level 2  - classification/routing
Level 3  - single read-only tool
Level 4  - multi-tool reasoning
Level 5  - memory retrieval
Level 6  - state-changing tool
Level 7  - ambiguous request
Level 8  - privacy/security boundary
Level 9  - degraded service/fallback
Level 10 - adversarial/chaos
```

Metrics should include:

- correctness;
- tool accuracy;
- route accuracy;
- latency;
- first-token latency;
- escalation frequency;
- cost;
- failure recovery;
- unauthorized-action prevention.

---

## 24. Failure Domains

Failure should degrade capability rather than collapse Freyja.

### Iris unavailable

Lose:

- Apple-native capabilities;
- fast resident model.

Keep:

- Director;
- identity;
- memory;
- other tools;
- heavy inference;
- cloud inference.

### Heavy inference node unavailable

Lose:

- large local cognition.

Keep:

- Iris fast model;
- deterministic processing;
- cloud escalation where allowed;
- tools.

### Cloud unavailable

Lose:

- cloud escalation.

Keep:

- all local functions.

### Hera unavailable

Lose:

- kitchen/avatar interface.

Keep:

- messaging and all Freyja services.

### Mars unavailable

Normal user interactions should be largely unaffected.

### Atlas unavailable

This is the major Freyja control-plane failure.

Atlas therefore requires:

- reliable storage;
- backups;
- tested restore;
- service supervision;
- health monitoring;
- documented replacement procedure.

A later release may provide standby Director capability, but distributed multi-master Director operation is not currently justified.

---

## 25. Security Boundaries

The most important security boundary is between **intent** and **authority**.

An LLM saying:

> unlock the front door

is not authorization.

Director must independently know:

- who requested it;
- whether they have permission;
- whether confirmation is required;
- which capability can perform it.

Other requirements:

- private network communication;
- authenticated service-to-service APIs;
- least privilege;
- no unrestricted shell from messaging;
- secrets unavailable to models;
- explicit high-risk confirmation;
- memory-domain isolation;
- sanitized logs;
- capability allowlists;
- fail-safe behavior.

External content such as web pages, email bodies, documents, and unknown messages is untrusted data. Untrusted content must not gain authority merely because an LLM interpreted it.

---

## 26. Network Model

Primary inter-node transport should remain private.

Preferred order:

1. localhost;
2. trusted LAN;
3. Tailscale/private overlay.

Internal APIs should use authenticated requests even on the private network where practical.

Public inbound ports should not be required for core Freyja services.

No Ollama endpoint, database, or Home Assistant administrative endpoint should be exposed directly to the public internet.

---

## 27. What Freyja Should Not Build

Freyja should not duplicate reliable commodity systems merely for architectural purity.

Use existing systems for:

- home automation;
- inference serving;
- databases;
- messaging;
- source control;
- speech engines;
- network overlays;
- operating-system services.

Freyja's unique value is:

```text
IDENTITY
+ CONTEXT
+ MEMORY POLICY
+ PRIVACY
+ ROUTING
+ AUTHORIZATION
+ CAPABILITY ORCHESTRATION
+ CERTIFICATION
```

That is the product.

---

## 28. Migration Strategy

Do not rewrite Freyja from scratch.

Migrate the existing system vertically.

### Phase 1 — Establish the spine

Prove:

```text
Joe
 -> one working messaging interface
 -> principal resolution
 -> Atlas Director
 -> routing
 -> model/tool
 -> Atlas Director
 -> response
```

Instrument the entire request.

### Phase 2 — Iris Router Advisor

Connect Atlas Director to Iris.

Keep the 7B model resident.

Run Iris routing in shadow mode against the certification gauntlet.

Do not transfer final routing authority yet.

### Phase 3 — Apple capability service

Formalize MacAgent/iMessage/Shortcuts as Iris-hosted capabilities called by Director.

Remove assumptions that Apple integration implies orchestration authority.

### Phase 4 — Capability normalization

Move existing Home Assistant, calendar, files, messaging, code, and other tools behind the capability registry.

Do not rewrite working integrations simply to rename them.

Wrap and normalize where possible.

### Phase 5 — Memory domains

Make identity and memory scope explicit.

Preserve existing shared-memory behavior during migration while establishing domain boundaries.

### Phase 6 — Heavy inference node

Expose the dedicated inference system through the provider abstraction.

It receives tasks and context but owns no Freyja identity or persistent memory.

### Phase 7 — Hera

Connect Hera to the same canonical request pipeline.

Voice and avatar become another interface, not another brain.

---

## 29. Immediate Vertical-Slice Definition of Done

The first Rev 2 slice is complete when the following works reliably:

```text
Joe sends:
"Are the downstairs lights on?"

        messaging interface
               |
               v
        principal = joe
               |
               v
        Atlas Director
               |
               v
   Iris router advice/shadow
               |
               v
    Director route decision
               |
               v
Home Assistant read capability
               |
               v
   Director validates result
               |
               v
      reply returned to Joe
```

The trace must prove:

- the correct principal was identified;
- Iris advised but did not authorize;
- the authoritative route came from Director policy;
- the correct capability was selected;
- the tool had appropriate permission;
- no unnecessary cloud model was used;
- the result came back through Director;
- latency was recorded;
- no unauthorized memory write occurred.

Then repeat with:

- calendar lookup;
- memory question;
- local conversational question;
- difficult reasoning request;
- cloud escalation;
- state-changing Home Assistant request;
- unauthorized user;
- Iris offline;
- inference node offline;
- malformed model/tool output.

---

## 30. Current Deployment vs. Target Architecture

This document defines the authoritative **target architecture**. Existing deployed components may temporarily differ during migration.

Status and handoff documents must distinguish:

- what exists now;
- what is deployed now;
- what has been tested;
- what Rev 2 requires next.

A target diagram must never be used as evidence that an unfinished migration is already operational.

---

## 31. Rev 2 Architectural Test

A component belongs in the architecture only if these questions have clear answers:

1. What plane is it in?
2. Who owns its authority?
3. What stable contract does it expose?
4. What data may it access?
5. What happens if it disappears?
6. Can it be replaced without redesigning Freyja?

If those answers are unclear, the component is too tightly coupled.

---

## 32. Final Model

The simplest description of Freyja Rev 2 is:

> **Atlas is the durable nervous system. Iris supplies fast reflexes and Apple-native capabilities. The heavy inference node supplies muscle. Hera supplies a body. Models supply cognition. Tools supply abilities. Memory belongs to explicit security domains. The Director remains the sole authority tying them together.**

Everything else is implementation detail.
