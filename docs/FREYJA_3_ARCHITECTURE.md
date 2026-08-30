# Freyja 3.0 Architecture Checkpoint

Last updated: 2026-08-30.

This checkpoint preserves the Freyja 3.0 architecture before the Freyja 4.0
Msty Nexus evaluation. The governing detailed architecture remains
`docs/architecture/FREYJA_3_ARCHITECTURE.md`; this file records the stable
system contract at the requested handoff path.

## Core Rule

Freyja 3.0 removes the intelligent intent-routing Director. The system must not
contain a central brain that classifies a request as weather, coding, calendar,
home control, document work, chat, or another task type and then plans the work.

Allowed gateway work is deterministic:

```text
channel adapter
  -> authenticate sender and channel
  -> resolve conversation
  -> resolve requested/default persistent agent
  -> enforce sender-agent permissions
  -> create agent handoff
  -> deliver the complete request to the agent runtime
  -> wrap the selected agent response for the originating channel
```

The selected persistent agent owns the tool loop, inference choice, memory use,
follow-up questions, and final answer.

## Identity Split

Freyja is the household interface and shared household agent. She keeps identity,
personality, privacy policy, channel routing, response wrapping, tool policy,
memory boundaries, family-agent coordination, Home Assistant access, calendar
access, iMessage/Signal/Gmail/voice ingress, and audit behavior.

Iris is Freyja's Apple body. Iris owns macOS and Apple-native capabilities:
iMessage, Apple Calendar, Contacts, Mail, Music, Safari, Shortcuts, and local
MacAgent execution. Iris may host a hot reflex/classifier only as advisory or
explicitly configured agent runtime placement; Iris is not the brain.

Vulcan is the brain and primary inference appliance. Vulcan owns heavy local
compute: Ollama, LM Studio, OpenAI-compatible local endpoints, general models,
coder models, vision models, and embeddings.

Atlas is the always-on gateway and infrastructure host. Atlas owns durable
service configuration, memory/data services, event bus, scheduler, worker queue,
Home Assistant, connector coordination, observability, and audits.

Hera is avatar, presence, and perception edge. Hera publishes semantic events
instead of continuously streaming raw household video to Vulcan.

## Persistent Family Agents

Freyja 3.0 treats agents as first-class persistent actors, separate from models
and machines:

| Agent | Domain | Role |
| --- | --- | --- |
| Freyja | Household | Shared household agent and home interface |
| Cloyd Gibbler | Joe | Joe's personal agent |
| Benedict | Beth | Beth's personal agent |
| Agent 44 | Liam | Liam's personal agent |
| Jenna | Jenna | Jenna's personal agent |

Agent identity survives model changes, endpoint changes, process moves, memory
migrations, and channel changes.

## Tool Fabric

Tools are permissioned capabilities, not routes chosen by a central Director.
Agents receive an allowed tool surface and choose tools themselves. The current
fabric includes web search, weather, browser, calendar, email, messaging,
Home Assistant read/control, MacAgent, shell/filesystem/git/coding, documents,
vision, music, scheduling, memory, and system health.

Mutation tools require explicit policy and approval where appropriate.
Under-specified mutation requests must ask follow-up questions instead of
fabricating success.

## Inference Registry

The inference registry is compute lookup only. It does not classify intent,
select tools, plan work, or act as an agent. Freyja 3.0 registers logical
capabilities such as `general.local`, `general.large`, `code.large`,
`vision.large`, and `embeddings.local` across machine-hosted endpoints.

Current seeded Vulcan endpoints include:

| Endpoint | Provider | Model | Purpose |
| --- | --- | --- | --- |
| `vulcan-reason` | Ollama | `qwen2.5:32b-instruct` | local reasoning/chat |
| `vulcan-deep` | Ollama | `qwen2.5vl:72b` | deep/long-context reasoning |
| `vulcan-code` | Ollama | `qwen3-coder-next:q4_K_M` | coding |
| `vulcan-vision` | Ollama | `qwen2.5vl:72b` | vision |
| `vulcan-embeddings` | Ollama | `nomic-embed-text` | embeddings |
| `paralegal-local` | Ollama | configured local model | paralegal enclave compute |

## Privacy And Egress Gate

Cloud AI is never called directly by an agent. Cloud requests must pass through
the Privacy/Egress Gate after classification and minimization. Private,
sensitive, and restricted data fail closed unless a specific one-request
override is present. Local household machines are the trusted default.

## Paralegal Enclave

Beth's professional paralegal system is a separate enclave, not a household
memory scope. Household agents may share local Vulcan compute only through
policy; they must not read, write, or infer access to paralegal enclave memory.

## Architecture-First Build Order

Freyja 3.0 is built architecture-first:

1. Define canonical data models and security domains.
2. Establish deterministic gateway handoff without intent routing.
3. Seed persistent agents, machines, tool grants, and inference endpoints.
4. Wire agent runtime to tools, memory, inference lookup, and audit.
5. Enforce privacy, egress, and enclave boundaries.
6. Add channel adapters and machine services around the same canonical path.
7. Debug integrated pathways only after the intended system shape exists.
