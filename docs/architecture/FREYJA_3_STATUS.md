# Freyja 3.0 Status

Last updated: 2026-08-26.

## Completed Repo Work

- Added Freyja 3 canonical models for security domains, persistent agents, machine roles, tool grants, gateway handoffs, inference endpoints, privacy audits, agent steps, execution results, and Hera semantic events.
- Expanded the deterministic Agent Gateway so it creates full agent handoff envelopes while avoiding intent classification, semantic routing, tool selection, model selection, planning, and answering.
- Added the Freyja 3 agent runtime contract. The selected agent receives the raw natural-language objective, chooses permitted tools itself, selects compute capabilities, uses the inference registry only for endpoint lookup, and preserves agent identity across endpoint changes.
- Extended the Freyja 3 runtime beyond contract selection: when supplied with the existing tool registry, agents execute selected permitted tool capabilities and record tool results/audit steps. Live model calls are separately gated by `FREYJA3_INFERENCE_ENABLED`.
- Added the Privacy/Egress Gate. Cloud AI requests must be evaluated there; private/sensitive/restricted data fails closed unless an explicit one-request override is provided.
- Added a feature flag, `FREYJA3_CANONICAL_ENABLED`, for routing `/canonical/route` through the Freyja 3 gateway/runtime path while leaving legacy `/route` compatibility intact.
- Added a durable Freyja 3 semantic event store and `/events/semantic` publish/list endpoints for Hera-to-Atlas perception events. The API accepts Hera system events and denies non-Hera publishers or private-domain readers.
- Added a dedicated `freyja.freyja3_app` ASGI service and side-by-side compose target at `deploy/compose/freyja3`, separate from the legacy Director path.
- Added a Freyja 3 scoped memory store and `/freyja3/memory` API with explicit owner domain, scope, provenance, classification, allowed readers/writers, and hard paralegal enclave separation.
- Added Freyja 3 architecture tests covering the 12 required proof points at the contract level.
- Preserved the iMessage photo fix: HEIC/HEIF photos convert to JPEG before model calls, and routine image requests can use approved cloud vision when policy permits.

## Machine Status

| Machine | Verified State | Freyja 3 Role Status |
| --- | --- | --- |
| Iris | `iris.lan`, macOS 26.5.2, Director and iMessage connector running locally | Apple-side runtime active. MacAgent and iMessage path available. Needs Freyja 3 canonical flag rollout after more integration testing. |
| Atlas | Ubuntu 24.04 kernel line, Docker active, Home Assistant container active, Atlas Director externally healthy at Tailscale port `8001`, Signal containers active; isolated `/home/joe/freyja-os-freyja3` checkout runs `freyja3-agent-gateway-1` healthy on Tailscale port `8300` with bearer auth | Persistent infrastructure role partially active: existing Director-compatible services are preserved. Freyja 3 gateway/runtime and semantic event receiver are deployed side-by-side on Atlas, verify Vulcan inference readiness, and accept Hera semantic events. HA live data/control still needs credentials wired into the sidecar. |
| Vulcan | Ubuntu kernel line, Ollama active, remote Ollama exposed on Tailscale port `11434`, models include `qwen3-coder-next:q4_K_M`, `qwen2.5:7b`, `minicpm-v`, and `nomic-embed-text` | Primary inference appliance partially active. General/code/vision/embedding compute available through remote Ollama. LM Studio/OpenAI-compatible endpoint still unverified. |
| Hera | Ubuntu kernel line, Ollama active on Tailscale port `11434`, local vision-capable models present on Hera, isolated `/home/joe/freyja-os-freyja3` checkout can publish authenticated semantic events to Atlas; no `/dev/video*` visible to `joe` account | Edge inference exists. Hera can publish typed semantic events to Atlas. Real camera-backed perception publisher is not deployed because camera device access needs confirmation. |
| Mars | Ubuntu kernel line, Docker active, Freyja Director container healthy on Tailscale port `8000`, Signal containers active; isolated `/home/joe/freyja-os-freyja3` checkout runs `freyja3-agent-gateway-1` healthy on `127.0.0.1:8300` | Worker/secondary host partially active. Existing Freyja services healthy; Freyja 3 sidecar is deployed on-host without touching the dirty live deploy checkout. Worker jobs/monitoring still need deployment. |

## Joe-Required Blockers

- Hera camera/perception hardware access is not visible from the current `joe` SSH session. Typed Hera-to-Atlas event publishing works, but real camera-backed perception needs physical/device confirmation or permission changes.
- Home Assistant API is reachable on Atlas but returns auth-required responses. The Freyja 3 Atlas sidecar selects the HA capability and reports `live_data_available=false` until a token/base URL is wired into its env without exposing secrets.
- LM Studio/OpenAI-compatible local endpoints on Vulcan are not yet verified.
- Atlas `/home/joe/freyja-os` and Mars live deploy checkout have uncommitted local changes. Live deployment/rebuild should wait for reconciliation or a deliberate separate Freyja 3 service target.

## Verification Snapshot

1. Gateway selects the correct agent: covered by `tests/test_freyja3_architecture.py`.
2. Agent receives the natural-language objective: covered by agent step evidence in tests.
3. Agent independently chooses tools: covered by runtime tool-selection tests.
4. Agents use Vulcan inference remotely: repo registry points to Vulcan Tailscale Ollama; remote service and required models verified from Iris, Atlas sidecar, and Mars sidecar.
5. Multi-step autonomous tool work functions: covered by agent-owned multi-tool execution through the existing tool registry; deeper iterative plan/observe/retry behavior still needs integration.
6. Iris uses Mac Agent/Apple capabilities: MacAgent/iMessage live services are running; Freyja 3 runtime selects Apple/Mac tools in tests.
7. Freyja controls HA on Atlas: Atlas sidecar selects the HA capability and executes the HA adapter, but live data/control remains blocked by missing HA env credentials.
8. Hera publishes semantic perception events: verified from Hera to Atlas over Tailscale with bearer auth; Atlas persisted and returned a `voice_activity` event. Real camera-backed publisher pending device access.
9. Memory privacy boundaries work: covered by runtime boundary tests and Freyja 3 memory store/API tests for private, shared, and paralegal scopes.
10. Cloud cannot bypass privacy controls: covered by egress gate tests.
11. Agents recover from inference outages: covered by runtime fallback test.
12. Agent identity is independent of model/host: covered by runtime endpoint-change test.

## Remaining Architecture Work

- Extend the first asynchronous tool loop into a full iterative plan/observe/retry loop with memory writes and follow-up question handling.
- Wire Atlas Freyja 3 sidecar to HA credentials and prove read/control against Home Assistant policy.
- Connect the Freyja 3 agent runtime to scoped memory writes/recall as part of the iterative loop.
- Enable Freyja 3 canonical mode gradually after integration tests pass.
- Deploy the Freyja 3 semantic event receiver on Atlas and add a real Hera camera/perception publisher once devices are visible.
- Verify Home Assistant control through Freyja 3 permission policy against Atlas.
- Verify Vulcan LM Studio/OpenAI-compatible service or document it as not installed.
- Commit the Freyja 3 foundation milestone after tests and remote installs are clean.
