# Freyja 3.0 Status

Last updated: 2026-08-26.

## Completed Repo Work

- Added Freyja 3 canonical models for security domains, persistent agents, machine roles, tool grants, gateway handoffs, inference endpoints, privacy audits, agent steps, execution results, and Hera semantic events.
- Expanded the deterministic Agent Gateway so it creates full agent handoff envelopes while avoiding intent classification, semantic routing, tool selection, model selection, planning, and answering.
- Added the Freyja 3 agent runtime contract. The selected agent receives the raw natural-language objective, chooses permitted tools itself, selects compute capabilities, uses the inference registry only for endpoint lookup, and preserves agent identity across endpoint changes.
- Extended the Freyja 3 runtime beyond contract selection: when supplied with the existing tool registry, agents execute selected permitted tool capabilities and record tool results/audit steps. Live model calls are separately gated by `FREYJA3_INFERENCE_ENABLED`.
- Added a bounded agent-owned plan/observe/retry loop. The runtime records the agent's plan, executes selected permitted tools, observes failures, selects a permitted `system.health` diagnostic when useful, and retries failed non-mutating capabilities within a fixed iteration limit without adding semantic routing or planning to the gateway.
- Added bounded agent-owned follow-up question handling. When the selected agent chooses an under-specified mutation capability such as messaging, scheduling, or Home Assistant control, it asks for the missing target/time/device detail before executing mutation tools.
- Wired the Freyja 3 runtime to scoped memory. Agents recall permitted private/household scopes at run start, write a scoped run summary after execution, persist explicit `remember ...` user requests as scoped durable memories with basic sensitivity classification, and propose inferred fact/preference memory candidates for review instead of silently storing them.
- Added Freyja 3-native configurable inference endpoints through `FREYJA3_INFERENCE_ENDPOINTS`, including LM Studio/OpenAI-compatible local providers. The inference registry still performs capability/domain lookup only.
- Added the Privacy/Egress Gate. Cloud AI requests must be evaluated there; private/sensitive/restricted data fails closed unless an explicit one-request override is provided.
- Added a feature flag, `FREYJA3_CANONICAL_ENABLED`, for routing `/canonical/route` through the Freyja 3 gateway/runtime path while leaving legacy `/route` compatibility intact.
- Added a durable Freyja 3 semantic event store and `/events/semantic` publish/list endpoints for Hera-to-Atlas perception events. The API accepts Hera system events and denies non-Hera publishers or private-domain readers.
- Added a durable Freyja 3 scheduler store and `/freyja3/schedules` API for deterministic Atlas-owned agent trigger envelopes. Due dispatch calls the existing canonical gateway/runtime path and does not classify intent or select task tools.
- Added a durable Freyja 3 machine status store, `/freyja3/machines/heartbeat`, `/freyja3/machines`, and `freyja3-machine-heartbeat` CLI so Mars and other hosts can publish system-scoped role/health observations to Atlas.
- Added reproducible user-level systemd service/timer assets for periodic Freyja 3 machine heartbeat publishing from Atlas/Mars-style hosts.
- Added a durable Freyja 3 audit store and `/freyja3/audit` API. Canonical sidecar executions persist gateway and agent runtime audit events for household/system observability.
- Added a durable Freyja 3 worker job queue API for Mars-style background work. Atlas can store deterministic worker envelopes, workers claim jobs by machine/class under system authority, complete or fail claimed jobs, and lifecycle events are audited.
- Added a `freyja3-worker-runner` CLI plus reproducible user-level systemd service/timer assets so Mars-style hosts can poll Atlas for one queued worker job per run and complete lightweight monitoring jobs or bounded document-ingestion jobs.
- Added a concrete Freyja 3 document-ingestion worker path. It accepts explicit text or files under configured ingestion roots and returns structured untrusted external-content observations without direct memory writes, messaging, home control, admin changes, or privileged execution.
- Added Freyja 3 memory candidate review APIs. Model-assisted fact/preference candidates stay pending until an authorized owner/system reviewer approves or rejects them; approved candidates become scoped memories with candidate provenance and proposal/review audit events.
- Added a dedicated `freyja.freyja3_app` ASGI service and side-by-side compose target at `deploy/compose/freyja3`, separate from the legacy Director path.
- Added a Freyja 3 scoped memory store and `/freyja3/memory` API with explicit owner domain, scope, provenance, classification, allowed readers/writers, and hard paralegal enclave separation.
- Added Freyja 3 architecture tests covering the 12 required proof points at the contract level.
- Preserved the iMessage photo fix: HEIC/HEIF photos convert to JPEG before model calls, and routine image requests can use approved cloud vision when policy permits.

## Machine Status

