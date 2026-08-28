# Freyja Completion Audit

Last audited: 2026-08-28.

This audit checks the current Freyja implementation against
`docs/architecture/FREYJA_3_ARCHITECTURE.md`. It does not redefine success
around passing tests alone. Repo state, live service state, and distributed smoke
checks are treated as separate evidence.

## Summary

Freyja is functionally deployed end-to-end across reachable machines. Hera is
now assigned to the Atlanta household IoT/logging and voice/avatar edge role.
Camera hardware remains out of current scope until the Atlanta camera/sensor
hardware is installed and visible. Hera publishes live semantic status events
with auto-probed audio/NPU/camera metadata, and the failing legacy camera loop
is disabled.

## Build-Order Audit

| Architecture Item | Status | Evidence |
| --- | --- | --- |
| Canonical data models | Proved | `src/freyja/foundation_models.py`; architecture tests cover agents, machines, tools, inference endpoints, memory scopes, security domains, handoffs, audits, and semantic events. |
| Deterministic Agent Gateway with no intent classification | Proved | `src/freyja/agent_gateway.py`; gateway creates handoff envelopes and audits identity/policy decisions only. |
| Persistent agent registry/runtime contracts | Proved | `src/freyja/foundation_seed.py`, `src/freyja/agent_runtime_v3.py`; Freyja, Cloyd, Benedict, Agent 44, and Jenna are seeded as persistent identities with separate owners/scopes/grants. |
| Tool fabric and permission checks | Proved | Shared registry plus Freyja runtime mapping execute permitted tools and deny under-specified mutations without fabricated success. |
| Inference registry as compute lookup only | Proved | `src/freyja/inference_registry_v3.py`; Atlas live health verifies Vulcan Ollama, OpenAI-compatible, and LM Studio endpoints. |
| Private/shared/system/enclave memory schemas | Proved | Freyja memory store/API uses owner domain, scope, provenance, classification, allowed readers/writers, and candidate review. |
| Privacy/Egress Gate before cloud AI | Proved | `src/freyja/privacy_egress.py`; tests cover private data failing closed and explicit override behavior. |
| Paralegal enclave boundary before legal ingestion | Proved | Paralegal domain and memory tests deny household reads/writes while allowing only local Vulcan compute sharing. |
| Connectors wired to Agent Gateway | Proved | Iris iMessage canonical path enters Freyja gateway/runtime; family route smoke passes for Joe, Beth, Liam, and Jenna. |
| Agents wired to tools, memory, and inference | Proved | Live canonical requests use Vulcan inference, scoped memory, Home Assistant, MacAgent, and worker/tool results. |
| Machine-role deployments | Proved for current scope | Iris, Atlas, Vulcan, Mars, and Hera have role-specific services deployed. Hera's Atlanta IoT/logging role is documented; camera-backed Hera perception is future scope until the Atlanta camera/sensor hardware is installed. |
| End-to-end integration tests | Proved for current scope | Full repo tests pass; live distributed smokes pass for iMessage, Atlas, Vulcan, Mars workers, Home Assistant, MacAgent, LM Studio, and Hera semantic status events. |
| Debug completed system pathways | Proved for current scope | Major integration blockers fixed; Hera camera recovery remains documented future work for when the camera hardware exists. |

## Required Proof Points

