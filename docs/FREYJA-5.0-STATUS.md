# Freyja 5.0 Status

## Complete

- Created a recoverable Freyja 4.1 baseline tag before migration work.
- Added source-controlled Freyja 5.0 architecture documentation.
- Added source-controlled canonical summaries for persistent agents and semantic
  Nexus routes.
- Added source-controlled MCP topology for Iris, Atlas, Vulcan, Hera, and
  logical-agent MCP consumption boundaries.
- Added semantic route selection for `fast`, `general`, `deep`, `code`,
  `vision`, `embedding`, and `private`.
- Extended runtime results with requested route, provider, egress state, and
  trace summary fields.
- Added `routing/freyja5_architecture` certification suite coverage for target
  cases A-G.

## Partial

- A. Gateway to Freyja to agent runtime to Nexus/Vulcan is covered by unit tests
  and existing Nexus provider tests; live Vulcan validation still depends on
  Joe's local Nexus token and service state.
- B. Freyja to Cloyd delegation is represented by persistent agent routing,
  coding lane contracts, and Freyja 5 certification trace evidence through
  `AgentGateway` and `AgentRuntimeV3`. Live model/tool delegation remains
  incremental after Nexus and service sessions are validated.
- C. Iris Calendar is represented by MCP-style tool grants and MacAgent
  adapters; live Apple Calendar certification must run on Iris.
- D. Image/PDF media path selects the `vision` semantic route and preserves
  document/image extraction code.
- E. Multi-channel identity maps into stable domain principals through gateway
  handoff metadata. Freyja 5 certification now summarizes same-user,
  authenticated-subject, actor-principal, and memory-policy evidence across
  channels.
- F. Benedict Paralegal selects the `private` route and local-only egress policy.
  Freyja 5 certification now records explicit enclave evidence for owner,
  security domain, private/shared memory scopes, private route, local Nexus
  endpoint, Vulcan runtime, and absence of unauthorized egress.
- G. Optional service disablement is covered by endpoint health fallback tests.
  Freyja 5 certification now records explicit service-degradation evidence for
  disabled optional-service fixtures and verifies unrelated local-only response
  paths remain operational.

## Blocked

See root-level `FREYJA-5.0-BLOCKERS.md` for Joe-required validation and
physical/session tasks.

## Latest Certification Attempt

- Command:
  `.venv/bin/freyja-certify routing/freyja5_architecture --output-dir certification/reports`
- Report:
  `certification/reports/20260831T202132Z0000-freyja5-architecture.md`
- Result: failed, 14.3% overall, 1/7 cases passed.
- Passed: C. Iris Calendar tool returned one live calendar event.
- Main failure mode: the existing certification provider still exercises the
  legacy Director/router path for this suite, so Freyja 5.0 Gateway/AgentRuntime
  trace assertions are not yet first-class certification evidence. Additional
  failures also depend on unavailable local/cloud model providers during the run.
- Follow-up implementation added a `freyja5` certification provider so the suite
  can exercise `AgentGateway` and `AgentRuntimeV3` directly without live model
  calls.
- Latest direct skeleton certification:
  `.venv/bin/freyja-certify routing/freyja5_architecture --provider freyja5 --output-dir certification/reports`
  passed 100.0% with latest report
  `certification/reports/20260901T025720Z0000-freyja5-architecture.md`.
- Latest local side-by-side smoke:
  `scripts/freyja5-smoke.py --base-url http://127.0.0.1:8500 --token test-connector-token --output certification/reports/freyja5-smoke-local.json`
  passed after starting a temporary `uvicorn freyja.main:app` service on port
  `8500` with live inference disabled. Checks covered `/health`,
  `/freyja5/readiness`, `/v1/models`, text chat, inline image routing, and
  inline PDF routing. The temporary service was stopped afterward.
- Latest Freyja 5 readiness bundle:
  `scripts/freyja5-readiness-bundle.py --certification-report certification/reports/20260901T025720Z0000-freyja5-architecture.json --smoke-report certification/reports/freyja5-smoke-local.json --output certification/reports/freyja5-readiness-bundle-local.json`
  returned exit code `2`: source certification and side-by-side smoke passed,
  and only Joe-required live blockers remain.
