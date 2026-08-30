# Freyja 3.0 Handoff

Last updated: 2026-08-30.

## Handoff Summary

Freyja 3.0 is preserved as a distributed household-agent architecture with no
intelligent Director. Freyja keeps identity, personality, privacy, routing,
tools, memory, family agents, Home Assistant, Apple/body services via Iris, and
response wrapping. Vulcan provides brain compute. Atlas provides always-on
gateway and infrastructure. Hera provides avatar/presence. Machines do not own
agent identity.

## Do Not Break

- Do not reintroduce an intelligent Director that classifies tasks, selects
  tools, selects models, plans work, or answers instead of a persistent agent.
- Do not collapse Freyja, Iris, Atlas, Vulcan, Hera, and family agents into one
  identity.
- Do not let a model gateway own memory, privacy policy, tool grants, channel
  routing, family-agent identity, or response authority.
- Do not send private/sensitive/restricted content to cloud AI without the
  Privacy/Egress Gate.
- Do not let household agents access the paralegal enclave.
- Do not treat compatibility names such as legacy Director or legacy Ollama
  fields as the target architecture.

## Freyja 4.0 Evaluation Entry Point

Evaluate Msty Nexus only as a model gateway candidate. Nexus may own provider
keys, model catalog, local/cloud runtimes, OpenAI-compatible API exposure,
presets/routes, app tokens, usage tracking, and model lifecycle.

Freyja must remain the system of record for:

- agent identity and personality
- privacy and egress policy
- channel adapters and response wrapping
- tool grants and authorization
- memory and family-agent boundaries
- Home Assistant, calendar, iMessage, Signal, Gmail, and MacAgent integration
- audit semantics and safety behavior

## Suggested First Commands

```sh
git status --short --branch
git remote -v
pytest tests/test_freyja3_architecture.py tests/test_host_role_docs.py
```
