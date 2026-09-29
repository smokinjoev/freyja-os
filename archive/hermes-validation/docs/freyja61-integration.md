# Freyja 6.1 Integration Runbook

## Purpose

Freyja 6.1 adds Hermes-based Discord coordination on Iris without replacing
Msty Go, Freyja 5, Open WebUI, Nexus, Vulcan, MacAgent, or OpenCode.
Open WebUI, OpenCode, and OpenCodex are canonical installed surfaces and must
remain present and functioning during 6.x work.

## Operating Model

```text
Discord -> Hermes Freyja parent -> private child roles -> Freyja Core
                                                     -> MacAgent / Home Assistant / OpenCode
Hermes model calls -> Iris LiteLLM -> Vulcan Ollama
Msty Go named agents -> Nexus -> Vulcan Ollama
Open WebUI / OpenCode / OpenCodex -> Vulcan OpenAI-compatible endpoint or Nexus preset
```

The parent is the sole Discord speaker. `research`, `household`, and `coding`
are private, flat Hermes child roles. They return summaries to the parent; they
do not own Discord identities, raw credentials, or durable-memory write access.

## Canonical Boundaries

- `config/freyja61/endpoint-registry.yaml` is the canonical endpoint registry.
- Freyja Core is the only Hermes tool transport. Hermes does not call MacAgent,
  Home Assistant, OpenCode, or the Msty Go database directly.
- Msty Go remains authoritative for its existing named-agent workspaces and
  `freyja5-shared-household` memory pack.
- Open WebUI, OpenCode, and OpenCodex may point straight to Vulcan for model
  inference, but they do not replace Freyja Core, Atlas Director policy, or
  approved memory/tool boundaries.
- Hermes retains only parent/session-private memory. Core stores explicit,
  authorized cross-runtime household facts.

## Activation Order

1. Run the static integration audit and the single-tool LiteLLM probe.
2. Enable the read-only Core tool stage for the parent only.
3. Verify a Discord round trip for each enabled capability.
4. Enable calendar writes only after MacAgent authentication and explicit
   confirmation behavior are verified.
5. Enable Home Assistant reads, then the bounded OpenCode lifecycle.

No later stage is enabled merely because an endpoint is healthy.

## Current Compatibility Gate

The pinned local model returns a valid native OpenAI tool call when tool choice
is forced through LiteLLM. Hermes's automatic tool-selection loop currently
receives a textual JSON representation of the same call instead of a native
tool-call response. Keep Discord on the no-tool profile until that adapter
behavior is corrected and the parent completes a real Core tool round trip.

The Core MCP bridge itself is ready for Hermes containers. Its loopback-only
listener accepts Docker Desktop's `host.docker.internal` alias internally; this
does not create a public listener.

## Verification

```bash
.venv/bin/python scripts/freyja61-integration-audit.py
.venv/bin/python -m pytest -q tests/test_freyja61_integration.py tests/test_freyja6_core_tools.py tests/test_mcp_gateway.py
```

For the live parent rollout, retain the existing `freyja-test` container and
channel. Record the LiteLLM tool-call result, a Core policy check, and a Discord
round trip before changing `tool-activation.yaml` from its disabled default.

## Rollback

Keep the 6.0 `freyja-test` profile, channel, image, LiteLLM route, and Core
token mapping intact. To roll back, disable the 6.1 tool profile and restart
Hermes. Do not stop or modify Msty Go, Nexus, Vulcan, Open WebUI, Freyja 5, or
the Msty Go database.

## Deferred Work

The future Msty Go-to-Core memory bridge is read-only design work only. It must
have stable IDs, provenance, authorization, deduplication, backups, and a
rollback plan before activation. Named household-agent migration and additional
Discord bots are outside Freyja 6.1.

## Discord Parent Remediation Record — 2026-09-21

The Discord parent is deliberately configured as a final-only profile while normal conversation is certified:

- platform_toolsets.discord is [no_mcp]; an empty list is insufficient because Hermes otherwise restores globally enabled MCP servers.
- Gateway streaming, Discord streaming, and tool-progress delivery are explicitly disabled.
- The dedicated Discord session was cleared before validation; only that freyja-test channel state was changed.
- The live selected alias is vulcan-fast through Iris LiteLLM. A direct non-streaming LiteLLM probe returned one plain-English sentence with finish_reason stop and the requested model alias.
- No Discord acceptance claim is recorded until the actual user-authored prompt and its bot reply are verified through the Discord API.

Controlled validation is one normal question from the existing allowlisted user in the dedicated channel, followed by Discord API verification of exactly one bot reply referencing that prompt. Do not enable any Core tool stage before that evidence exists. For rollback, restore discord: [no_mcp], retain the explicit streaming-off settings, clear only the dedicated test session, and restart freyja6-hermes-freyja-test-1.
