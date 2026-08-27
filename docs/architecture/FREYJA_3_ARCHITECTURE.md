# Freyja Architecture

**Status:** governing architecture.
**Architecture rule:** build the complete intended system described here before
debugging individual pathways, unless a blocker prevents further construction.
**Supersedes:** Director-centered Freyja 2.x architecture wherever this document
conflicts with older documentation.

Freyja is a distributed household agent platform. Agents, models, tools,
memory, and machines are separate concepts and must not be collapsed into one
another.

```text
Agent   = identity + personality + memory + permissions + context + autonomous tool loop
Model   = replaceable inference resource
Tool    = capability an agent may invoke
Machine = infrastructure hosting agents, services, tools, or inference
```

The central design shift from previous revisions is that persistent agents own
the work. Gateways transport requests to agents. Inference endpoints provide
compute. Tools provide capabilities. No intelligent Director decides intent or
routes tasks by category.

## 1. Core Principles

1. Agents are first-class persistent actors.
2. Models are replaceable compute resources, not identities.
3. Tools are permissioned capabilities selected by agents.
4. Machines are movable infrastructure roles.
5. Gateways are deterministic transport and permission components.
6. Memory belongs to an agent, the household, a system function, or a separate
   enclave; it does not belong to a model or a host.
7. Local household machines are a trusted zone for Freyja household operation.
8. Cloud AI is never called directly by an agent; all cloud egress passes
   through the Privacy/Egress Gate.
9. Beth's professional paralegal system is a separate enclave and is not part
   of Freyja's trust domain.
10. Share compute when appropriate; never share trust.

## 2. No Director

Freyja removes the intelligent intent-routing Director.

The system MUST NOT contain a central intelligent component that decides whether
a request is weather, coding, calendar, home control, document work, general
chat, or any other task type.

The system uses a small deterministic Agent Gateway only to:

- authenticate and identify the sender
- resolve the conversation
- select the persistent agent
- enforce access permissions
- transport request and response envelopes
- produce audit events

The Agent Gateway MUST NOT:

- classify user intent
- select tools based on request semantics
- select models based on request semantics
- decide whether a request is coding, weather, calendar, memory, home control,
  document, or web work
- plan the work
- summarize the user's request for the agent
- silently answer instead of the selected agent

Once selected, the autonomous agent receives the complete request and determines
how to solve it. The agent is responsible for discovering missing information,
choosing tools, selecting inference capabilities, iterating, asking follow-up
questions, and returning the response.

### 2.1 Allowed Gateway Decisions

Gateway decisions are deterministic identity and policy decisions:

```text
incoming message
  -> authenticate channel and sender
  -> resolve sender identity
  -> resolve conversation
  -> resolve requested or default persistent agent
  -> check sender-agent permissions
  -> create agent handoff
  -> deliver handoff to agent runtime
  -> return agent response to channel
```

If the gateway cannot resolve identity, agent, conversation, or permission, it
fails closed with a safe transport-level error.

## 3. Agents

Persistent first-class agents:

| Agent | Owner / Domain | Role |
| --- | --- | --- |
| Freyja | Household | Shared household agent |
| Cloyd | Joe | Joe's personal agent |
| Benedict | Beth | Beth's personal agent |
| Agent 44 | Liam | Liam's personal agent |
| Jenna agent | Jenna | Jenna's personal agent |

Agents may run on different machines and may move without changing identity,
state, memory, or permissions.

An agent identity is stable even when:

- its runtime process moves machines
- its selected model changes
- its tool loop implementation changes
- its memory backend is migrated
- its channel changes from iMessage to Gmail, Signal, voice, browser, or shell

### 3.1 Agent Contract

Each agent has:

- stable `agent_id`
- display name and personality profile
- owner or domain
- private memory scope
- allowed shared memory scopes
- permissions and capability grants
- autonomous tool loop
- default local inference preferences
- optional cloud-egress policy
- audit identity

An agent request envelope includes:

- trace id
- channel
- sender identity
- resolved conversation id
- selected agent id
- sender-agent permission context
- raw user text
- attachments and attachment metadata
- reply context
- available tool policy
- memory scopes available to that agent
- cloud-egress policy

### 3.2 Freyja

Freyja remains the household agent. She owns shared household continuity,
household coordination, Home Assistant interaction, household routines, and
shared family context.

Freyja controls the house, but she is not a bottleneck for all household
actions. Personal agents may directly use authorized household capabilities.

### 3.3 Personal Agents

Cloyd, Benedict, Agent 44, and Jenna's agent are not aliases for Freyja. They
are persistent personal agents with their own identity, memory, permission
surface, and tool loop.

Personal agents may:

- use their owner's private memory
- use family/shared memory when authorized
- invoke household tools directly when authorized
- use local inference resources
- request cloud inference only through the Privacy/Egress Gate
- perform multi-step work without asking Freyja to route it

Personal agents MUST NOT:

- claim to be Freyja
- use another person's private memory without explicit policy permission
- bypass the Privacy/Egress Gate
- access the paralegal enclave

## 4. Machine Roles