- Runtime trace summaries now include channel, resolved user, authenticated
  subject, actor principal, memory scopes, agent, requested route, actual
  endpoint/provider/model/runtime, selected tools, tool calls, delegation
  evidence, machine, latency, failures, fallbacks, inference status, and egress
  state.
- Freyja 5 important-request traceability is now canonicalized in
  `config/freyja-5.0-traceability.yaml` and surfaced through readiness and
  certification evidence.
- Gateway handoff audit events now carry channel, message ID, source/target
  domains, authenticated subject, actor principal, memory scopes, and handoff ID
  so important requests are traceable from ingress before agent runtime starts.
- Privacy egress audit events now record destination provider, classification,
  redaction status, and a bounded redacted prompt preview so explicit cloud
  decisions and denied local-only paths remain auditable without leaking raw
  secrets.
- Freyja 5 runtime trace summaries include privacy egress decision evidence
  when fallback evaluation occurs, including denied cloud attempts with redacted
  prompt previews.
- Freyja 5 certification reports now include a compact audit chain from Gateway
  handoff creation through runtime events so important requests can be followed
  from ingress to response evidence.
- Source-controlled Freyja 5.0 agent and route summaries are covered by drift
  tests against `foundation_seed.py`.
- Freyja 5.0 certification/runtime mode disables implicit cloud fallback while
  preserving the legacy 4.1 policy-gated fallback path for compatibility.
- MCP-preferred tool boundaries are explicit in source tool grants and runtime
  traces record each selected tool's protocol, machine affinity, and mutation
  status.
- Freyja 5 certification reports now include compact per-case tool-boundary
  evidence for selected tools, tool calls, protocols, MCP host affinity, MCP
  counts, and mutation-tool presence. Target B currently proves Cloyd
  delegation through internal read tooling while live MCP delegation remains
  listed under the `live_tool_sessions` blocker.
- MCP servers are assigned by capability host, not duplicated per agent: Iris
  owns Apple/macOS MCP capabilities, Atlas owns household/service MCP
  capabilities, Vulcan remains Nexus inference, and agents consume MCP through
  source-controlled scoped grants.
- Added an opt-in OpenAI-compatible `freyja-5` model path that exercises
  Gateway identity/channel handling and `AgentRuntimeV3` route/trace selection
  without live inference, while preserving the existing Open WebUI model-proxy
  default and `agent-smith` compatibility path.
- The opt-in OpenAI-compatible `freyja-5` response metadata now exposes the
  Gateway/runtime trace ID directly as `freyja.trace_id`, matching the nested
  trace summary for easier WebGUI inspection of important requests.
- Added default-off `FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED` so the opt-in
  `freyja-5` OpenAI-compatible path can use live local Nexus inference only
  when explicitly enabled. Cloud fallback remains disabled on that path.
- Live Nexus inference readiness now comes from a shared helper that reports
  explicit enablement, configured Nexus URL/API-key presence, disabled cloud
  fallback, and readiness without exposing secrets.
- Freyja 5 certification reports include source-controlled MCP topology
  evidence: default per-agent MCP servers are disabled, MCP hosts are Atlas and
  Iris, and Vulcan remains the OpenAI-compatible Nexus inference boundary.
- `/freyja5/readiness` now exposes persistent logical-agent posture from source
  control: display/logical names, owners, security domains, Atlas home
  placement, private/shared memory scopes, tool grant counts, and cloud egress
  policy, including Benedict Paralegal's local-only enclave policy.
- Persistent logical-agent readiness and certification evidence now share a
  single canonical helper, with drift tests against `config/freyja-5.0-agents.yaml`
  and `src/freyja/foundation_seed.py`.
- Freyja 5 certification evidence now includes persistent logical-agent posture
  so generated A-G reports prove the canonical agent definitions, Agent 44/Jenna
  display names, and Benedict Paralegal enclave policy from source control.
- Added a side-by-side Freyja 5 compose target at `deploy/compose/freyja5` for
  Atlas testing on port `8500`. It preserves existing 4.1/Freyja3/Open WebUI
  deployments and keeps live inference/cloud egress disabled by default.
- Added `scripts/freyja5-smoke.py`, a read-only side-by-side Gateway smoke
  operator that checks health, readiness, OpenAI-compatible model listing,
  text chat, inline image routing, and inline PDF routing, then writes a
  sanitized JSON report without exposing the connector token. The readiness
  check now records bounded WebGUI posture, MCP hosts/server IDs, persistent
  logical-agent MCP grant counts, and A-G certification target IDs so smoke
  artifacts prove the main Freyja 5 architecture boundaries without carrying
  secrets.
