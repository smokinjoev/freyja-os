# Open WebUI Placement

Decision: Open WebUI runs on Atlas.

Atlas is the always-on Freyja control-plane/infrastructure host, so it is the
right permanent home for a shared household Open WebUI instance. Iris is only
the Apple/Mac interaction host and workstation. Vulcan remains compute.

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

Intended topology:

```text
phones/laptops/tablets browser or PWA
  -> Open WebUI on Atlas
  -> Vulcan OpenAI-compatible endpoint
```

Freyja remains the Atlas control plane. Main Freyja Director is healthy on
Atlas. Freyja 5.0 exposes an opt-in OpenAI-compatible `freyja-5` model for
Gateway/runtime skeleton testing, but the production Open WebUI default remains
the local `model-proxy` until live Nexus/Vulcan readiness is validated.

Do not install separate Open WebUI servers on every client device. Other
devices should open the Atlas URL in a browser and optionally install it as a
PWA/Add to Home Screen.

Atlas deployment files live under:

```text
deploy/compose/open-webui/
```

Default Atlas URL:

```text
http://100.119.235.114:3001
```

Initial provider target:

```text
OPENAI_API_BASE_URL=http://model-proxy:8080/v1
DEFAULT_MODELS=qwen2.5vl:72b
OPEN_WEBUI_APPROVED_MODELS=qwen2.5:32b-instruct,qwen2.5vl:72b,qwen3:30b-a3b,qwen3-coder-next:q4_K_M,gpt-oss:20b,gpt-oss-freyja:20b-analysis-prefill,gpt-oss:120b
OPEN_WEBUI_FALLBACK_MODELS=qwen2.5:7b
```

Long-running model timeout settings:

```text
AIOHTTP_CLIENT_TIMEOUT=1800
AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST=15
AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST=15
```

`DEFAULT_MODELS` only controls the initial Open WebUI default. Runtime model choice belongs to Open WebUI; the proxy preserves the selected request model and unloads other resident Vulcan models before forwarding chat.

The model proxy checks Vulcan first and Iris second. Iris fallback is only for
7B/12B-class active models installed on Iris.

When the Freyja 5.0 gateway is ready for live Open WebUI traffic, switch Open
WebUI to the Atlas-local Freyja `/v1` endpoint and select `freyja-5`.

Avoid `qwen3:30b-a3b` for normal Open WebUI chat until the reasoning-output
adapter is fixed. It can return text in an OpenAI-compatible `reasoning` field
with empty assistant `content`, which leaves Open WebUI showing little or no
answer.

Change procedure:

```bash
cd /home/joe/freyja-os
sed -i 's/^DEFAULT_MODELS=.*/DEFAULT_MODELS=<model-id>/' deploy/compose/open-webui/.env
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
curl http://100.94.80.21:8088/api/ps
```

After using a model, verify Vulcan has only the selected model resident. If
another model remains loaded, unload it on Vulcan before continuing.

For now, when ending an Open WebUI work session, leave the last active model
warm on Vulcan instead of unloading it immediately.
