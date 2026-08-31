# Family Agent Blueprint

Last updated: 2026-08-30.

## Intent

Give each family member a dependable personal agent surface while keeping
Freyja authoritative for identity, memory policy, tools, privacy, audit, and
household coordination.

Msty Nexus can provide the local model gateway and per-agent presets, but Nexus
must not become the source of truth for family identity, school records,
permissions, or memory ownership.

## Core Idea

Each interaction enters through a trusted family-member route. The route stamps
the request with the speaker, target agent, memory scope, document scope, tool
policy, and audit context before any model is called.

```text
channel or app
  -> family route
  -> identity and policy stamp
  -> memory/document context assembly
  -> selected family agent
  -> Nexus preset
  -> local model on Vulcan
  -> Freyja response wrapper and audit
```

The model may express who it is talking to, but it does not decide who the
speaker is. Identity comes from the authenticated endpoint, channel, token,
device, or account.

## Principal Routes

Keep the public routing surface small. Do not deploy a separate service for
every person-agent pair.

```text
POST /family/joe
POST /family/beth
POST /family/liam
POST /family/jenna
```

The body can request a target agent:

```json
{
  "agent": "agent_47",
  "message": "Can you help me study this worksheet?",
  "attachments": []
}
```

The route resolves to a canonical handoff:

```text
actor_principal: person:liam
target_agent: agent_47
source_channel: web|msty|imessage|homepod|gmail|telegram
memory_scope: person:liam
document_scope: person:liam/school
tool_policy: child_homework
conversation_id: stable per thread
```

Model aliases can exist as convenience labels, but they should compile down to
the same route metadata:

```text
@joe/cloyd
@beth/benedict
@liam/agent_47
@jenna/jennacide
```

## Family Member Spaces

Each family member gets a private space with explicitly named subspaces.

```text
person:liam
  profile
  conversations
  school
  assignments
  preferences
  corrections

person:beth
  profile
  conversations
  documents
  household
  preferences
  corrections
```

Shared family memory remains separate:

```text
family
  household facts
  shared schedule
  Home Assistant preferences
  family travel
  shared reminders
```

Restricted enclave memory remains separate from both personal and family
memory:

```text
enclave:paralegal
  legal documents
  legal research
  legal work product
```

## Liam Homework Example

Liam's agent should get better as assignments are uploaded, without turning
into an answer mill.

Upload flow:

```text
file upload
  -> OCR/document extraction
  -> classify class, topic, due date, rubric, teacher constraints
  -> store original file and extracted text in person:liam/school
  -> create assignment record
  -> update skill observations only when evidence is strong
```

Assignment record:

```text
owner: person:liam
class: Algebra
topic: linear equations
due_date: optional
source_file: stored document id
teacher_policy: unknown|tutoring_allowed|no_ai_drafting|custom
support_mode: hint_first
observations:
  - Liam made sign errors in two-step equations.
  - Visual balance-scale explanations helped.
```

The agent can then choose support style:

```text
homework help: hints and explanations first
study prep: quiz and spaced review
draft review: comments and revision prompts
parent summary: progress and blockers, not raw private chat by default
```

## Policy Modes

Child academic routes need explicit modes:

| Mode | Allowed behavior |
| --- | --- |
| `hint_first` | Ask guiding questions, give partial hints, avoid final answer unless requested by an allowed reviewer. |
| `explain_concept` | Teach the underlying concept with new examples. |
| `check_work` | Review Liam's attempted answer and explain mistakes. |
| `quiz` | Generate practice questions and grade responses. |
| `outline_only` | Help plan writing without drafting final prose. |
| `parent_summary` | Summarize progress, assignments, and concerns for a parent. |

The default for schoolwork should be `hint_first`.

## Nexus Role

Nexus is useful for:

- local OpenAI-compatible endpoint on Vulcan
- per-agent presets
- model catalog and provider routing
- tokened access to local models
- usage visibility
- optional licensed features if needed

Freyja remains responsible for:

- family principal registry
- endpoint-to-principal mapping
- memory and document namespaces
- child homework policy
- privacy and cloud egress gates
- parent/child visibility rules
- audit events
- channel behavior and response wrapping

If a Nexus license is required for stable multi-user app tokens, presets, usage
controls, or administrative features, it is an operations dependency. Buying a
license should not change the ownership boundary above.

## Problems To Design Against

- Wrong principal stamped on a conversation or upload.
- A model infers identity from text instead of trusted route metadata.
- Uploaded school documents leak into shared family memory.
- A child agent gives complete homework answers when tutoring is intended.
- Parents receive raw private child conversations when they only need progress
  summaries and safety signals.
- One agent writes long-lived claims about a person from weak evidence.
- Old academic observations remain active after the child improves.
- Legal enclave memory leaks into ordinary Beth or family memory.
- Cloud routing is used for private documents without explicit approval.
- Model aliases grow into an unreviewable 4-by-5 matrix of special cases.

## Required Data Fields

Every family-agent handoff should carry:

```text
actor_principal
target_agent
source_channel
authenticated_subject
memory_scope
document_scope
tool_policy
privacy_policy
cloud_policy
conversation_id
request_id
attachments
parent_visibility
audit_reason
```

Every memory write should carry:

```text
owner_scope
visibility
source_type
source_id
confidence
created_at
expires_at optional
correction_of optional
```

## MVP

Phase 1 should be intentionally small:

1. Add canonical family routes for Joe, Beth, Liam, and Jenna.
2. Stamp route metadata before calling the existing `AgentGateway`.
3. Add model aliases for the default personal agent for each person.
4. Create private document scopes for Liam and Jenna school uploads.
5. Store assignment uploads and extracted text without advanced learning logic.
6. Add `hint_first`, `check_work`, and `quiz` policy modes.
7. Add audit events proving principal, agent, memory scope, and document scope.

Do not start with adaptive tutoring, parent dashboards, or automatic progress
models. First make the identity, routing, storage, and policy boundaries
boring and testable.

## Implemented Route Contract

Initial API surface:

```text
POST /family/{member}
```

Supported members:

```text
joe, beth, liam, jenna
```

Request:

```json
{
  "message": "Help with algebra.",
  "agent": "agent_47",
  "conversation_id": "optional",
  "message_id": "optional",
  "attachments": [],
  "policy_mode": "check_work",
  "channel": "family"
}
```

For child homework routes, `policy_mode` is limited to:

```text
hint_first, check_work, quiz
```

The response includes a `family_route` block with the stamped identity,
agent, memory scopes, document scope, tool policy, privacy policy, cloud
policy, parent visibility, and request/message ids. This block is the audit
surface proving that identity and memory boundaries were established before
runtime execution.

## Later

- Per-class assignment timelines.
- Teacher/rubric policy capture.
- Skill observations with decay and correction.
- Parent progress summaries.
- Study plans from upcoming due dates and weak topics.
- School-safe web research.
- Optional Nexus license evaluation for token/app/preset/usage management.
