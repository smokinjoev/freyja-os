# Open WebUI on Atlas

This Compose target runs Open WebUI as a user-facing web UI on Atlas while
keeping Atlas Freyja as the control-plane authority and Vulcan as compute.

Policy: Open WebUI lists the approved model catalog. The backend enforces one resident Vulcan model at a time.

Planned model catalog:

| Role | Model |
| --- | --- |
| Daily driver | `qwen2.5vl:72b` |
| Fast general chat | `qwen2.5:32b-instruct` |
| Reasoning agent candidate | `qwen3:30b-a3b` |
| Coding | `qwen3-coder-next:q4_K_M` |
| GPT OSS small | `gpt-oss:20b` or `gpt-oss-freyja:20b-analysis-prefill` |
| GPT OSS large | `gpt-oss:120b` |

Open WebUI may show these models in its picker. Only the selected model should be resident on Vulcan at runtime.

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
OPEN_WEBUI_APPROVED_MODELS=qwen2.5:32b-instruct,qwen2.5vl:72b,qwen3:30b-a3b,qwen3-coder-next:q4_K_M,gpt-oss:20b,gpt-oss-freyja:20b-analysis-prefill,gpt-oss:120b
OPEN_WEBUI_FALLBACK_MODELS=qwen2.5:7b
```

`DEFAULT_MODELS` only controls the initial Open WebUI default. Runtime model
choice belongs to Open WebUI; the proxy preserves the selected request model
and unloads other resident Vulcan models before forwarding chat.

The model proxy checks Vulcan first and Iris second. Iris fallback is only for
7B/12B-class active models installed on Iris.

When Freyja exposes an OpenAI-compatible gateway, switch `OPENAI_API_BASE_URL`
to that Atlas-local `/v1` endpoint.

Avoid `qwen3:30b-a3b` for normal Open WebUI chat until the reasoning-output
adapter is fixed. It can return text in an OpenAI-compatible `reasoning` field
with empty assistant `content`, which leaves Open WebUI showing little or no
answer.

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

If more than the intended model is resident, unload the unwanted model from
Vulcan before continuing.

For now, when ending an Open WebUI work session, leave the last active model
warm on Vulcan instead of unloading it immediately.

## Update

```bash
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml pull
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
```

The `open-webui` Docker volume preserves `/app/backend/data` across container
recreates.
