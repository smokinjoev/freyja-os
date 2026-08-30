# Freyja 4.0 Msty Nexus Decision

Last updated: 2026-08-30.

## Verdict

Adopt for the Freyja 4.0 local Vulcan model gateway.

Continue separate testing for cloud research only. Cloud routing was not enabled
or tested during this run to avoid burning cloud tokens and to preserve Freyja's
Privacy/Egress Gate as the authority.

Adopt Msty Studio separately as Joe's operator workbench on Mac/iPad for manual
model testing, chats, prompts, presets, and inspection. Studio is not a Freyja
runtime component and must not replace Freyja identity, memory, tools, routing,
privacy gates, family agents, audit, or response wrapping.

## What Worked

- Official Msty docs describe Nexus as a local Runtime with OpenAI-compatible
  routes, local Nexus client tokens, model catalog, providers, presets/routes,
  runtime management, usage, and local/cloud gateway behavior.
- Freyja already has an inference endpoint registry that can target
  OpenAI-compatible local gateways.
- Freyja now has a dedicated `nexus` provider credential path using
  `NEXUS_BASE_URL` and `NEXUS_API_KEY`, avoiding accidental reuse of LiteLLM
  credentials.
- Vulcan itself is reachable from Iris over Tailscale.
- Nexus Runtime 0.4.1 is installed from the official Linux AppImage on Vulcan.
- `msty-nexus-runtime.service` is enabled and active under Joe's user manager.
- Nexus listens on `0.0.0.0:3939` and is reachable from Iris at
  `http://100.94.80.21:3939`.
- Nexus registered Vulcan's existing local Ollama runtime as provider
  `vulcan-ollama`.
- Nexus lists 16 visible model entries, including direct local Ollama models and
  Freyja local presets.
- Nexus chat works for `@preset/freyja-fast-local` and
  `@preset/freyja-strong-local`.
- Bad token returns `401 UNAUTHORIZED`.
- Bad model returns `404 MODEL_NOT_FOUND`.
- Freyja talks directly to Nexus through its OpenAI-compatible API at
  `http://100.94.80.21:3939/v1`.
- Freyja runtime can call Nexus from Iris and get the intended local response
  from Vulcan.

## What Failed Or Was Not Verified

- `freyja-cloud-research` was not configured or tested.
- The Nexus Runtime service is a user-level service built around the extracted
  AppImage runtime binary, not a distro-managed `.deb` install.
- Freyja-side bad-token and bad-model errors currently surface as
  `inference_status=error`; Nexus itself returns explicit machine-readable
  error codes.

## Blockers

- BLOCKER: Before enabling `freyja-cloud-research`, Joe must approve the cloud
  provider, budget, model allowlist, and privacy/egress policy.

## Recommended Freyja 4.0 Architecture

Adopt Nexus as the local model gateway between Freyja/Iris/Atlas and Vulcan:

```text
channel adapter
  -> Freyja dispatcher
  -> Privacy/Egress Gate
  -> Nexus preset/route
  -> model on Vulcan or approved cloud provider
  -> Freyja wrapper
```

Freyja keeps identity, personality, privacy policy, memory, family agents,
channel routing, tools, Home Assistant, Apple/body services through Iris, audit,
and response wrapping. Nexus may own model catalog, provider keys, local/cloud
runtimes, presets/routes, app tokens, usage, and model lifecycle.

Vulcan is the brain. Iris owns Apple/body services. Atlas remains the always-on
gateway. Hera owns avatar/presence.

The finalized local family agent roster and boundaries are documented in
`docs/FREYJA_4_LOCAL_FAMILY_AGENTS.md`.

## Exact Next Commands For Joe

Current smoke command:

```sh
export NEXUS_BASE_URL=http://100.94.80.21:3939
export NEXUS_API_KEY='<local Nexus client token>'

scripts/nexus-smoke.py --output logs/nexus-smoke.json
```

Service checks on Vulcan:

```sh
systemctl --user status msty-nexus-runtime.service
curl http://100.94.80.21:3939/health
```

Freyja now seeds Nexus preset endpoints by default while keeping direct Ollama
providers as local fallback. To override from the environment:

```sh
export FREYJA3_INFERENCE_ENDPOINTS='[{"endpoint_id":"vulcan-nexus-fast","display_name":"Vulcan Nexus fast local preset","provider":"nexus","machine_id":"vulcan","base_url":"http://100.94.80.21:3939","model":"@preset/freyja-fast-local","capabilities":["general.local","chat"],"security_domain_id":"household","priority":12},{"endpoint_id":"vulcan-nexus-strong","display_name":"Vulcan Nexus strong local preset","provider":"nexus","machine_id":"vulcan","base_url":"http://100.94.80.21:3939","model":"@preset/freyja-strong-local","capabilities":["general.large","reasoning"],"security_domain_id":"household","priority":12},{"endpoint_id":"vulcan-nexus-coder","display_name":"Vulcan Nexus coder preset","provider":"nexus","machine_id":"vulcan","base_url":"http://100.94.80.21:3939","model":"@preset/freyja-coder","capabilities":["code.large","coding"],"security_domain_id":"household","priority":12}]'
.venv/bin/pytest tests/test_nexus_provider.py tests/test_nexus_smoke.py tests/test_freyja3_foundation.py
```
