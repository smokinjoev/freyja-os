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
  handoff metadata.
- F. Benedict Paralegal selects the `private` route and local-only egress policy.
- G. Optional service disablement is covered by endpoint health fallback tests.

## Blocked

See `FREYJA-5.0-BLOCKERS.md` for Joe-required validation and physical/session
tasks.

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
  `certification/reports/20260831T233459Z0000-freyja5-architecture.md`.
- Runtime trace summaries now include channel, resolved user, authenticated
  subject, agent, requested route, actual endpoint/provider/model/runtime,
  selected tools, tool calls, delegation evidence, machine, latency, failures,
  fallbacks, inference status, and egress state.
- Source-controlled Freyja 5.0 agent and route summaries are covered by drift
  tests against `foundation_seed.py`.
- Freyja 5.0 certification/runtime mode disables implicit cloud fallback while
  preserving the legacy 4.1 policy-gated fallback path for compatibility.
- MCP-preferred tool boundaries are explicit in source tool grants and runtime
  traces record each selected tool's protocol, machine affinity, and mutation
  status.
- MCP servers are assigned by capability host, not duplicated per agent: Iris
  owns Apple/macOS MCP capabilities, Atlas owns household/service MCP
  capabilities, Vulcan remains Nexus inference, and agents consume MCP through
  source-controlled scoped grants.
- Added an opt-in OpenAI-compatible `freyja-5` model path that exercises
  Gateway identity/channel handling and `AgentRuntimeV3` route/trace selection
  without live inference, while preserving the existing Open WebUI model-proxy
  default and `agent-smith` compatibility path.
- Added default-off `FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED` so the opt-in
  `freyja-5` OpenAI-compatible path can use live local Nexus inference only
  when explicitly enabled. Cloud fallback remains disabled on that path.
- Freyja 5 certification reports include source-controlled MCP topology
  evidence: default per-agent MCP servers are disabled, MCP hosts are Atlas and
  Iris, and Vulcan remains the OpenAI-compatible Nexus inference boundary.
- Added a side-by-side Freyja 5 compose target at `deploy/compose/freyja5` for
  Atlas testing on port `8500`. It preserves existing 4.1/Freyja3/Open WebUI
  deployments and keeps live inference/cloud egress disabled by default.

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
- Start the side-by-side Freyja 5 gateway with
  `docker compose --env-file deploy/compose/freyja5/.env -f deploy/compose/freyja5/compose.yaml up -d --build`.
- Start Atlas/Freyja sidecar using the existing deployment docs in
  `docs/operations/deployment.md`.
