# Freyja 4.0 Local Family Agents

Last updated: 2026-08-30.

## Final Roster

Freyja 4.0 is local-first. Family and personal agents use Nexus presets on
Vulcan by default, and no agent silently falls back to cloud.

| Agent | Owner | Role | Memory Scope | Default Preset | Allowed Tool Classes |
| --- | --- | --- | --- | --- | --- |
| Freyja | household | Primary household interface, coordinator, HomePod/Hera voice | `family`, `system`, `agent:freyja` private | `@preset/freyja-fast-local` | Home Assistant, Apple services through Iris, messages, calendar, shared memory, system health |
| Cloyd Gibbler | Joe | Joe's personal/project/code agent | `person:joe`, `family`, `system` | `@preset/freyja-coder` | code, shell/files/git when authorized, Apple services through Iris, messages, calendar, private/shared memory |
| Benedict | Beth | Beth's personal agent for ordinary personal and household work | `person:beth`, `family`, `system` | `@preset/freyja-private-local` | documents, Apple services through Iris, messages, calendar, private/shared memory |
| Benedict Paralegal | paralegal enclave | Legal-support enclave for restricted legal documents and research | `enclave:paralegal`, `system` | `@preset/benedict-paralegal-local` | document review, browser/search when approved, vision/document inspection, enclave memory |
| Agent 44 | Liam | Liam's personal agent | `person:liam`, `family`, `system` | `@preset/freyja-private-local` | age-appropriate personal tools, messages/calendar reads as authorized, private/shared memory |
| Jenna | Jenna | Jenna's personal agent | `person:jenna`, `family`, `system` | `@preset/freyja-private-local` | age-appropriate personal tools, messages/calendar reads as authorized, private/shared memory |
| Agent Smith | system | Infrastructure, diagnostics, certification, recovery | `system` | `@preset/freyja-private-local` | system health and bounded maintenance tools |

## Boundaries

- Freyja can coordinate household context, Home Assistant, shared memory, and
  Apple/body services through Iris, but cannot read paralegal enclave memory.
- Personal agents can read and write their own private memory plus ordinary
  family shared memory. They cannot read another person's private memory unless
  a higher-level Freyja policy explicitly grants a scoped handoff.
- Benedict's ordinary Beth-personal identity is separate from Benedict
  Paralegal. Legal work routes to `benedict-paralegal`, not Beth's personal
  `benedict` agent.
- Benedict Paralegal cannot share legal memory into the family memory pool.
  Its cloud policy is `paralegal-local-only`.
- Home Assistant control belongs to Freyja by default. Personal agents may
  request household actions through Freyja rather than directly controlling the
  house unless a tool grant explicitly permits the action.
- Calendar, messages, mail, browser, music, and other Apple/body services run
  through Iris. Freyja keeps authorization and response wrapping.
- Web/cloud research is disabled unless Joe explicitly approves provider,
  model, budget, and privacy rules.

## Local Gateway

Freyja talks directly to Msty Nexus through the OpenAI-compatible API at
`http://100.94.80.21:3939/v1`. Nexus runs on Vulcan and exposes local presets.
Msty Studio is Joe's workbench for manual chats, prompts, presets, model tests,
and inspection. Studio must not replace Freyja identity, memory, tools,
routing, privacy gates, family agents, audit, or channel behavior.

Tokens stay outside git. The Nexus client token is stored on Vulcan at
`/home/joe/.config/freyja/msty-nexus-token` and is supplied to Freyja through
`NEXUS_API_KEY`.
