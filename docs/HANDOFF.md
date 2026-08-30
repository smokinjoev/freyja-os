# Freyja 4.0 Handoff

Last updated: 2026-08-30.

## Current State

Freyja 4.0 adopts Msty Nexus as the local model gateway on Vulcan and Msty
Studio as Joe's human-facing workbench for manual testing and inspection.
Freyja remains the identity, personality, privacy, memory, family-agent, tool,
channel, audit, Home Assistant, Apple/Iris, and response authority.

Prior Nexus commits are present and pushed at `origin/main`:

- `d0cc058 freyja 4.0: adopt nexus local gateway`
- `b6e6c7f freyja 4.0: record nexus blocker retry`
- `40771e9 freyja 4.0: add nexus smoke runner`
- `db67746 freyja 4.0: evaluate msty nexus gateway`

## Endpoints

- Vulcan Tailscale IP: `100.94.80.21`
- Nexus base URL: `http://100.94.80.21:3939`
- OpenAI-compatible base URL: `http://100.94.80.21:3939/v1`
- Token file on Vulcan: `/home/joe/.config/freyja/msty-nexus-token`
- Freyja token env var: `NEXUS_API_KEY`

## Adopted Roles

- Vulcan is the brain and runs Nexus plus local model presets.
- Iris owns Apple/body services and hot local device integrations.
- Atlas remains the always-on gateway/infrastructure host.
- Hera owns avatar, voice, presence, and perception.
- Studio is Joe's Mac/iPad workbench and does not replace Freyja runtime
  authority.

## Local Presets

- `@preset/freyja-fast-local`: default household/local chat.
- `@preset/freyja-strong-local`: heavier private household reasoning.
- `@preset/freyja-coder`: Joe/Cloyd coding work.
- `@preset/freyja-vision-docs`: local vision and document understanding.
- `@preset/freyja-private-local`: personal/private family agents.
- `@preset/benedict-paralegal-local`: restricted paralegal enclave.

## Family Agents

The finalized roster is in `docs/FREYJA_4_LOCAL_FAMILY_AGENTS.md`.

Runtime defaults now prefer Nexus endpoints:

- `vulcan-nexus-fast`
- `vulcan-nexus-strong`
- `vulcan-nexus-coder`
- `vulcan-nexus-vision-docs`
- `benedict-paralegal-nexus`

Direct Ollama endpoints remain available as local fallback. Cloud routes are
disabled unless Joe explicitly approves provider, model, budget, and privacy
rules. There is no silent cloud fallback.

## Blockers

- BLOCKER: Cloud research remains disabled until Joe approves provider, model
  allowlist, budget, and privacy/egress policy.
- BLOCKER: Nexus token must remain outside git and be supplied from local
  environment or host secret management.

## Next Commands

```sh
export NEXUS_BASE_URL=http://100.94.80.21:3939
export NEXUS_API_KEY="$(ssh vulcan 'cat /home/joe/.config/freyja/msty-nexus-token')"

scripts/nexus-smoke.py --output logs/nexus-smoke.json
.venv/bin/pytest tests/test_nexus_provider.py tests/test_nexus_smoke.py tests/test_household_agents.py tests/test_freyja3_foundation.py
```
