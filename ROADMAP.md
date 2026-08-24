# Freyja-OS Rev 2 Roadmap

**Status:** Authoritative implementation roadmap
**Architecture:** See `ARCHITECTURE.md`

Rev 2 reorganizes Freyja-OS around four durable planes: Atlas for control and state, the primary AI PC for cognition and local coding, Iris for Apple-native services through MacAgent, and Hera for household voice/avatar presence.

## Phase 0 — Freeze Rev 1 topology

- Stop adding new production responsibilities to Mars, Cloyd, NUCs, or spare Macs.
- Preserve working code, tests, identity, messaging, memory, provider adapters, certification, and Home Assistant work.
- Treat Rev 1 host-specific placement as deprecated.

**Exit:** No new work depends on Mars as Director, Iris as primary inference, or Hera as central reasoning.

## Phase 1 — Atlas becomes the control plane

- Deploy or validate the Freyja Director on Atlas.
- Move authoritative routing, identity, memory, capability registry, policy, scheduling, messaging gateways, databases, and audit services to Atlas.
- Place Home Assistant and its durable integration state on Atlas.
- Add health checks, backups, restart recovery, and service dependency documentation.
- Verify deterministic home actions do not require an LLM.

**Exit:** Atlas is the single control/state authority and core services survive AI-provider failure.

## Phase 2 — Capability-based routing

- Replace host-specific routing with logical capability names.
- Add registry metadata for host, schema, health, permissions, offline requirement, timeout, and certification status.
- Define initial namespaces: `model.*`, `home.*`, `apple.*`, `memory.*`, `identity.*`, `speech.*`, `vision.*`, `code.*`, `files.*`, `notifications.*`, `web.*`.
- Add honest failure behavior when a capability is unavailable.

**Exit:** Director requests capabilities rather than computers.

## Phase 3 — Primary AI PC cognition node

- Bring the new high-memory AI PC onto LAN/Tailscale.
- Benchmark local model runtimes.
- Establish fast chat, strong reasoning, coding, vision, embedding, and reranking profiles.
- Expose stable internal endpoints behind logical capability names.
- Add provider health and fallback behavior.
- Certify local inference quality and tool-call reliability.

**Exit:** Routine and advanced local reasoning no longer depends on Iris or Hera.

## Phase 4 — Offline local coding

- Build a bounded repository coding agent on the cognition node, exposed to Joe through Cloyd and backed by the primary local inference endpoint.
- Permit repository inspection, edits, approved commands, tests, and diff generation.
- Add workspace and command allowlists.
- Add rollback and review checkpoints.
- Certify that messaging cannot become unrestricted shell access.
- Keep inspection, tests, compilation, and diff validation available locally when cloud/chat credits are unavailable; require explicit approval for edits, staging, commits, and other consequential repository changes.

**Exit:** Freyja can perform meaningful coding work without cloud AI.

## Phase 5 — Iris MacAgent / Apple Services

- Define the MacAgent service contract.
- Implement Apple capability adapters using native APIs first, then AppleScript/Shortcuts, with GUI automation only as fallback.
- Prioritize Messages, Calendar, Contacts, Reminders, and Shortcuts.
- Integrate Apple identities with canonical Freyja `Person` records.
- Add live smoke tests and mocked certification contracts.

**Exit:** Freyja can reliably execute Apple-native actions through Iris.

## Phase 6 — Hera Presence Node

- Convert Hera into the kitchen reference Presence Node, with Freyja as the shared household voice and avatar.
- Implement wake word, VAD, microphone capture, STT, TTS, speakers, avatar display, interruption handling, and session transport.
- Connect Hera to Atlas rather than embedding independent authority.
- Add local timers and low-latency interaction handling.
- Add optional small fallback model only if it improves resilience.

**Exit:** Hera functions as an Alexa-class household Freyja interface.

## Phase 7 — Home Assistant hardening

- Repair and validate Zigbee and existing integrations.
- Define safe `home.*` capabilities.
- Separate read-only state queries, low-risk actions, and high-risk actions.
- Require evidence for claims about live home state.
- Add confirmation or policy gates for destructive/security-sensitive actions.
- Certify operation with AI PC unavailable and WAN unavailable.

**Exit:** Core household control is dependable and independent of cloud AI.

## Phase 8 — Identity and memory unification

- Make Atlas authoritative for identity and durable memory.
- Validate cross-platform mapping across Signal, Gmail, iMessage, Apple context, and Hera voice sessions.
- Preserve explicit-user-instruction priority over stored preferences.
- Add memory provenance, review, deletion, and retention behavior.
- Add passive-source memory candidates for authorized family iMessage context, including confidence, status, expiration, source thread, and update/invalidation metadata.
- Keep passive memory extraction separate from calendar creation; confirmed events may become calendar candidates only under separate permission rules.
- Eliminate accidental node-local memory authorities.

**Exit:** One person and one durable memory model span every interface.