| Proof Point | Status | Evidence |
| --- | --- | --- |
| 1. Gateway selects the correct agent | Proved | Architecture tests and live family iMessage route smoke show Joe->Cloyd, Beth->Benedict, Liam->Agent 44, Jenna->Jenna. |
| 2. Agent receives the natural-language objective | Proved | Agent handoff/runtime tests assert raw prompt propagation; live canonical requests preserve user text into agent runtime. |
| 3. Agent independently chooses tools | Proved | Runtime tests and live canonical smokes show tool selection after gateway handoff; gateway does not choose task tools. |
| 4. Agents use Vulcan inference remotely | Proved | Atlas canonical Cloyd smoke returned through `vulcan-reason`; Atlas inference health verifies Vulcan Ollama, OpenAI-compatible, and LM Studio endpoints reachable/model-available. |
| 5. Multi-step autonomous tool work functions | Proved | Runtime plan/observe/retry tests and Mars worker smokes show bounded iteration, failure observation, retries, and no fabricated mutation success. |
| 6. Iris uses Mac Agent/Apple capabilities | Proved | Atlas-to-Iris canonical execution returns successful MacAgent browser, music, and `email.read` tool results; iMessage family route smoke passes. |
| 7. Freyja controls Home Assistant on Atlas | Proved | Atlas sidecar reads HA state, denies unapproved control, and executes approved HA light control through policy boundary. |
| 8. Hera publishes semantic perception events | Proved for current scope | Hera timer publishes authenticated semantic events to Atlas with auto-probed metadata. Latest event reports no camera devices, nonzero audio source evidence, and NPU detected. Camera-derived perception is future scope for the Atlanta camera/sensor hardware. |
| 9. Memory privacy boundaries work | Proved | Tests and live smokes verify Joe private memory hidden from Beth, paralegal writes denied to household agents, and inferred memory candidates require review. |
| 10. Cloud cannot bypass privacy controls | Proved | Egress gate tests enforce local default for private/sensitive/restricted data and require explicit one-request override. |
| 11. Agents recover from inference outages | Proved at contract level | Runtime fallback tests cover unhealthy endpoints and preserved agent identity across endpoint changes. |
| 12. Agent identity is independent of model/host | Proved | Runtime endpoint-change tests and seeded agent identities keep agent id/memory/permissions separate from compute endpoint. |

## Live Machine Evidence

| Machine | Evidence |
| --- | --- |
| Iris | MacAgent running on `0.0.0.0:8765`; authenticated health advertises Apple Messages, Calendar, Contacts, Mail, Music, Browser, and Shortcuts. Apple Mail count-only fallback returns INBOX counts from the local envelope index. |
| Atlas | Freyja sidecar healthy on Tailscale port `8300`; Home Assistant, memory, events, schedules, workers, machine heartbeat, audit, MacAgent client, and live Vulcan inference configured. |
| Vulcan | Ollama on `11434`; OpenAI-compatible Ollama proxy on `8088`/`8090`; LM Studio `llmster` installed and `freyja-lmstudio-server.service` enabled/active on Tailscale port `1234`. |
| Hera | Atlanta household IoT/logging and voice/avatar edge node. Avatar, wake, agent, Hermes adapter, Ollama, and Freyja semantic publisher timer are the active service set. AMD NPU and audio source were visible at last check. No `/dev/video*` was visible because camera hardware was not installed, so the legacy vision restart loop is disabled and replaced by semantic no-camera status events. |
| Mars | Freyja sidecar healthy on `127.0.0.1:8300`; machine heartbeat and worker runner timers active; document, email-content, and web-research worker smokes completed as untrusted observations. |

## Future Camera Scope

Hera real camera-backed perception is skipped until the Atlanta camera/sensor
hardware is installed and visible. Required evidence will be a visible camera
device or equivalent real sensor feed, followed by a semantic event such as
`person_present`, `occupancy_changed`, or `object_seen` derived from that sensor
without continuously streaming raw video to Vulcan.

Current no-camera evidence:

- `ls /dev/video*` on Hera returns no devices.
- `freyja3-hera-semantic-publisher.timer` is active and publishes
  `camera_unavailable` with `camera_device_count=0`.
- PipeWire reports audio source metadata and PCI reports an AMD NPU.
- The previous `freyja-vision.service` restart loop was disabled because it
  repeatedly failed against the missing camera device.

Recovery commands for the future camera hardware are documented in
`docs/operations/hera-camera-recovery.md`.

## Current Readiness Estimate

Current implementation readiness is 100% for the reachable current-scope
deployment. Future Atlanta camera/sensor hardware can add camera-derived Hera
semantic perception using the documented recovery path.