- Added `scripts/freyja5-readiness-bundle.py`, which assembles Freyja 5 direct
  architecture certification plus side-by-side Gateway smoke evidence and
  reports remaining Joe-required live blockers as a distinct live-blocked
  state.
- Added `scripts/freyja5-preflight-status.py`, which summarizes the latest
  Freyja 5 readiness bundle and returns exit code `2` for the expected
  source-ready/live-blocked state. The readiness bundle and preflight summary
  now include Joe blocker component and required-evidence details directly in
  the generated output.
- Joe-required blocker metadata now includes source-controlled `next_actions`
  for Atlas/Msty Go, Vulcan/Nexus, Iris, Hera, live MCP delegation, and Benedict
  private-route validation. The readiness bundle and preflight summary surface
  those operator actions alongside required evidence.
- MCP topology evidence now exposes the concrete capability-server records:
  Iris hosts Apple/macOS MCP, Atlas hosts household-service MCP and media/vision
  MCP, and all persistent agents consume those servers through scoped tool
  grants rather than per-agent duplicated MCP servers. The compact
  `/freyja5/readiness` MCP view now includes those server records directly.
- The source-controlled Freyja 5 agent summary now lists each persistent
  logical agent's MCP tool grants and tests them against the runtime seed, so
  other-agent MCP access remains explicit without creating per-agent servers.
- Certification target posture now has a source-controlled A-G matrix in
  `config/freyja-5.0-certification-targets.yaml`; readiness and certification
  evidence expose each target's case, operator-facing name, skeleton status,
  proof points, and live blocker IDs. Freyja 5 certification reports persist
  the same matrix under `freyja5_certification` case evidence.
- The Freyja 5 readiness bundle now requires persisted target-matrix evidence
  before accepting a certification report as source-ready, preventing stale
  legacy-shaped reports from satisfying the current gate.
- The readiness bundle also requires persisted Freyja 5 trace summary fields
  before accepting certification evidence as source-ready, so important-request
  observability remains part of the certification gate.
- The readiness bundle now also requires the smoke report's readiness check to
  include WebGUI default/opt-in posture, MCP host/server IDs, persistent
  logical-agent MCP grant counts, and A-G target IDs before accepting
  side-by-side smoke evidence as source-ready.
- Added `GET /freyja5/readiness` for source-controlled architecture posture:
  semantic routes, persistent agents, MCP host placement, Vulcan boundary, and
  explicit live-local Nexus readiness without exposing secrets.
- The readiness `ok` gate now comes from shared Freyja 5 evidence and requires
  both semantic routes and MCP hosts, leaving the API endpoint as a composition
  layer instead of a YAML parser.
- `/freyja5/readiness` reports A-G certification skeleton coverage and explicit
  Joe-required live blockers for Msty Go/Atlas, Vulcan/Nexus, Iris, and Hera.
- A-G certification target posture is now exposed through a shared canonical
  helper backed by `certification/suites/routing/freyja5_architecture.yaml` and
  `config/freyja-5.0-live-blockers.yaml`, while readiness preserves its compact
  public payload shape.
- `/freyja5/readiness` now consumes a shared compact certification view so the
  API and certification helper expose the same A-G target/blocker posture.
- `/freyja5/readiness` now exposes all Joe-required blockers in a
  machine-readable form, including Msty Go always-on Linux validation, Vulcan
  local-only Nexus presets, Iris Apple session validation, and Hera
  voice/avatar hardware validation. The payload records that secrets must stay
  out of source and independent work should continue.
- Joe-required blocker evidence now also defines the A-G target-specific live
  blockers for delegated MCP tool sessions and Benedict Paralegal's private
  Nexus route, so every certification target blocker maps to an actionable
  blocker entry in `FREYJA-5.0-BLOCKERS.md`.
- Joe-required Freyja 5 live blocker posture is now canonicalized in
  `config/freyja-5.0-live-blockers.yaml` and shared by readiness and
  certification evidence.
- A-G target-specific live blocker mappings are now canonicalized in the same
  blocker config instead of being embedded in the readiness endpoint.
