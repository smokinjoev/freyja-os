# Open WebUI on Atlas

This Compose target runs Open WebUI as a user-facing web UI on Atlas while
keeping Atlas Freyja as the control-plane authority and Vulcan as compute.

Policy: Open WebUI lists the approved model catalog. The backend enforces one
resident Vulcan model at a time.

Planned model catalog:

| Role | Model |
| --- | --- |
| Hot daily/tool model | `qwen3.8:27b` |
| Fast general chat | `gpt-oss-freyja:20b-analysis-prefill` |
| Reasoning agent candidate | `qwen3:30b-a3b` |
| Coding | `qwen3-coder-next:q4_K_M` |
| GPT OSS small | `gpt-oss:20b` or `gpt-oss-freyja:20b-analysis-prefill` |
| GPT OSS large | `gpt-oss:120b` |

Open WebUI may show these models in its picker. The intentionally hot resident
model is `qwen3.8:27b`; larger or specialized models stay available on demand
but should not remain resident accidentally.

Fallback rule: Iris/Ollama is only a 7B/12B-class fallback tier. The 20B, 30B,
coder, 72B, and 120B roles are Vulcan-only unless another machine with enough
memory is added.

Default topology:

```text
browser/PWA clients -> Atlas Open WebUI -> Vulcan OpenAI-compatible endpoint
```

Freyja remains the Atlas control plane. Main Freyja Director is healthy on
Atlas, but it does not currently expose OpenAI-compatible `/v1/models`
endpoints for Open WebUI.

## Start

On Atlas:

```bash
cp deploy/compose/open-webui/.env.example deploy/compose/open-webui/.env
chmod 600 deploy/compose/open-webui/.env
sed -i "s/replace-with-random-hex/$(openssl rand -hex 32)/" deploy/compose/open-webui/.env
sed -i "s/replace-with-random-secret/$(openssl rand -hex 32)/" deploy/compose/open-webui/.env
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml config
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
```

Then open:

```text
http://<atlas-tailscale-host>:3001
```

## Provider

The default `.env.example` points Open WebUI to Vulcan's OpenAI-compatible
endpoint over Tailscale:

```text
OPENAI_API_BASE_URL=http://model-proxy:8080/v1
OPENAI_API_KEY=not-needed
DEFAULT_MODELS=qwen2.5vl:72b
OPEN_WEBUI_APPROVED_MODELS=qwen3.8:27b,qwen2.5vl:72b,qwen3:30b-a3b,qwen3-coder-next:q4_K_M,gpt-oss:20b,gpt-oss-freyja:20b-analysis-prefill,gpt-oss:120b
OPEN_WEBUI_FALLBACK_MODELS=qwen2.5:7b
```

`DEFAULT_MODELS` only controls the initial Open WebUI default. Runtime model
choice belongs to Open WebUI; the proxy preserves the selected request model
and unloads other resident Vulcan models before forwarding chat.

Vulcan policy: Ollama is the canonical model runtime. Msty Nexus is the stable
preset/routing layer over Ollama, not a second model source of truth. Ollama is
configured for one loaded model and one parallel request, with qwen3.8 warmed
by `freyja-hot-model-warm.timer`. The Ollama context cap is `16384` for normal
serving so OpenAI-compatible calls do not accidentally allocate the full 262k
context. Vulcan exposes an AMD Strix/Krackan/Strix Halo NPU at `/dev/accel0`
with the `amdxdna` driver, but normal LLM serving remains on the Radeon GPU.

The model proxy checks Vulcan first and Iris second. Iris fallback is only for
7B/12B-class active models installed on Iris. DNS, socket, and other connection
failures from any upstream are returned as bounded JSON errors instead of
disconnecting the Open WebUI client.

The model proxy includes a narrow reasoning-output adapter for local models
such as `gpt-oss:120b` that sometimes return useful text in an
OpenAI-compatible `reasoning` field while leaving assistant `content` empty.
For non-streaming chat completions, the proxy promotes nonempty `reasoning` to
visible `content` only when `content` is empty. Normal responses with existing
assistant content are left unchanged.

## Default Model Change Procedure

1. Pick the default model.
2. Use the switch helper:

```bash
deploy/compose/open-webui/switch-model.sh <model-id>
```

Or set the default in `deploy/compose/open-webui/.env` manually:

```text
DEFAULT_MODELS=<model-id>
```

3. Recreate Open WebUI:

```bash
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
```

4. Check Vulcan residency:

```bash
curl http://100.94.80.21:8088/api/ps
```

If more than the intended model is resident, or if qwen3.8 is not the hot
resident model after normal use, unload the unwanted model from Vulcan before
continuing:

```bash
scripts/vulcan-operator.py loaded
scripts/vulcan-operator.py unload-profile reason --yes
```

For now, when ending an Open WebUI work session, leave the last active model
warm on Vulcan instead of unloading it immediately.

## Open Terminal

The compose stack runs Open Terminal on the private Docker network only. In
Open WebUI, configure it under Admin Settings > Admin > Integrations > Open
Terminal:

```text
URL: http://open-terminal:8000
Auth Type: Bearer
API Key: value of OPEN_TERMINAL_API_KEY from deploy/compose/open-webui/.env
```

Do not use `localhost` for this URL; from the Open WebUI container, the service
name is `open-terminal`.

## Update

```bash
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml pull
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
```

The `open-webui` Docker volume preserves `/app/backend/data` across container
recreates.
