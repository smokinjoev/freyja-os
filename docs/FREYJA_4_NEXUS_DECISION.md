# Freyja 4.0 Msty Nexus Decision

Last updated: 2026-08-30.

## Verdict

Continue testing.

Nexus fits the intended Freyja 4.0 model-gateway boundary on paper, but it was
not reachable on Vulcan during this run. The current evidence is insufficient to
adopt or reject it.

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
- Existing Vulcan Ollama and OpenAI-compatible proxy chat works.

## What Failed Or Was Not Verified

- Nexus was not reachable from Iris at `http://100.94.80.21:3939`.
- No ports in `3900-3960` were open on Vulcan.
- SSH inspection of Vulcan failed with host-key verification, so local
  installation state and systemd units could not be checked.
- No Nexus API token was available in the current environment.
- `/v1/models`, `/v1/chat/completions`, bad-token, and bad-model Nexus tests
  could not run against Nexus.
- Iris-to-Vulcan Nexus chat could not be verified.

## Blockers

- BLOCKER: Joe must repair or approve SSH trust for Vulcan:

```sh
ssh-keygen -R vulcan
ssh-keygen -R 100.94.80.21
ssh vulcan true
```

- BLOCKER: If Nexus is not installed, Joe must install it only from the official
  Msty Nexus Linux AppImage or Linux `.deb` installer from:

```text
https://msty.ai/products/nexus/
```

- BLOCKER: Joe must open Nexus on Vulcan, configure or discover the local
  runtime, create a local client token, enable Tailscale/LAN access only if
  Freyja/Iris/Atlas must connect remotely, and store the token outside git as
  `NEXUS_API_KEY`.

## Recommended Freyja 4.0 Architecture

Adopt Nexus only as a model gateway candidate:

```text
channel adapter
  -> Freyja dispatcher
  -> Privacy/Egress Gate
  -> Nexus preset/route
  -> model on Vulcan or approved cloud provider
  -> Freyja wrapper
```

Freyja must keep identity, personality, family agents, memory, privacy policy,
channel routing, tools, Home Assistant, Apple/body services through Iris, audit,
and response wrapping. Nexus may own model catalog, provider keys, local/cloud
runtimes, presets/routes, app tokens, usage, and model lifecycle.

## Exact Next Commands For Joe

After fixing SSH trust and installing/running Nexus:

```sh
export NEXUS_BASE_URL=http://100.94.80.21:3939
export NEXUS_API_KEY='<local Nexus client token>'

scripts/nexus-smoke.py --output logs/nexus-smoke.json
```

Manual equivalent:

```sh
curl "$NEXUS_BASE_URL/health"
curl "$NEXUS_BASE_URL/version"
curl "$NEXUS_BASE_URL/v1/models" \
  -H "Authorization: Bearer $NEXUS_API_KEY"
curl "$NEXUS_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $NEXUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"@preset/freyja-fast-local","messages":[{"role":"user","content":"Reply exactly: nexus-ok"}],"stream":false}'
```

Then configure Freyja:

```sh
export FREYJA3_INFERENCE_ENDPOINTS='[{"endpoint_id":"vulcan-nexus-fast","display_name":"Vulcan Nexus fast local preset","provider":"nexus","machine_id":"vulcan","base_url":"http://100.94.80.21:3939","model":"@preset/freyja-fast-local","capabilities":["general.local","chat"],"security_domain_id":"household","priority":12},{"endpoint_id":"vulcan-nexus-strong","display_name":"Vulcan Nexus strong local preset","provider":"nexus","machine_id":"vulcan","base_url":"http://100.94.80.21:3939","model":"@preset/freyja-strong-local","capabilities":["general.large","reasoning"],"security_domain_id":"household","priority":12},{"endpoint_id":"vulcan-nexus-coder","display_name":"Vulcan Nexus coder preset","provider":"nexus","machine_id":"vulcan","base_url":"http://100.94.80.21:3939","model":"@preset/freyja-coder","capabilities":["code.large","coding"],"security_domain_id":"household","priority":12}]'
.venv/bin/pytest tests/test_nexus_provider.py tests/test_nexus_smoke.py tests/test_freyja3_foundation.py
```