- `/freyja5/readiness` now reports Atlas as the persistent agent plane owning
  Gateway, `AgentRuntimeV3`, memory, audit, workers, health APIs, and Atlas MCP
  services. Msty Go remains preferred but unvalidated; the Atlas runtime
  boundary is preserved for substitution once live Linux reliability is proven.
- Static Freyja 5 plane posture is now canonicalized in
  `config/freyja-5.0-planes.yaml` and exposed through readiness.
- Freyja 5 certification evidence now includes the canonical plane posture so
  generated A-G reports prove Atlas/Iris/Hera/Vulcan boundaries and fallback
  preservation from source control.
- `/freyja5/readiness` now reports Vulcan/Nexus as the semantic inference plane,
  including source-controlled route-to-runtime preset mappings for `fast`,
  `general`, `deep`, `code`, `vision`, `embedding`, and `private`. Physical
  model/runtime selection remains owned by Nexus and cloud fallback remains
  explicit-only.
- Vulcan/Nexus readiness evidence now comes from a shared canonical helper that
  combines the MCP topology, semantic route map, and plane posture so readiness
  keeps proving Nexus ownership, local-by-default behavior, and explicit-only
  cloud fallback without endpoint-local boundary logic.
- `/freyja5/readiness` now exposes the same canonical semantic route evidence
  used by certification reports, including route capabilities, preferred Nexus
  runtime presets, and Benedict Paralegal's private local-only route policy.
- Freyja 5 certification evidence now includes canonical semantic route
  mappings from `config/freyja-5.0-semantic-routes.yaml`, proving Nexus route
  ownership, explicit-only cloud fallback, and the Benedict private local-only
  route in generated A-G reports.
- Freyja 5 certification reports now include the combined Vulcan/Nexus
  readiness evidence so generated A-G case artifacts prove the same semantic
  route presets, Nexus ownership, local-by-default posture, and explicit-only
  cloud fallback as `/freyja5/readiness`.
- Freyja 5 OpenAI-compatible requests now resolve known household `user` values
  such as `joe`, `beth`, `liam`, and `jenna` to stable `person:<id>` principals
  so the WebGUI channel uses the same identity/memory policy shape as other
  channels. Unknown UI users remain channel-scoped.
- Freyja 5 certification target E now includes compact identity-policy evidence
  summarizing channels, handoff count, common sender/authenticated subject/actor
  principal, and matching memory scopes.
- The opt-in `freyja-5` OpenAI-compatible path now converts inline data URL
  image/file content parts into Gateway attachments, preserving WebGUI
  operability while routing image/PDF-style requests through the media/vision
  skeleton without remote fetches.
- Freyja 5 certification reports now include sanitized media-path evidence for
  attachment count, MIME types, inline/path payload shape, vision-route
  selection, model/runtime, and confirmation that raw payload data is omitted.
- Freyja 5 certification reports now include optional-service degradation
  evidence for target G, recording disabled service fixtures, response
  availability, route selection, and local-only egress state.
- Freyja 5 certification reports now include Benedict Paralegal enclave
  evidence for target F, proving the paralegal owner/domain, enclave memory
  scope, private route, local-only egress policy, Vulcan/Nexus endpoint, and no
  unauthorized egress.
- The opt-in `freyja-5` OpenAI-compatible path now returns the
  `AgentRuntimeV3` response text with trace metadata instead of discarding it
  for a fixed skeleton banner. The preserved `agent-smith` WebGUI default path
  is unchanged.
- `/freyja5/readiness` now reports the WebGUI compatibility posture: the
  OpenAI-compatible surface is present, `agent-smith` remains the preserved
  default model, `freyja-5` is opt-in, inline image/PDF content parts are
  accepted, and cloud fallback stays disabled.
- WebGUI compatibility posture is now canonicalized in
  `config/freyja-5.0-webgui.yaml` and included in Freyja 5 certification
  evidence so generated reports prove the opt-in `freyja-5` path does not
  replace the preserved `agent-smith`/model-proxy default.
- `/freyja5/readiness` now exposes source-controlled MCP consumption evidence:
  per-agent scoped MCP tool IDs, grant counts, the MCP hosts those grants depend
  on, and confirmation that logical agents do not run duplicated default MCP
  servers.
