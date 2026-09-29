# Freyja Architecture

**Status:** operational convergence target, established 2026-09-29.

This document makes the currently working deployment explicit. It is not a new
model gateway, an additional agent framework, or a replacement for Iris Core.
It consolidates the agent identities, web UI, inference path, tool boundary,
and channels around their actual owners.

## Canonical path

```text
LibreChat named agent ──direct──> Vulcan Nexus ──> local model
        │
        └──per-agent MCP token──> Iris Freyja Core ──> MacAgent / Home Assistant / OpenCode / memory

Discord, Telegram, Signal ──> Director identity and channel policy ──> same named agent identity
```

LibreChat is the operational web home for named-agent chat. Nexus owns model
selection and inference. Iris Freyja Core owns tool implementation, approval
policy, Apple integration, and tool-scoped memory. Director owns channel
identity and delivery policy; it must not become a second model-response
composer for portal chat.

## Canonical identities

| Identity | Role | Normal model class | Tool posture |
| --- | --- | --- | --- |
| Freyja | Shared household coordinator | strong local reasoning | household tools through Core policy |
| Cloyd | Joe's technical agent | strong local reasoning | technical and household tools through Core policy |
| Benedict | Deliberate research and analysis | deep local reasoning | read-oriented Core access by policy |
| Agent 47 | Software implementation specialist | local coder | bounded OpenCode lifecycle through Core |
| JennaCide | Jenna's personal agent | fast local conversation | private memory and Core-scoped access |
| Agent Smith | Freyja hardware watchdog | bounded diagnostics/coder | health, alerting, and explicitly approved maintenance only |

Agent Smith is a service identity, not a household-chat replacement. It has no
shared personal memory, no general-purpose social role, and no unrestricted
shell or home-control authority. Its alerts go to Freyja or Cloyd according to
the approved escalation policy.

## Live state

- LibreChat is live on Atlas and currently hosts Freyja, Cloyd, Benedict,
  Agent 47, and JennaCide as native profiles with isolated agent memory.
- Each of those profiles uses a distinct Iris Core MCP identity. Their
  source-controlled definition is `config/librechat-family-agents.yaml`.
- Iris Core HTTP and MCP services are live on the Tailscale network. Core owns
  the authoritative tool catalog.
- Freyja and Cloyd Discord DM connectors are active. Additional channel
  activation remains explicit and per identity.
- Agent Smith's existing OpenClaw and monitoring runtime remains a preserved
  operational lane while its Core-scoped watchdog contract is completed.

## Compatibility and retirement posture

Open WebUI, LobeHub, Msty Go, and OpenClaw remain installed compatibility or
evaluation surfaces. They are not alternate canonical homes for agent memory,
tool authority, or model routing. Do not remove a preserved service until its
replacement path has been exercised and rollback is documented.

The former single-agent acceptance stack and Hermes-parent work remain useful
experimental evidence in `archive/hermes-validation/`, but they do not define
production. Their incomplete acceptance reports must not be reported as
failures of the live LibreChat/Core path.

## Completion criteria

1. The six-identity roster is consistent in source manifests, portals, and
   channel configuration.
2. Each web agent has its intended Nexus preset, private memory scope, and
   Core identity.
3. Agent Smith has a documented read-only health check and a separately
   approved maintenance escalation path.
4. Discord uses the same canonical identities as LibreChat; Telegram or Signal
   is selected and certified before it is described as a household channel.
5. Legacy validation documents are archived or migrated without deleting their
   acceptance evidence.
