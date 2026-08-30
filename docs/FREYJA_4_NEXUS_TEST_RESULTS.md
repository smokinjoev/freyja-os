# Freyja 4.0 Msty Nexus Test Results

Last updated: 2026-08-30.

## Status

Verdict for this run: continue testing. Nexus was not reachable on Vulcan from
Iris at the documented default runtime port, and SSH inspection of Vulcan was
blocked by host-key verification. Existing non-Nexus Vulcan inference remains
healthy.

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

SSH inspection:

```text
ssh -o BatchMode=yes -o ConnectTimeout=5 vulcan ...
Host key verification failed.
```

BLOCKER: Joe must repair or approve the SSH host key for Vulcan, then rerun the
Vulcan filesystem/systemd inspection:

```sh
ssh-keygen -R vulcan
ssh-keygen -R 100.94.80.21
ssh vulcan 'hostname; command -v msty-nexus msty-nexusctl msty || true; systemctl --user --no-pager --type=service --all | grep -iE "msty|nexus" || true; systemctl --no-pager --type=service --all | grep -iE "msty|nexus" || true; ss -ltnp | grep -iE "3939|msty|nexus" || true'
```

Nexus runtime probe from Iris to Vulcan:

```text
http://100.94.80.21:3939/health    -> connection refused
http://100.94.80.21:3939/v1/models -> connection refused
TCP scan 3900-3960                 -> no open ports
```

Interpretation: no Nexus Runtime was reachable on the documented default port
or nearby ports from Iris over Tailscale during this run. This does not prove
Nexus is absent from disk because SSH inspection was blocked.

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

- No Nexus token was found or committed.
- Freyja config now uses `NEXUS_API_KEY` for provider `nexus`; it does not reuse
  `LITELLM_MASTER_KEY`.
- Any real Nexus local client token must be stored outside git.

## Required Remaining Nexus Tests

After Nexus is installed/running on Vulcan and LAN/Tailscale access is enabled:

```sh
curl http://100.94.80.21:3939/health
curl http://100.94.80.21:3939/version
curl http://100.94.80.21:3939/v1/models \
  -H "Authorization: Bearer $NEXUS_API_KEY"
curl http://100.94.80.21:3939/v1/chat/completions \
  -H "Authorization: Bearer $NEXUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"@preset/freyja-fast-local","messages":[{"role":"user","content":"Reply exactly: nexus-ok"}],"stream":false}'
```

Also verify bad-token and bad-model behavior:

```sh
curl http://100.94.80.21:3939/v1/models \
  -H "Authorization: Bearer bad-token"
curl http://100.94.80.21:3939/v1/chat/completions \
  -H "Authorization: Bearer $NEXUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"@preset/not-a-real-preset","messages":[{"role":"user","content":"test"}],"stream":false}'
```

Expected: explicit unauthorized / invalid model errors, no silent cloud fallback.