- MCP topology readiness and certification evidence now share a single
  canonical helper, with tests guarding host placement, Vulcan's
  OpenAI-compatible Nexus boundary, Gateway policy, and per-agent MCP grant
  posture from `config/freyja-5.0-mcp-topology.yaml`.
- `/freyja5/readiness` consumes a shared compact MCP topology view instead of
  rebuilding its own agent/server summary, keeping per-agent MCP grants and
  host placement consistent with certification evidence.
- `/freyja5/readiness` now reports the Gateway boundary contract: Atlas hosts a
  deterministic ingress layer for auth, identity, channel/attachment
  normalization, policy, trace envelopes, and handoff forwarding, while agent
  reasoning, arbitrary tool orchestration, physical model selection, and
  implicit cloud fallback remain outside the Gateway.
- Freyja 5 certification evidence now includes per-agent MCP grant posture and
  Gateway boundary policy so generated A-G reports can prove agent/tool
  consumption and non-Director Gateway constraints from source control.
- The Freyja 5 Gateway non-Director contract is now canonicalized in
  `config/freyja-5.0-gateway.yaml` and shared by readiness and certification
  evidence: Atlas hosts channel normalization, identity/auth/policy,
  attachment normalization, trace envelopes, and handoff forwarding while agent
  reasoning, arbitrary tool orchestration, physical model selection, and
  implicit cloud fallback stay out of the Gateway.
- Freyja 5 certification evidence now includes Joe-required live blocker
  posture from `FREYJA-5.0-BLOCKERS.md`, including required validation evidence
  and confirmation that secrets remain outside source while independent work
  continues.
- `/freyja5/readiness` now reports Hera as a voice/avatar/perception channel
  edge that publishes semantic events into Atlas/Gateway, not as a general MCP
  or tool server. The readiness payload keeps live voice/avatar hardware listed
  as the remaining blocker.
- `/freyja5/readiness` now reports Iris as the Apple/macOS MCP capability
  server with MacAgent configuration presence, supported Apple capability
  families, Atlas-owned authorization, and live Apple session validation
  recorded as the remaining blocker without exposing tokens.
- Iris readiness evidence now comes from a shared helper that combines the
  source-controlled MCP plane contract with runtime MacAgent configuration
  booleans, while keeping token values out of the readiness payload.
- Certification target E now records separate `signal` and `open-webui` Gateway
  handoffs and verifies that both carry the same stable household principal and
  memory-scope policy for Joe.

## Start And Test

- Run unit tests: `pytest tests/test_freyja5_architecture.py tests/test_nexus_provider.py`
- Run the broader architecture spine: `pytest tests/test_freyja3_architecture.py`
- Run the 5.0 certification suite when live services are available:
  `freyja-certify routing/freyja5_architecture --provider freyja5`
- To test the explicit Freyja 5 OpenAI-compatible skeleton path, select model
  `freyja-5` against the Freyja `/v1/chat/completions` endpoint. Existing Open
  WebUI deployment remains pointed at `model-proxy` unless changed manually.
- To allow the `freyja-5` OpenAI-compatible endpoint to call live local Nexus
  inference, set `FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED=true` with `NEXUS_BASE_URL`
  and local host secrets configured outside source control.
- Capture the side-by-side Freyja 5 smoke report after starting the service:
  `scripts/freyja5-smoke.py --base-url http://127.0.0.1:8500 --token "$FREYJA_CONNECTOR_TOKEN" --output certification/reports/freyja5-smoke.json`.
- Assemble Freyja 5 certification/smoke evidence:
  `scripts/freyja5-readiness-bundle.py --run-certification --run-smoke --base-url http://127.0.0.1:8500 --token "$FREYJA_CONNECTOR_TOKEN" --output certification/reports/freyja5-readiness-bundle.json`.
  Exit code `2` means source certification and side-by-side smoke passed, but
  Joe-required live validation is still blocked.
- Summarize the latest Freyja 5 readiness bundle:
  `scripts/freyja5-preflight-status.py --report certification/reports/freyja5-readiness-bundle.json`.
- Start the side-by-side Freyja 5 gateway with
  `docker compose --env-file deploy/compose/freyja5/.env -f deploy/compose/freyja5/compose.yaml up -d --build`.
- Check Freyja 5 architecture posture with `GET /freyja5/readiness`.
- Start Atlas/Freyja sidecar using the existing deployment docs in
  `docs/operations/deployment.md`.
