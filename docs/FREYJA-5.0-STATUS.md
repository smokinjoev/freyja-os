# Freyja 5.0 Status

## Complete

- Created a recoverable Freyja 4.1 baseline tag before migration work.
- Added source-controlled Freyja 5.0 architecture documentation.
- Added source-controlled canonical summaries for persistent agents and semantic
  Nexus routes.
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
- B. Freyja to Cloyd delegation is represented by persistent agent routing and
  coding lane contracts; richer agent-to-agent delegation remains incremental.
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

## Start And Test

- Run unit tests: `pytest tests/test_freyja5_architecture.py tests/test_nexus_provider.py`
- Run the broader architecture spine: `pytest tests/test_freyja3_architecture.py`
- Run the 5.0 certification suite when live services are available:
  `freyja-certify routing/freyja5_architecture`
- Start Atlas/Freyja sidecar using the existing deployment docs in
  `docs/operations/deployment.md`.
