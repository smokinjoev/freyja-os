# Freyja consolidation promotion review

`codex/freyja-consolidation` is intentionally a consolidation branch, not a
single merge candidate.  It is 25 commits ahead of `main` and combines
runtime behavior, deployment wiring, host migration records, and portability
cleanup.  Promote only reviewed slices, in this order.

## Promotion slices

| Slice | Commits | Scope | Required gate before promotion |
| --- | --- | --- | --- |
| Smith runtime and prerequisites | `9ad7391` through `89b6b9f`, `c6ca3a5`, `31e360b`, `6a02894` | Smith/Cloyd runtime stabilization, clean-checkout validation, Open WebUI Apple policy alignment, and sanitized certification baselines | Focused Smith/Cloyd tests plus the full suite |
| Messaging reminders | `df0f31e` through `09cd0f1` | Gmail reminder monitor and Signal scheduled-reminder delivery, Compose wiring, and ownership | Gmail/Signal focused tests, Atlas compose validation, then a healthy deployed monitor and connector |
| Apple and portal safety | `7c8146d`, `3e27384`, `c6ca3a5`, `f678581` | Constrained Apple Mail tools, bounded portal context, source-checkout testability, and MacAgent routing safeguards | Apple/MacAgent focused tests, full suite, and authenticated Iris health checks |
| Runtime portability | `33f6f3b`, `7d6a2aa` | Checkout-relative Core-MCP and Discord wrappers | Wrapper-focused tests, full suite, and Iris Core-MCP/Discord process audit |
| Operational records | `d3157c4` through `da33cfc` | Canonical-source and host-migration documentation | Documentation tests and confirmation that archive locations exist |

## Review rules

1. Do not merge the whole branch directly into `main`.
2. For each slice, create a review branch from current `main`, cherry-pick the
   listed commits in order, and rerun that slice's gate.
3. Deploy only the services affected by the reviewed slice; retain the prior
   host checkout or configuration as a dated recovery artifact until health is
   confirmed.
4. Treat host-specific LaunchAgents, credentials, data, and identity mappings
   as external configuration.  They are not promotion candidates unless their
   generic behavior is extracted and tested.
5. After each accepted slice, refresh this inventory against the new `main`
   before preparing the next one.

## Current evidence

- The full suite passed at `7d6a2aa`: 1,971 passed, 6 skipped.
- An isolated candidate from current `main` cherry-picked the Smith range plus
  `c6ca3a5`, `31e360b`, and `6a02894`. Its Smith-focused gate passed (139
  tests) and its full suite passed: 1,948 passed, 6 skipped. The Open WebUI
  policy alignment and sanitized certification baselines are therefore
  required prerequisites for this promotion slice, not optional follow-ups.
- Iris runs its eight managed services from canonical staging; Director,
  OpenAI API, and Core-MCP health checks passed before the legacy checkout was
  moved to a dated recovery archive.
- Atlas and Vulcan retain their validated canonical deployments described in
  `freyja-source-consolidation.md`.
