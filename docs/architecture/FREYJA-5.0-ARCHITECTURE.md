# Freyja 5.0 Architecture

Freyja 5.0 preserves the Freyja 4.1 runtime as fallback and formalizes the
architecture boundary names used by the current implementation.

## Planes

| Plane | Role | Implementation boundary |
| --- | --- | --- |
| Vulcan | Inference plane | Msty Nexus on Vulcan exposes semantic local presets and owns physical model/runtime selection. |
| Atlas | Persistent agent plane | Atlas hosts the Freyja Gateway, persistent agent runtime, memory, audit, workers, and health APIs. Msty Go may replace or wrap this plane only if it proves reliable for always-on Linux operation. |
| Iris | Apple/macOS capability server | MacAgent/MCP-style tools for Messages, Calendar, Contacts, Mail, Music, Browser, and Shortcuts. |
| Hera | Avatar/voice interface | Voice/avatar/perception edge publishes semantic events and channel input into Atlas. |
| Freyja Gateway | Deterministic ingress boundary | Authenticates, resolves household identity, applies deterministic domain/policy checks, normalizes channel payloads, traces, and forwards handoff envelopes. |

The Gateway must not become a Director. It must not accumulate agent reasoning,
arbitrary tool orchestration, or hard-coded physical model selection.

## Semantic Routes

Agents request semantic routes: `fast`, `general`, `deep`, `code`, `vision`,
`embedding`, and `private`. Nexus owns the mapping from route preset to concrete
model/runtime. Cloud fallback is never implicit; egress must be explicit and
audited by policy.

## Persistent Agents

Canonical agent configuration is kept in source control via
`src/freyja/foundation_seed.py` and summarized in
`config/freyja-5.0-agents.yaml`. Freyja, Cloyd Gibbler, Benedict, Benedict
Paralegal, Agent 44, and Jenna agent are persistent logical agents with scoped
memory/tool grants.

## MCP Topology

MCP servers run by capability location, not per logical agent. The canonical
topology is source controlled in `config/freyja-5.0-mcp-topology.yaml`.

Iris hosts the Apple/macOS MCP boundary for Browser, Calendar, Mail, Messages,
Music, and MacAgent capabilities because those APIs require a macOS session and
local Apple permissions. Atlas hosts persistent household/service MCP boundaries
for Home Assistant, scheduling, document processing, and vision inspection.
Vulcan does not host agent MCP servers by default; it remains the inference
plane behind Nexus semantic routes. Hera is a voice/avatar channel edge and
publishes semantic events into the Gateway rather than becoming a general tool
server.

Freyja, Cloyd, Benedict, Benedict Paralegal, Agent 44, and Jenna agent consume
MCP tools through scoped grants in `src/freyja/foundation_seed.py`. They do not
each run duplicated MCP servers unless a future capability requires an
agent-owned service boundary. This keeps policy, audit, and host-specific
permissions deterministic while preserving independent logical agents.

## Traceability

Important requests carry `trace_id`, channel, resolved user, authenticated
subject, actor principal, memory scopes, agent, requested semantic route, actual
endpoint/provider/model/runtime when available, selected tools, tool calls,
delegation, failures, fallbacks, machine, latency, inference status, and egress
state through `AgentExecutionResult.trace_summary` and audit events.

The canonical trace fields are source controlled in
`config/freyja-5.0-traceability.yaml`: `trace_id`, `channel`,
`resolved_user`, `authenticated_subject`, `actor_principal`, `memory_scopes`,
`agent`, `requested_route`, `actual_endpoint`, `actual_provider`,
`actual_model`, `actual_runtime`, `selected_tools`, `tool_calls`,
`delegation`, `machine`, `latency_ms`, `failures`, `fallbacks`,
`inference_status`, and `egress_state`.

## Certification Targets

A through G are tracked in `docs/FREYJA-5.0-STATUS.md`. Missing live credentials,
Msty Go validation, and physical-service work are recorded in
`FREYJA-5.0-BLOCKERS.md` without blocking independent source work.