## Phase 8.5 — Household personal agents

- Keep Freyja as the shared household intelligence, coordinator, and the personality presented through Hera and HomePods.
- Establish durable personal-agent assignments:
  - Joe -> Cloyd Gibbler (`cloyd-gibbler`), with bounded `code.inspect`, `code.edit`, `code.test`, `code.diff`, and `code.commit` capabilities
  - Beth -> Benedict (`benedict`)
  - Liam -> Agent 44 (`agent-44`)
  - Jenna -> reserved personal-agent slot; name and personality TBD
  - Infrastructure -> Agent Smith (`smith`)
- Select the personal agent only after canonical sender/person resolution.
- Give every personal agent a stable identity, personality prompt, owner, conversation continuity, personal memories, task state, and correction history.
- Use the same registered inference capabilities for all agents; do not bind an agent identity to a specific model or host.
- Make household-shared memory the normal collaboration layer. Allow ordinary family context to cross between agents while retaining an explicit private scope for information that must not be shared.
- Let Jenna route through Freyja until her personal-agent identity is deliberately selected; never invent a temporary name in conversation.
- Eliminate canned reset behavior: agents respond directly, avoid repeated introductions and “How may I help you?”, and use recent conversation plus relevant durable memory.
- Add connector-independent agent metadata so Signal, iMessage, Gmail, Hera voice sessions, and HomePod/Shortcut sessions resolve the same agent.
- Add certification for identity-to-agent routing, stable agent voice, restart continuity, shared-memory recall, correction retention, and private-scope enforcement.

**Exit:** Joe reaches Cloyd, Beth reaches Benedict, Liam reaches Agent 44, Jenna reaches Freyja pending her selection, shared household interfaces present Freyja, and every agent maintains a stable relationship across channels and service restarts.

## Phase 9 — Messaging convergence

- Keep Signal, Gmail, Telegram, and iMessage as gateways into the same Director.
- Finish production smoke tests for Signal, Gmail, and iMessage.
- Configure family aliases and permissions.
- Standardize safe error handling, sender allowlists, thread preservation, and attachment normalization.
- Enable Gmail as a work-environment fallback using Freyja's existing Gmail identity; run a mailbox transport, preserve Gmail threads as Freyja conversation threads, and keep gateway authorization separate from IMAP/SMTP delivery.
- Enable the family iMessage group as a passive context source that remains silent unless explicitly addressed by `Freyja` or `@Freyja`.
- Validate that Gmail cannot approve consequential actions and that family iMessage passive extraction stores structured candidates rather than raw conversation.
- Add HomePod/Shortcut entry points where useful.

**Exit:** Family members can reach the same Freyja safely from multiple interfaces, and authorized passive streams can improve shared context without becoming unbounded chatbot channels.

## Phase 10 — Offline certification

Test with WAN intentionally unavailable.

Required behaviors:

- Hera voice path works locally.
- Home Assistant actions work.
- Local reasoning works.
- Memory and identity work.
- Gmail and family iMessage connector logic works for authorized local cases without cloud dependency.
- Local coding works.
- Local vision/document retrieval works.
- Offline-capable Iris actions work.
- Cloud-only features fail visibly without fabricated results.

**Exit:** Offline-first is demonstrated, not assumed.

## Phase 11 — Reliability and recovery

- Add monitoring for all four production nodes.
- Document backup and restore procedures.
- Test Atlas recovery.
- Validate failure isolation for cognition, Apple, and Presence planes.
- Add deployment rollback procedures.

**Exit:** Loss of a non-Atlas node removes only its capability domain; Atlas recovery is documented and tested.

## Phase 12 — Retire unnecessary production nodes

- Remove Mars from required production service placement once Atlas cutover is verified.
- Remove any NUC/Pi/old-Mac service that no longer solves a unique requirement.
- Keep spare hardware available for experiments, backup, sensors, or future Presence nodes without making it architectural debt.

**Exit:** Production topology consists only of nodes with unique, justified responsibilities.

## Rev 2 completion criteria

Rev 2 is complete when:

1. Atlas is authoritative for Director, identity, memory, messaging, Home Assistant, and state.
2. The primary AI PC is authoritative for local cognition and coding workloads.
3. Iris provides production Apple capabilities through MacAgent.
4. Hera is a working kitchen Presence Node.
5. Home control works without cloud AI.
6. The system provides useful local AI and coding during WAN outage.
7. Identity remains consistent across voice and messaging interfaces.
8. Tool execution is evidence-grounded and unavailable capabilities never produce invented state.
9. Cloud use is optional, policy-controlled, observable, and cost-aware.
10. Passive family context extraction is bounded by source permissions, confidence, provenance, and action-authorization policy.
11. Spare machines are not part of production unless they provide a unique required capability.
12. Canonical people resolve to durable personal agents consistently across messaging, Hera, and HomePod entry points.
13. Personal agents retain distinct identity and continuity while collaborating through household-shared memory.
