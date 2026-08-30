# Freyja 3.0 Status

Last updated: 2026-08-30.

## Repository State At Checkpoint

- Active repository: `/Users/freyja/freyja-os`
- Branch: `main`
- Remote: `origin https://github.com/smokinjoev/freyja-os.git`
- Starting state: `main` was ahead of `origin/main` by 3 commits before this
  checkpoint work.
- Pre-existing uncommitted work was present in source, tests, docs, config, and
  Open WebUI deployment files. Those changes were treated as user/worktree
  state and were not reverted.

## Implemented Architecture

- Deterministic Agent Gateway creates handoff envelopes without intent
  classification, model selection, tool selection, or planning.
- Persistent agents are seeded for Freyja, Cloyd Gibbler, Benedict, Agent 44,
  and Jenna.
- Agent runtime receives the raw objective, chooses tools, performs bounded
  observe/retry work, asks follow-up questions for unsafe mutations, and can use
  live inference only when explicitly enabled.
- Tool grants and machine affinities preserve the split between agent identity,
  tool capability, and host placement.
- Freyja scoped memory separates private, household, system, candidate-review,
  and paralegal enclave records.
- Privacy/Egress Gate blocks private/sensitive/restricted cloud AI by default.
- Hera semantic event publishing, Atlas sidecar APIs, worker queues, schedulers,
  machine heartbeat, and audit APIs are represented in code and prior status
  docs.

## Machine Roles

| Machine | Freyja 3.0 Role |
| --- | --- |
| Iris | Apple/body services: iMessage, Apple Calendar, Contacts, Mail, Music, Safari, Shortcuts, and MacAgent |
| Vulcan | Brain/heavy local inference: Ollama, LM Studio, local OpenAI-compatible APIs, code, vision, embeddings |
| Atlas | Always-on gateway/infrastructure: Home Assistant, memory, events, scheduler, worker queue, connectors, audits |
| Hera | Avatar/presence/perception edge, semantic events, voice/avatar services |
| Mars | Worker/secondary ingestion and monitoring host |

## Verification Evidence

- Architecture tests exist in `tests/test_freyja3_architecture.py`.
- Host role documentation tests exist in `tests/test_host_role_docs.py`.
- Freyja 3.0 status and completion audit exist under `docs/architecture/`.
- The current source seeds persistent agents, machine roles, tool grants, and
  Vulcan inference endpoints in `src/freyja/foundation_seed.py`.
- Runtime/config compatibility layers exist in `src/freyja/agent_runtime_v3.py`,
  `src/freyja/inference.py`, `src/freyja/inference_registry_v3.py`, and
  `src/freyja/config.py`.

## Open State

Freyja 3.0 is preserved as the architecture baseline. Freyja 4.0 work should
evaluate whether Nexus can own model gateway duties without taking identity,
policy, tools, memory, channel routing, or response authority away from Freyja.
