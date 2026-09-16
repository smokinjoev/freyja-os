# Open WebUI Placement

Decision: Open WebUI runs on Atlas.

Atlas is the always-on Freyja control-plane/infrastructure host, so it is the
right permanent home for a shared household Open WebUI instance. Iris is only
the Apple/Mac interaction host and workstation. Vulcan remains compute.

Policy: Open WebUI lists the approved model catalog. The backend enforces one resident Vulcan model at a time.

Planned model catalog:

| Role | Model |
| --- | --- |
| Hot daily/tool model | `qwen3.8:27b` |
| Vision daily driver | `qwen2.5vl:72b` |
| Fast general chat | `gpt-oss-freyja:20b-analysis-prefill` |
| Reasoning agent candidate | `qwen3:30b-a3b` |
| Coding | `qwen3-coder-next:q4_K_M` |
| GPT OSS small | `gpt-oss:20b` or `gpt-oss-freyja:20b-analysis-prefill` |
| GPT OSS large | `gpt-oss:120b` |

Open WebUI may show these models in its picker. The intentionally hot resident model is `qwen3.8:27b`; larger or specialized models stay available on demand but should not remain resident accidentally.

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

The `freyja-5` endpoint does not run live inference unless
`FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED=true` is set on the Freyja service with
`NEXUS_BASE_URL` and host secrets configured outside source control. Cloud
fallback remains disabled for this path.

Do not install separate Open WebUI servers on every client device. Other
devices should open the Atlas URL in a browser and optionally install it as a
PWA/Add to Home Screen.

Iris must not be used as the household Open WebUI host. If a compose project
named `freyja-open-webui-atlas` is found running on Iris, treat it as a
duplicate local stack and stop it after confirming Atlas is reachable. Host
identity comes from Tailscale/DNS and service reachability, not from the Docker
Compose project name alone.

Atlas deployment files live under:

```text
deploy/compose/open-webui/
```

The home-agent runbook, source-controlled agent definitions, scoped memory API,
backup inventory, and current blockers are tracked in:

```text
docs/operations/open-webui-home-agent.md
config/open-webui-home-agents.yaml
```

Default Atlas URL:

```text
http://100.119.235.114:3001
```

Initial provider target:

```text
OPENAI_API_BASE_URL=http://model-proxy:8080/v1
DEFAULT_MODELS=qwen2.5vl:72b
OPEN_WEBUI_APPROVED_MODELS=qwen3.8:27b,qwen2.5vl:72b,qwen3:30b-a3b,qwen3-coder-next:q4_K_M,gpt-oss:20b,gpt-oss-freyja:20b-analysis-prefill,gpt-oss:120b
OPEN_WEBUI_FALLBACK_MODELS=qwen2.5:7b
```

Long-running model timeout settings:

```text
AIOHTTP_CLIENT_TIMEOUT=1800
AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST=15
AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST=15
```

`DEFAULT_MODELS` only controls the initial Open WebUI default. Runtime model choice belongs to Open WebUI; the proxy preserves the selected request model and unloads other resident Vulcan models before forwarding chat.

Vulcan policy: Ollama is the canonical model runtime. Msty Nexus is the stable
preset/routing layer over Ollama, not a second model source of truth. Ollama is
configured for one loaded model and one parallel request, with qwen3.8 warmed
by `freyja-hot-model-warm.timer`. The Ollama context cap is `16384` for normal
serving so OpenAI-compatible calls do not accidentally allocate the full 262k
context. Vulcan exposes an AMD Strix/Krackan/Strix Halo NPU at `/dev/accel0`
with the `amdxdna` driver, but normal LLM serving remains on the Radeon GPU.

Current endpoint map:

| Surface | Endpoint | Purpose |
| --- | --- | --- |
| Atlas Open WebUI | `http://100.119.235.114:3001` | Household UI |
| Atlas model proxy | `http://model-proxy:8080/v1` | Open WebUI provider boundary |
| Vulcan Ollama native | `http://100.94.80.21:11434` | Canonical model runtime and loaded-model state |
| Vulcan Ollama OpenAI | `http://100.94.80.21:11434/v1` | Direct OpenAI-compatible diagnostic path |
| Vulcan Ollama TCP proxy | `http://100.94.80.21:8088/v1` | Open WebUI/model-proxy primary upstream |
| Vulcan Nexus | `http://100.94.80.21:3939/v1` | Stable preset/routing layer over Ollama |
| Iris fallback Ollama | `http://100.115.228.56:11434/v1` | 7B-class fallback only |

Current Nexus presets:

| Preset | Model |
| --- | --- |
| `@preset/freyja-fast-local` | `external-ollama/gpt-oss:20b` |
| `@preset/freyja-strong-local` | `external-ollama/qwen3.8:27b` |
| `@preset/freyja-private-local` | `external-ollama/qwen3.8:27b` |
| `@preset/freyja-coder` | `external-ollama/qwen3.8:27b` |
| `@preset/benedict-paralegal-local` | `external-ollama/qwen3.8:27b` |
| `@preset/freyja-vision-docs` | `external-ollama/qwen2.5vl:72b` |

The model proxy checks Vulcan first and Iris second. Iris fallback is only for
7B/12B-class active models installed on Iris.

When the Freyja 5.0 gateway is ready for live Open WebUI traffic, switch Open
WebUI to the Atlas-local Freyja `/v1` endpoint and select `freyja-5`.

For Freyja Core v0.1 testing, keep the existing Open WebUI provider pointed at
`http://model-proxy:8080/v1` and expose only the opt-in `freyja-core` model
through the proxy:

```text
OPEN_WEBUI_FREYJA_CORE_BASE_URL=http://100.115.228.56:8510/v1
OPEN_WEBUI_FREYJA_CORE_API_KEY=not-needed
OPEN_WEBUI_FREYJA_CORE_MODELS=freyja-core
```

Do not set `DEFAULT_MODELS=freyja-core` until the test profile has been
validated. Existing Vulcan/Open WebUI models remain the default path.

Msty Go can reach the same Core directly over Tailscale with an
OpenAI-compatible provider:

```text
Base URL: http://100.115.228.56:8510/v1
Model: freyja-core
API key: not-needed
```

Use Ollama on Vulcan as the canonical model runtime. Keep Msty Nexus as the stable preset and routing layer over Ollama; Core may call Nexus presets, but physical model residency and health are verified through Ollama.

The model proxy includes a narrow non-streaming reasoning-output adapter. If an
upstream returns empty assistant `content` with useful text in an
OpenAI-compatible `reasoning` field, the proxy promotes that text to visible
content so Open WebUI does not render a blank answer.

Change procedure:

```bash
cd /home/joe/freyja-os
sed -i 's/^DEFAULT_MODELS=.*/DEFAULT_MODELS=<model-id>/' deploy/compose/open-webui/.env
docker compose --env-file deploy/compose/open-webui/.env \
  -f deploy/compose/open-webui/compose.yaml up -d
curl http://100.94.80.21:8088/api/ps
```

After using a model, verify Vulcan has only the intended model resident. If
another model remains loaded, or qwen3.8 is not restored as the hot resident
model after normal use, unload the unwanted model and rerun the hot-model
warmer before continuing.

For now, when ending an Open WebUI work session, leave the last active model
warm on Vulcan instead of unloading it immediately.