Machine roles are infrastructure roles. They do not define agent identity.

### 4.1 Iris

Iris is Freyja's primary Apple incarnation.

Iris hosts:

- Freyja interactive runtime
- small always-hot local model / reflex brain
- Mac Agent
- Apple Messages integration
- Apple Calendar integration
- Apple Mail integration
- Apple Music integration
- Finder, Safari, Shortcuts, and macOS automation
- intelligent Home Assistant client

Iris delegates heavy reasoning to Vulcan. Iris may run an agent runtime when
that is the best operational placement, but the agent identity is not Iris.

### 4.2 Vulcan

Vulcan is the primary heavy inference appliance.

Vulcan hosts compute resources:

- Ollama
- LM Studio
- OpenAI-compatible local endpoints
- large general model
- coder model
- vision model
- embedding model
- future local inference providers

Vulcan hosts compute. Agents do not have to run on Vulcan.

### 4.3 Atlas

Atlas is persistent infrastructure.

Atlas hosts:

- Home Assistant
- memory and data services
- event bus
- schedulers
- messaging and backend services
- agent hosting
- durable service configuration
- observability and audits

Home Assistant remains the source of truth for device state.

### 4.4 Hera

Hera is Freyja's physical embodiment and perception / edge-AI node.

Hera hosts:

- avatar and voice interface
- cameras and microphones
- NPU continuous perception
- person detection
- occupancy detection
- object detection
- audio processing
- local or secondary inference

Hera converts raw sensor data into semantic events. It MUST NOT continuously
stream household video to Vulcan as the normal perception path.

Examples of Hera semantic events:

```text
person_present(room=kitchen, person=joe, confidence=0.91)
occupancy_changed(room=living_room, occupied=true, confidence=0.88)
object_seen(room=office, object=backpack, confidence=0.77)
voice_activity(room=kitchen, speaker=beth, confidence=0.83)
```

### 4.5 Mars

Mars is a secondary agent and worker host.

Mars may host:

- additional agents
- background jobs
- ingestion pipelines
- monitoring
- lower-priority services
- batch processing

## 5. Tool Fabric

Agents choose their own tools. The tool fabric exposes capabilities, metadata,
permission requirements, input/output schemas, safety policy, and audit hooks.

Tool categories include:

- web and search
- weather
- browser control
- calendar
- email
- messaging
- Mac Agent
- Home Assistant
- shell
- filesystem
- Git
- coding
- documents and PDFs
- vision
- music
- scheduling
- memory
- retrieval
- notifications

The tool fabric MUST NOT decide what the user means. It provides tools; the
agent decides whether and how to use them.

### 5.1 Coding Work

A coding request is handled by the selected agent, not by a Director.

For example, Cloyd may receive a request, inspect files, use Git and shell,
invoke a coder model, run tests, iterate, and report results. The agent decides
that the work is coding because it is the actor solving the request.

The tool fabric enforces permissions:

- which agent may inspect which repositories
- which agent may edit files
- which agent may run shell commands
- which agent may commit or push
- which agent requires approval for mutation
- which paths are forbidden

## 6. Inference Fabric

The Inference Registry maps capabilities to endpoints. It locates compute only.
It never decides how to solve a request.

Example capability mapping:

| Capability | Preferred Host / Provider |
| --- | --- |
| `general.large` | Vulcan |
| `code.large` | Vulcan |
| `vision.large` | Vulcan |
| `embeddings.local` | Vulcan |
| `general.local` | Iris |
| `vision.edge` | Hera |
| `premium` | OpenAI through Privacy/Egress Gate |

Supported provider types:

- Ollama
- LM Studio
- OpenAI-compatible local endpoints
- OpenAI
- future providers

The registry answers questions like:

```text
Where is a local large code model available?
Where is an edge vision model available?
Which endpoint provides embeddings inside the trusted zone?
Which premium provider is configured behind the Privacy/Egress Gate?
```

The registry MUST NOT answer:

```text
Is this a coding request?
Should the user request use weather tools?
Should this conversation go to Cloyd or Freyja?
Should the agent search the web?
```

Those are agent decisions after gateway handoff.

## 7. Memory

Memory is separated by ownership and scope:

- agent-private memory
- family/shared memory
- system memory
- enclave memory

Agent state must not depend on a particular model or host.

Every memory record stores:

- memory id
- owner
- scope
- source agent or system
- provenance
- timestamp
- confidence
- sensitivity
- update metadata
- expiration metadata
- allowed readers
- allowed writers
- audit trail

### 7.1 Agent-Private Memory

Agent-private memory belongs to one agent or one agent-owner relationship.

Examples:

- Cloyd's private memory for Joe
- Benedict's private memory for Beth
- Agent 44's private memory for Liam
- Jenna agent's private memory for Jenna

Agent-private memory is not automatically visible to Freyja or other personal
agents.

### 7.2 Family / Shared Memory

Family/shared memory contains household context authorized for shared use.

Examples:

- household preferences
- shared routines
- non-sensitive device context
- common schedules when authorized
- house state summaries

Personal agents may read or write shared memory according to policy.

### 7.3 System Memory

