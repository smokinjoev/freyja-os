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
| Vulcan model runtime | Ollama API answered at `:11434`; Nexus answered with expected authorization required at `:3939/v1/models` | reachable and protected |
| Named-agent inference | Each deployed Nexus preset returned a written reply with a 1,024-token agent output budget | healthy |
| Director | `GET http://100.94.80.21:8512/health` returned healthy; `freyja-paralegal-director.service` is active as a user service | healthy |
| Iris Core | `GET http://100.115.228.56:8510/health` returned healthy; Core launch agent is running | healthy |
| Core MCP | LibreChat starts five per-agent Core MCP connections. The published catalog contains named Core tools; authorization is determined by the authenticated agent token, not the portal. Freyja includes read-only `home_assistant.read_state` and `home_assistant.list_states`. | initialized |
| Named web-agent configuration | LibreChat startup log loaded Freyja, Cloyd, Benedict, Agent 47, and Jenna MCP identities with their Nexus presets | configured |
| Discord Freyja | Iris launch agent is running; connector log reports it ready and authenticated | connected |
| Discord Cloyd | Iris connector is ready and authenticated. Director's read-only `opencode.status` now passes through Cloyd's scoped Iris Core route; awaiting one live Discord reply for certification. | connected, certification pending |
| Agent Smith monitor | Iris monitor status and runtime-health APIs answered at `:8000/agent-runs/api/*` | reachable, no alert route certified |
| Telegram | No live Telegram connector container was found on Atlas | not activated |
| Signal | Signal API and connector containers are healthy, but the connector's receive loop is repeatedly rejected by the Signal API | not operational |

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

## Still requiring an interactive acceptance pass

The following cannot be truthfully certified by an unauthenticated HTTP probe.
Run them in LibreChat using an approved local account and record only the
result, agent, and timestamp—not chat content or secrets.

| Agent | Plain written reply | MCP read-only call | Memory isolation check | Outcome |
| --- | --- | --- | --- | --- |
| Freyja | pending | pending | pending | pending |
| Cloyd | pending | pending | pending | pending |
| Benedict | pending | pending | pending | pending |
| Agent 47 | pending | pending | pending | pending |
| JennaCide | pending | pending | pending | pending |

For Agent 47, add one bounded OpenCode handoff check after the plain and
read-only checks: request a non-destructive status or repository inspection,
confirm the output is written and attributable to Agent 47, then confirm no
unapproved filesystem change occurred.

## Gate for production-baseline merge

The branch is eligible only when every row above has a recorded interactive
result and Agent Smith's watchdog check has a tested alert route. Portal
reachability and MCP initialization alone are necessary but not sufficient.
