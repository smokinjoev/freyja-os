# Freyja 4.0 Msty Nexus Test Results

Last updated: 2026-08-30.

## Status

Verdict for this run: adopt Nexus for the Freyja 4.0 local Vulcan model-gateway
path. Keep cloud research disabled until separate cloud egress and budget review.

Nexus Runtime is installed from the official Linux AppImage on Vulcan, runs as a
Joe user-level systemd service, exposes an OpenAI-compatible API over Tailscale,
registers Vulcan's existing local Ollama runtime, lists local models/presets,
returns successful chat completions, and produces explicit bad-token and
bad-model failures.

## Official Nexus Reference Points

- Msty's Nexus product page lists Linux AppImage and Linux `.deb` installers for
  Nexus and describes it as a local gateway for model catalogs, runtimes,
  provider credentials, presets, app tokens, and usage.
- Msty's Nexus setup docs say production Runtime is local-only by default,
  `http://127.0.0.1:3939`, and LAN exposure should be enabled only with a token
  and network plan.
- Msty's Nexus gateway/API docs list OpenAI-compatible routes including
  `GET /v1/models` and `POST /v1/chat/completions`.
- Msty's Nexus security docs say every `/v1/*` endpoint requires a local Nexus
  token, with `Authorization: Bearer`, `X-Msty-Nexus-Token`, or `x-api-key`
  accepted, and provider credentials are not returned by API responses.

Sources checked:

- https://msty.ai/products/nexus/
- https://docs.msty.ai/nexus/setup
- https://docs.msty.ai/nexus/gateway
- https://docs.msty.ai/nexus/api-and-sdks
- https://docs.msty.ai/nexus/security

## Local/Tailscale Evidence

Machine discovery:

```text
tailscale status showed:
100.94.80.21 vulcan-1 linux active
100.115.228.56 iris macOS active
100.119.235.114 atlas linux idle
```

SSH and install inspection:

```text
ssh joe@100.94.80.21 -> hostname Vulcan
official AppImage: /home/joe/Applications/Msty-Nexus_x86_64.AppImage
extracted runtime: /home/joe/Applications/squashfs-root/usr/bin/msty-nexus
user service: msty-nexus-runtime.service enabled and active
```

Runtime:

```text
GET http://100.94.80.21:3939/health -> {"status":"ok"}
GET http://100.94.80.21:3939/version -> msty-nexus 0.4.1, linux/amd64
listen address -> 0.0.0.0:3939 and [::]:3939
```

Provider and models:

```text
provider id: vulcan-ollama
provider kind: ollama
provider base URL inside Vulcan: http://127.0.0.1:11434/v1
autoProxyModels: true
models listed through Nexus: 16 including presets and local Ollama models
```

Configured local presets:

- `@preset/freyja-fast-local` -> `vulcan-ollama/qwen2.5:7b`
- `@preset/freyja-strong-local` -> `vulcan-ollama/qwen2.5:32b-instruct`
- `@preset/freyja-coder` -> `vulcan-ollama/qwen3-coder-next:q4_K_M`
- `@preset/freyja-vision-docs` -> `vulcan-ollama/qwen2.5vl:72b`
- `@preset/freyja-private-local` -> `vulcan-ollama/qwen2.5:32b-instruct`
- `@preset/benedict-paralegal-local` -> `vulcan-ollama/qwen2.5:32b-instruct`

All configured local presets use `routing.preferLocal=true`,
`allowFallbacks=false`, and `allowPaidFallback=false`.

## Existing Vulcan Runtime Evidence

Ollama native API:

```text
http://100.94.80.21:11434/api/tags -> reachable
```

Observed local model IDs included:

- `gpt-oss:120b`
- `gpt-oss:20b`
- `qwen2.5:32b-instruct`
- `qwen3:30b-a3b`
- `qwen3-coder-next:q4_K_M`
- `qwen2.5vl:72b`
- `hf.co/bartowski/Qwen_Qwen2.5-VL-32B-Instruct-GGUF:Q6_K`
- `minicpm-v:latest`
- `nomic-embed-text:latest`
- `qwen2.5:7b`

Ollama OpenAI-compatible proxy:

```text
http://100.94.80.21:8088/v1/models -> reachable
http://100.94.80.21:8090           -> TCP open
```

LM Studio:

```text
http://100.94.80.21:1234/v1/models -> reachable
model: text-embedding-nomic-embed-text-v1.5
```

Chat smoke from Iris to Vulcan OpenAI-compatible proxy:

```text
POST http://100.94.80.21:8088/v1/chat/completions
model: qwen2.5:32b-instruct
result: assistant returned "vulcan-chat-ok"
```

## Token Notes

- Runtime token is stored on Vulcan at
  `/home/joe/.config/freyja/msty-nexus-token` and injected into the user service
  through `/home/joe/.config/freyja/msty-nexus-runtime.env`.
- Freyja config uses `NEXUS_API_KEY` for provider `nexus`; it does not reuse
  `LITELLM_MASTER_KEY`.
- No Nexus token was committed. Smoke output reports only `token_configured`
  and `token_value: <redacted>`.

## Nexus Smoke Results

From Iris:

```sh
NEXUS_BASE_URL=http://100.94.80.21:3939 \
NEXUS_API_KEY='<local Nexus client token>' \
scripts/nexus-smoke.py --output logs/nexus-smoke.json
```

Result:

```text
ready: true
health: 200
version: 200, msty-nexus 0.4.1
models: 200, 16 visible model entries
chat: 200, resolved_model qwen2.5:7b, response_matched true
bad_token: 401 UNAUTHORIZED
bad_model: 404 MODEL_NOT_FOUND
```

Freyja runtime smoke from Iris:

```text
endpoint: vulcan-nexus-fast
machine: vulcan
model: @preset/freyja-fast-local
status: ok
response: freyja-nexus-ok
```

Strong/local route smoke:

```text
endpoint: vulcan-nexus-strong
machine: vulcan
model: @preset/freyja-strong-local
status: ok
response: freyja-nexus-strong-ok
```

Bad Freyja-side Nexus token/model tests returned `inference_status=error` and
did not silently fall back to cloud.

## Remaining Follow-Up

- `freyja-cloud-research` was intentionally not configured or tested because
  the evaluation rule says not to burn cloud tokens.
- If cloud research is added later, configure it only after Freyja's
  Privacy/Egress Gate and budget policy approve the route.