System memory contains operational state:

- host inventory
- service topology
- deployment state
- tool registry state
- inference registry state
- audit and health summaries
- non-secret configuration facts

System memory is not a dumping ground for private personal context.

## 8. Privacy and Cloud Egress

Local household machines form a trusted zone. Full private context may move
locally across trusted Freyja machines when policy permits.

No agent may send data directly to cloud AI.

All cloud AI requests pass through the Privacy/Egress Gate.

The Privacy/Egress Gate performs:

- classification
- context minimization
- redaction
- tokenization
- secret detection
- PII detection
- policy enforcement
- provider selection where policy allows it
- audit logging

Sensitive data defaults local. Secrets and restricted data cannot leave the
trusted zone unless policy explicitly permits a one-request override.

The one-request override must record:

- requesting agent
- requesting user
- data class
- destination provider
- purpose
- approved scope
- expiration
- audit id

Agents MUST NOT cache cloud-redacted substitutions as if they were the original
private facts.

## 9. Paralegal Enclave

Beth's professional paralegal system is not Benedict and is not part of
Freyja's trust domain.

The paralegal system is a separate enclave with:

- separate legal agent
- separate storage
- separate database
- separate vector store
- separate memory
- separate credentials and keys
- separate logs
- separate backups
- local-only document pipeline
- local-only OCR pipeline
- local-only embedding pipeline
- local-only inference pipeline
- cloud AI blocked
- cloud OCR blocked
- cloud storage blocked

The enclave may use Vulcan's local inference endpoints, but Freyja agents must
have no access to legal data.

Principle:

```text
SHARE COMPUTE, NEVER SHARE TRUST.
```

### 9.1 Enclave Boundary

The enclave boundary is security-critical.

Freyja household agents MUST NOT:

- read legal documents
- search legal embeddings
- access legal vector stores
- access legal credentials
- access legal backups
- read legal logs
- summarize legal case material
- use legal memory

The legal agent MUST NOT:

- use Freyja household memory
- expose Beth's professional legal data to Freyja
- use cloud AI, cloud OCR, or cloud storage
- share legal retrieval output with household agents

The only permitted shared resource is local compute through approved Vulcan
local inference endpoints.

## 10. Events and Scheduling

Atlas owns durable event bus and scheduler infrastructure. Agents may subscribe
to events they are authorized to observe.

Events are semantic, typed, and auditable. Raw sensor streams are not the
default system substrate.

Example event classes:

- message received
- conversation updated
- calendar changed
- home state changed
- person present
- occupancy changed
- reminder due
- ingestion completed
- memory updated
- tool invocation completed
- egress request approved or denied

Schedulers trigger agents or jobs through deterministic envelopes. A scheduler
does not become a Director.

## 11. Security Domains

Freyja uses explicit security domains:

| Domain | Scope |
| --- | --- |
| `household` | Freyja shared household system |
| `person.joe` | Joe / Cloyd private context |
| `person.beth` | Beth / Benedict private context |
| `person.liam` | Liam / Agent 44 private context |
| `person.jenna` | Jenna agent private context |
| `system` | infrastructure state |
| `paralegal` | separate professional legal enclave |

Cross-domain access requires explicit policy. Absence of policy means deny.

## 12. Implementation Order

Build Freyja architecture-first in this order:

1. Define canonical data models for agents, machines, tools, inference
   endpoints, memory scopes, security domains, gateway handoffs, and audits.
2. Implement the deterministic Agent Gateway with no intent classification.
3. Implement persistent agent registry and agent runtime contracts.
4. Implement the tool fabric registry and permission checks.
5. Implement the inference registry as compute lookup only.
6. Implement memory schemas for private, shared, system, and enclave memory.
7. Implement Privacy/Egress Gate before any cloud AI path.
8. Implement paralegal enclave boundaries before any legal ingestion.
9. Wire connectors to the Agent Gateway.
10. Wire agents to tools, memory, and inference fabric.
11. Wire machine-role deployments.
12. Run end-to-end integration tests.
13. Debug completed system pathways.

During construction, avoid piecemeal bug fixing unless a defect blocks further
architecture implementation.

## 13. Compatibility and Migration

Existing Director-centered endpoints, docs, and tests are legacy compatibility
surfaces during migration.

Legacy components may remain temporarily only when:

- they are clearly marked as compatibility paths
- they do not define new architecture
- they do not make semantic intent-routing decisions for Freyja
- they are behind migration flags or adapters
- replacement Agent Gateway and autonomous agent paths are being built first

New Freyja work must use this document as the governing architecture.

## 14. Non-Negotiable Requirements

- No intelligent intent-routing Director.
- Gateway selects agent and enforces policy only.
- Agents choose tools.
- Inference Registry locates compute only.
- Models are not agents.
- Machines are not agents.
- Memory is portable across models and hosts.
- Home Assistant remains source of truth for device state.
- Hera emits semantic events instead of default continuous video streaming to
  Vulcan.
- Cloud AI is reachable only through the Privacy/Egress Gate.
- Paralegal data is outside Freyja's trust domain.
- Share compute, never share trust.
