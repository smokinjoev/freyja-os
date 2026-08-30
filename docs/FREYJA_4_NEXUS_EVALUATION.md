# Freyja 4.0 Msty Nexus Evaluation

Last updated: 2026-08-30.

## Question

Can Msty Nexus become the Freyja 4.0 model gateway between Freyja/Iris/Atlas and
Vulcan without taking over Freyja identity, privacy, tools, memory, channels, or
response authority?

## What Nexus May Replace

Nexus may replace or consolidate Freyja's model-provider plumbing:

- model catalog and model IDs
- provider keys and local/cloud runtime definitions
- local runtime start/stop and residency management
- OpenAI-compatible endpoint exposed to Freyja
- route/preset mapping for model classes
- app/API tokens for the model gateway
- model usage and gateway-level telemetry
- provider failover within policy-approved boundaries

Nexus may reduce direct Freyja integration with per-provider APIs such as
Ollama, LM Studio, and OpenRouter, provided Freyja still controls whether a
request is allowed to reach a given route.

## What Freyja Keeps

Freyja keeps:

- identity and personality
- family/personal agent registry
- privacy classification and egress policy
- channel adapters and canonical routing
- response wrapping
- tool grants and authorization
- memory stores and memory boundaries
- Home Assistant, calendar, iMessage, Signal, Gmail, MacAgent, and Apple service
  integration
- paralegal enclave separation
- audit events and safety behavior
- deterministic gateway behavior

Nexus must not become a Director or hidden agent.

## Required Flow

```text
channel adapter
  -> Freyja dispatcher
  -> privacy gate
  -> Nexus preset/route
  -> model
  -> Freyja wrapper
  -> channel adapter
```

The privacy gate must run before Nexus receives the prompt. Freyja must choose a
logical route/preset from policy and agent context, not from untrusted Nexus
side effects.

## Proposed Presets

| Preset | Intended Use | Locality |
| --- | --- | --- |
| `freyja-fast-local` | low-latency household chat/reflex work | local |
| `freyja-strong-local` | heavier private household reasoning | local |
| `freyja-coder` | Cloyd/code tasks | local |
| `freyja-vision-docs` | image and document understanding | local preferred |
| `freyja-private-local` | private/sensitive household prompts | local only |
| `benedict-paralegal-local` | Beth paralegal enclave work | local enclave only |
| `freyja-cloud-research` | approved public/cloud research | cloud after egress gate |

## Pass Criteria

- Nexus is installed from an official Msty Linux distribution path or is already
  installed on Vulcan.
- Nexus exposes an OpenAI-compatible API or equivalent stable API usable from
  Freyja.
- Freyja can list models/presets through Nexus without committing secrets.
- Freyja can complete a normal chat request through a Nexus route on Vulcan.
- From Iris, Freyja can reach Nexus on Vulcan over Tailscale/LAN and receive a
  correct response from the intended model.
- Bad token and bad model failures are explicit and do not silently fall back to
  cloud.
- Private/local and paralegal presets cannot egress to cloud.
- Existing provider behavior remains available or has a documented rollback.

## Fail Criteria

- Nexus requires Freyja prompts or private data to transit a cloud service for
  local inference.
- Nexus cannot expose a stable local API reachable from Iris/Atlas.
- Nexus cannot run or route local Vulcan models reliably.
- Nexus token behavior cannot be made non-secret in repo config.
- Nexus route/preset behavior bypasses Freyja's Privacy/Egress Gate.
- Nexus cannot produce clear bad-token/bad-model errors.
- Integration would require replacing Freyja's agent, tool, memory, or channel
  authority.

## Test Artifacts

Record runtime evidence in `docs/FREYJA_4_NEXUS_TEST_RESULTS.md` and the final
adoption decision in `docs/FREYJA_4_NEXUS_DECISION.md`.
