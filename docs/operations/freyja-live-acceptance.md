# Freyja Live Acceptance Record

This record distinguishes live evidence from configuration-only evidence. It
is safe to update without recording credentials or private conversation data.

Run `python3 scripts/freyja-live-readiness.py` before an acceptance pass. It
checks the same no-secret network baseline recorded below, including the
expected protected Nexus response.

Follow `docs/operations/librechat-acceptance-runbook.md` for the exact
no-write agent and tool checks. It separates those safe checks from the
operator-approved durable-memory isolation test.

## Verified on 2026-09-29

| Capability | Evidence | Result |
| --- | --- | --- |
| Atlas portals | HTTP 200 from LibreChat (`:3080`), Open WebUI (`:3001`), LobeHub (`:3210`), and family page (`:9091`) | reachable |
| Family-page operational links | On 2026-09-29, every visible portal link returned HTTP 200: LibreChat, Open WebUI, LobeHub, Nextcloud, Home Assistant, Paperless, Director docs, Iris Core docs, Agent Smith, and the versioned Ops Manual. | verified; only working targets are displayed |
| Vulcan model runtime | Ollama API answered at `:11434`; Nexus answered with expected authorization required at `:3939/v1/models` | reachable and protected |
| Named-agent inference | On 2026-09-29, all five deployed Nexus presets returned visible written replies with the 1,024-token agent output budget. Freyja, Cloyd, Benedict, and Agent 47 resolved to `qwen3.8:27b`; JennaCide resolved to `gpt-oss:20b`. | healthy |
| Director | `GET http://100.94.80.21:8512/health` returned healthy; `freyja-paralegal-director.service` is active as a user service | healthy |
| Canonical Home Assistant read | On 2026-09-29, a canonical Freyja request for current light states was read through Iris Core and returned 29 Atlanta light entities with `source=home_assistant` and `live_data_available=true`. No control action was issued. | certified read-only |
| Iris Core | `GET http://100.115.228.56:8510/health` returned healthy; Core launch agent is running | healthy |
| Core MCP | LibreChat starts five per-agent Core MCP connections. The published catalog contains named Core tools; authorization is determined by the authenticated agent token, not the portal. Freyja includes read-only `home_assistant.read_state` and `home_assistant.list_states`. | initialized |
| Named web-agent configuration | LibreChat startup log loaded Freyja, Cloyd, Benedict, Agent 47, and Jenna MCP identities with their Nexus presets | configured |
| Discord Freyja | Iris launch agent is running and authenticated. On 2026-09-29, its canonical Director route completed a live Home Assistant read through Iris Core; the pre-fix fixture fallback has been removed from this live path. | certified read-only path |
| Discord Cloyd | On 2026-09-29, Cloyd's live Discord DM returned the scoped Iris Core `opencode.status` fields: alias, session, idle state, working directory, and recent action. The connector is routed through Vulcan's canonical Director. | certified |
| Agent Smith monitor | Iris monitor status and runtime-health APIs answered at `:8000/agent-runs/api/*`. A controlled Discord delivery test to Joe through Cloyd Bot was accepted; the test stated that no repair was attempted. On 2026-09-29, the active observe-only shepherd was updated to detect only a known-healthy→critical transition, send no startup/repeat alert, and never repair a service. Its dedicated alert credential is not provisioned, so automatic delivery remains dormant. | bounded workflow certified; delivery provisioning pending |
| Telegram | Operator-disabled on 2026-09-29: private enablement flags were turned off and the Iris launch agent was unloaded. | disabled, not certified |
| Signal | Signal API and connector containers are healthy, but on 2026-09-29 the connector receive loop was repeatedly rejected by the Signal API with HTTP 400. | not operational |

### Current Nexus resolutions

These are observed live resolutions, not a recommendation to change routes:

| LibreChat profile(s) | Nexus preset | Current physical model |
| --- | --- | --- |
| Freyja, Cloyd | `@preset/freyja-strong-local` | `qwen3.8:27b` |
| Benedict | `@preset/benedict-paralegal-local` | `qwen3.8:27b` |
| Agent 47 | `@preset/freyja-coder` | `qwen3.8:27b` |
| JennaCide | `@preset/freyja-fast-local` | `gpt-oss:20b` |

The intended alternate deep, coding, and vision models remain installed on
Vulcan. Their selection remains the responsibility of Nexus and has not been
changed in this acceptance pass.

## Interactive acceptance results

These checks cannot be truthfully certified by an unauthenticated HTTP probe.
They were run in LibreChat using an approved local account; this record retains
only the result, agent, and date—not private chat content or secrets.

| Agent | Plain written reply | MCP read-only call | Memory isolation check | Outcome |
| --- | --- | --- | --- | --- |
| Freyja | On 2026-09-29, LibreChat returned the current Atlanta light inventory | On 2026-09-29, scoped `home_assistant.list_states` returned 29 live entities with no control or memory write. Core now returns authoritative `state_counts` alongside entities to prevent prose-count drift. | Core protocol memory isolation verified | LibreChat written and Core MCP read-only acceptance certified |
| Cloyd | On 2026-09-29, LibreChat returned an OpenCode status response | On 2026-09-29, scoped `opencode.status` returned alias `freyja-core-coder`, state `idle`, and working directory `/Users/freyja/freyja-os`; no mutation requested | Core protocol memory isolation verified | LibreChat written and Core MCP read-only acceptance certified |
| Benedict | On 2026-09-29, LibreChat returned a scoped Core status response | On 2026-09-29, used scoped `status.check` to report `freyja-core`, `iris.lan`, healthy; no mutation requested | Core protocol memory isolation verified | LibreChat written and Core MCP read-only acceptance certified |
| Agent 47 | On 2026-09-29, LibreChat returned a scoped OpenCode status response | On 2026-09-29, scoped `opencode.status` returned alias `freyja-core-coder`, state `idle`, and working directory `/Users/freyja/freyja-os`; no mutation requested | Core protocol memory isolation verified | LibreChat written and bounded OpenCode handoff acceptance certified |
| JennaCide | On 2026-09-29, returned exact `JennaCide LibreChat written-response check.` | On 2026-09-29, used scoped `status.check` to report `freyja-core`, `iris.lan`, healthy; no mutation requested | Core protocol memory isolation verified | LibreChat written and Core MCP read-only acceptance certified |

On 2026-09-29, each authenticated Iris Core MCP route wrote a temporary
caller-owned marker, read it as its owner, was unable to read each of the other
four markers, deleted its own marker, and confirmed it was absent. The test
left no marker records behind. This is protocol-level isolation evidence; it
does not substitute for the remaining portal acceptance rows.

For Agent 47, add one bounded OpenCode handoff check after the plain and
read-only checks: request a non-destructive status or repository inspection,
confirm the output is written and attributable to Agent 47, then confirm no
unapproved filesystem change occurred.

## Gate for production-baseline merge

Every named-agent row now has a recorded interactive result, and Agent Smith's
observe-only alert route has a controlled delivery test. The separate
production-baseline gate remains open for the documented full-suite
disposition and explicit operator merge approval; portal reachability and MCP
initialization alone are not a merge authorization.