| Machine | Verified State | Freyja 3 Role Status |
| --- | --- | --- |
| Iris | `iris.lan`, macOS 26.5.2, Director and iMessage connector running locally | Apple-side runtime active. MacAgent and iMessage path available. Needs Freyja 3 canonical flag rollout after more integration testing. |
| Atlas | Ubuntu 24.04 kernel line, Docker active, Home Assistant container active, Atlas Director externally healthy at Tailscale port `8001`, Signal containers active; isolated `/home/joe/freyja-os-freyja3` checkout runs `freyja3-agent-gateway-1` healthy on Tailscale port `8300` with bearer auth | Persistent infrastructure role partially active: existing Director-compatible services are preserved. Freyja 3 gateway/runtime, scoped memory API, memory candidate review API, semantic event receiver, scheduler API, worker job queue API, machine status API, and audit API are deployed side-by-side on Atlas. The sidecar verifies Vulcan inference readiness, accepts Hera semantic events, enforces private/paralegal memory boundaries, recalls/writes scoped memory during canonical execution, captures explicit `remember ...` requests as durable private memories, proposes inferred memory candidates for review, live-smoked bounded plan/observe/retry iteration after failed `git.inspect`, live-smoked deterministic scheduler due dispatch into Cloyd, live-smoked Mars-targeted worker job create/claim/complete lifecycle, live-smoked mutation follow-up questions with no fabricated tool success, stores Atlas/Mars machine-role heartbeats from active user-level timers, and persists canonical gateway/runtime audit events. HA live data/control still needs credentials wired into the sidecar. |
| Vulcan | Ubuntu kernel line, Ollama active, remote Ollama exposed on Tailscale port `11434`, models include `qwen3-coder-next:q4_K_M`, `qwen2.5:7b`, `minicpm-v`, and `nomic-embed-text`; no LM Studio/OpenAI-compatible process was found listening on common local ports during SSH inspection | Primary inference appliance partially active. General/code/vision/embedding compute available through remote Ollama. Freyja 3 can register LM Studio/OpenAI-compatible local endpoints through `FREYJA3_INFERENCE_ENDPOINTS` when one is installed/listening on Vulcan. |
| Hera | Ubuntu kernel line, Ollama active on Tailscale port `11434`, local vision-capable models present on Hera, isolated `/home/joe/freyja-os-freyja3` checkout can publish authenticated semantic events to Atlas; no `/dev/video*` visible to `joe` account | Edge inference exists. Hera can publish typed semantic events to Atlas. Real camera-backed perception publisher is not deployed because camera device access needs confirmation. |
| Mars | Ubuntu kernel line, Docker active, Freyja Director container healthy on Tailscale port `8000`, Signal containers active; isolated `/home/joe/freyja-os-freyja3` checkout runs `freyja3-agent-gateway-1` healthy on `127.0.0.1:8300`; user-level `freyja3-machine-heartbeat.timer` and `freyja3-worker-runner.timer` active | Worker/secondary host partially active. Existing Freyja services healthy; Freyja 3 sidecar is deployed on-host without touching the dirty live deploy checkout and live-smoked bounded plan/observe/retry iteration after failed `git.inspect`, deterministic scheduler due dispatch into Cloyd, mutation follow-up questions with no fabricated tool success, durable worker job API availability, periodic Mars-to-Atlas machine heartbeat publishing, and a timer-run Mars worker job claim/complete cycle against Atlas with audit. Document-ingestion worker implementation exists; live Mars ingestion proof pending. |

## Joe-Required Blockers

- Hera camera/perception hardware access is not visible from the current `joe` SSH session. Typed Hera-to-Atlas event publishing works, but real camera-backed perception needs physical/device confirmation or permission changes.
- Home Assistant API is reachable on Atlas but returns auth-required responses. The Freyja 3 Atlas sidecar selects the HA capability and reports `live_data_available=false` until a token/base URL is wired into its env without exposing secrets.
- LM Studio/OpenAI-compatible local endpoint installation on Vulcan is not currently visible from SSH. Freyja 3 registry support exists, but a listening endpoint still needs to be installed/enabled or exposed.
- Atlas `/home/joe/freyja-os` and Mars live deploy checkout have uncommitted local changes. Live deployment/rebuild should wait for reconciliation or a deliberate separate Freyja 3 service target.

## Verification Snapshot

1. Gateway selects the correct agent: covered by `tests/test_freyja3_architecture.py`.
2. Agent receives the natural-language objective: covered by agent step evidence in tests.
3. Agent independently chooses tools: covered by runtime tool-selection tests.
4. Agents use Vulcan inference remotely: repo registry points to Vulcan Tailscale Ollama; remote service and required models verified from Iris, Atlas sidecar, and Mars sidecar.
5. Multi-step autonomous tool work functions: covered by agent-owned multi-tool execution through the existing tool registry, scoped memory recall/write, explicit durable memory capture, bounded plan/observe/retry after failed tool results, and bounded follow-up questions before under-specified mutation execution.
6. Iris uses Mac Agent/Apple capabilities: MacAgent/iMessage live services are running; Freyja 3 runtime selects Apple/Mac tools in tests.
7. Freyja controls HA on Atlas: Atlas sidecar selects the HA capability and executes the HA adapter, but live data/control remains blocked by missing HA env credentials.
8. Hera publishes semantic perception events: verified from Hera to Atlas over Tailscale with bearer auth; Atlas persisted and returned a `voice_activity` event. Real camera-backed publisher pending device access.
9. Memory privacy boundaries work: covered by runtime boundary tests and Freyja 3 memory store/API tests for private, shared, paralegal, and reviewable candidate scopes. Live Atlas sidecar smoke verified Joe private memory is hidden from Beth, Beth/Benedict cannot write paralegal enclave memory, Cloyd recalls/writes scoped memory during canonical runtime execution, explicit `remember ...` requests persist as Joe-private memory, and inferred memory candidates require authorized review before becoming durable memory.
10. Cloud cannot bypass privacy controls: covered by egress gate tests.
11. Agents recover from inference outages: covered by runtime fallback test.
12. Agent identity is independent of model/host: covered by runtime endpoint-change test.

## Remaining Architecture Work

- Wire Atlas Freyja 3 sidecar to HA credentials and prove read/control against Home Assistant policy.
- Enable Freyja 3 canonical mode gradually after integration tests pass.
- Deploy the Freyja 3 semantic event receiver on Atlas and add a real Hera camera/perception publisher once devices are visible.
- Verify Home Assistant control through Freyja 3 permission policy against Atlas.
- Deploy and live-smoke the Mars document-ingestion worker path on top of the worker runner.
- Install/enable Vulcan LM Studio or another OpenAI-compatible local server if that provider type is still desired beyond Ollama.
- Commit the Freyja 3 foundation milestone after tests and remote installs are clean.
