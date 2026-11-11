# Freyja consolidation promotion record

The former `codex/freyja-consolidation` integration branch was promoted to
`main` as reviewed, tested slices. `main` is now the shared canonical source.
The historic branch remains a recovery and audit reference, not a deployment
baseline.

## Completed promotion slices

| Slice | Pull request | Scope | Validation |
| --- | --- | --- | --- |
| Smith runtime and prerequisites | #14 | Smith/Cloyd stabilization, clean-checkout validation, Open WebUI Apple policy alignment, and sanitized certification baselines | Focused Smith/Cloyd tests and full suite |
| Messaging reminders | #19 | Gmail reminder monitor, Signal scheduled reminders, Compose wiring, and ownership | Gmail/Signal focused tests and full suite |
| Terminal bridge reliability | #20 | Scheduler-safe terminal bridge lifecycle assertion | Full suite on Python 3.11, 3.12, and 3.13 |
| Apple and portal safety | #21 | Constrained Apple Mail tools, bounded portal context, and MacAgent routing safeguards | Apple/MacAgent focused tests and full suite |
| Runtime portability | #22 | Checkout-relative Core-MCP and Discord launchers | Wrapper-focused tests and full suite |
| Operational records | This change | Canonical-source boundaries and host-migration records | Full suite and documentation review |

## Ongoing operating rules

1. Create changes from current `main`, review them in a scoped pull request,
   and run the relevant focused gate plus the full suite.
2. Deploy only the services affected by an accepted change; retain the prior
   host checkout or configuration as a dated recovery artifact until health is
   confirmed.
3. Treat host-specific LaunchAgents, credentials, data, and identity mappings
   as external configuration. Generic behavior may enter `main` only when it
   has been extracted and tested.
4. Keep the canonical-host inventory current whenever a host migration or
   source path changes.

## Current evidence

- The current documentation candidate passed the full suite: 1,971 passed,
  6 skipped.
- Iris runs its eight managed services from canonical staging; Director,
  OpenAI API, and Core-MCP health checks passed before the legacy checkout was
  moved to a dated recovery archive.
- Atlas and Vulcan retain the validated canonical deployments described in
  `freyja-source-consolidation.md`.
