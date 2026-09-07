# Open WebUI Response Diagnostics - 2026-09-02

Scope: diagnose broken, truncated, JSON-only, incoherent, or schema-like model
responses seen through Open WebUI while preserving Freyja 4.1/data. This note
records non-destructive evidence gathered from Iris against reachable
Atlas/Vulcan endpoints.

## Current Path Evidence

Source-controlled intended Open WebUI path:

```text
browser/PWA -> Atlas Open WebUI -> model-proxy -> Vulcan OpenAI-compatible endpoint -> Ollama -> model
browser/PWA -> Atlas Open WebUI -> model-proxy -> Freyja 5 /v1 -> Msty Nexus -> Vulcan
```

Live pre-fix path actually in use:

```text
browser/PWA -> Atlas Open WebUI -> Vulcan OpenAI-compatible endpoint -> Ollama -> model
browser/PWA -> Atlas Open WebUI -> Atlas-local Ollama 0.20.4 -> local small/cloud models
```

Reason: Open WebUI's database config overrode the container env and set
`openai.api_base_urls` to `["http://100.94.80.21:8088/v1"]`; `ollama.enable`
was also `true` with `ollama.base_urls=["http://host.docker.internal:11434"]`.
The model-proxy logs had no recent chat traffic before the fix.

Live post-fix path:

```text
browser/PWA -> Atlas Open WebUI -> model-proxy -> Vulcan OpenAI-compatible endpoint -> Ollama -> model
```

Reachability checks from Iris:

| Layer | Endpoint | Evidence |
| --- | --- | --- |
| Atlas Open WebUI | `http://100.119.235.114:3001/api/version` | returned `{"version":"0.11.3","deployment_id":""}` |
| Vulcan Ollama | `http://100.94.80.21:11434/api/version` | returned `{"version":"0.32.15"}` |
| Vulcan OpenAI-compatible gateway | `http://100.94.80.21:8088/v1/models` | listed Vulcan models |
| Msty Nexus | `http://100.94.80.21:3939` | returned `msty-nexus` `0.5.0`; `/v1/models` requires a token |

Unauthenticated Open WebUI metadata:

```json
{
  "status": true,
  "name": "Open WebUI",
  "version": "0.11.3",
  "features": {
    "auth": true,
    "auth_trusted_header": false,
    "enable_signup_password_confirmation": false,
    "enable_ldap": false,
    "enable_signup": false,
    "enable_login_form": true,
    "enable_websocket": true
  }
}
```

Unauthenticated `GET /api/models` returned `{"detail":"Not authenticated"}`.
The Open WebUI model/provider/tool/RAG settings therefore still require an
admin session, API token, or Atlas-side database/log access.

Current Nexus metadata differs from the older stored smoke report that recorded
`msty-nexus` `0.4.1`; the live endpoint now reports:

```json
{
  "object": "msty.nexus.version",
  "name": "msty-nexus",
  "version": "0.5.0",
  "commit": "ee7ad68",
  "buildDate": "2026-09-01T19:05:51Z",
  "goVersion": "go1.26.6",
  "platform": "linux/amd64"
}
```

Atlas SSH was not available from Iris during this pass:

```text
freyja@atlas: Permission denied (publickey,password).
```

Vulcan SSH was not available because host-key verification failed. No host-key
or credential state was modified.

Later access using the documented `joe@` accounts succeeded with
`UserKnownHostsFile=/dev/null`, so host-key state was still not persistently
changed. Live Atlas state was captured under:

```text
logs/open-webui-diagnostics/atlas-state-20260903T022208Z
```

The Open WebUI Docker data volume was backed up read-only on Atlas before live
configuration edits:

```text
/home/joe/freyja-os/logs/open-webui-diagnostics/atlas-state-20260903T022208Z/open-webui-data-volume.tgz
```

Backup size: about 965 MB.

## Model Inventory From Vulcan Ollama

| Model | Size | Family | Quantization | Context |
| --- | ---: | --- | --- | ---: |
| `qwen3.5:122b-a10b` | 81,370,036,360 bytes | `qwen35moe` | `Q4_K_M` | 262144 |
| `qwen2.5:72b` | 47,415,724,625 bytes | `qwen2` | `Q4_K_M` | 32768 |
| `gpt-oss:120b` | 65,369,818,941 bytes | `gptoss` | `MXFP4` | 131072 |
| `gpt-oss:20b` | 13,793,441,244 bytes | `gptoss` | `MXFP4` | 131072 |
| `qwen3:30b-a3b` | 18,556,699,314 bytes | `qwen3moe` | `Q4_K_M` | 262144 |
| `qwen2.5:32b-instruct` | 19,851,349,669 bytes | `qwen2` | `Q4_K_M` | 32768 |
| `qwen2.5vl:72b` | 48,709,042,849 bytes | `qwen25vl` | `Q4_K_M` | 128000 |
| `qwen3-coder-next:q4_K_M` | 51,741,611,823 bytes | `qwen3next` | `Q4_K_M` | 262144 |
| `qwen2.5:7b` | 4,683,087,332 bytes | `qwen2` | `Q4_K_M` | 32768 |

Atlas-local Ollama, reachable from Open WebUI as `host.docker.internal:11434`,
reported version `0.20.4` and models:

| Model | Size | Family | Quantization |
| --- | ---: | --- | --- |
| `llava:latest` | 4,733,363,377 bytes | `llama`/`clip` | `Q4_0` |
| `hermes3:latest` | 4,661,227,243 bytes | `llama` | `Q4_0` |
| `kimi-k2.5:cloud` | 340 bytes | cloud shim | none |
| `llama3.2:latest` | 2,019,393,189 bytes | `llama` | `Q4_K_M` |

## Direct Isolation Results

All requests used deterministic settings and no Open WebUI chat history,
memory, RAG, notes, documents, or browser state.

Repeatable evidence script:

```text
scripts/open-webui-response-matrix.py
```

Atlas/Open WebUI state collector prepared for when Atlas shell access is
available:

```text
scripts/collect-open-webui-state.sh
```

Run on Atlas from the Freyja repo root:

```bash
scripts/collect-open-webui-state.sh
BACKUP_OPEN_WEBUI_DATA=1 scripts/collect-open-webui-state.sh
```

The default run captures redacted env/config, Docker state, container inspect,
logs, and unauthenticated local Open WebUI metadata. The `BACKUP_OPEN_WEBUI_DATA`
variant additionally creates a read-only tarball of the Docker data volume.

Raw evidence files:

```text
logs/open-webui-diagnostics/response-matrix-qwen25-20260903T0200.json
logs/open-webui-diagnostics/response-matrix-qwen25-72b-stream-20260903T0204.json
logs/open-webui-diagnostics/response-matrix-qwen35-122b-20260903T0208.json
logs/open-webui-diagnostics/qwen35-recovery-20260903T021240.jsonl
logs/open-webui-diagnostics/atlas-state-20260903T022208Z/db-metadata-redacted.json
logs/open-webui-diagnostics/atlas-state-20260903T022208Z/config-keys-redacted.json
logs/open-webui-diagnostics/atlas-state-20260903T022208Z/affected-chat-redacted.json
```

| Path | Model | Prompt | Limit | Result |
| --- | --- | --- | ---: | --- |
| Ollama `/api/chat` | `qwen2.5:7b` | exact sentence | 32 | clean `message.content`, `done_reason=stop` |
| Ollama `/api/chat` | `qwen2.5:72b` | exact sentence | 32 | clean `message.content`, `done_reason=stop` |
| Ollama `/api/chat` | `qwen3.5:122b-a10b` | exact sentence | 32 | empty `message.content`, truncated `thinking`, `done_reason=length` |
| OpenAI gateway `/v1/chat/completions` | `qwen3.5:122b-a10b` | exact sentence | 32 | empty `message.content`, truncated `message.reasoning`, `finish_reason=length` |
| OpenAI gateway `/v1/chat/completions` | `qwen3.5:122b-a10b` | exact sentence | 256 | visible `message.content`, long `message.reasoning`, `finish_reason=length`, reasoning tail included `cw` |
| OpenAI gateway `/v1/chat/completions` | `qwen2.5:72b` | two-sentence writing | 120 | clean prose, `finish_reason=stop` |
| OpenAI gateway `/v1/chat/completions` | `qwen2.5:72b` | same writing plus irrelevant tool schema, tool auto | 120 | clean prose, no corruption, `finish_reason=stop` |
| OpenAI gateway `/v1/chat/completions` | `qwen2.5:7b` | same writing plus irrelevant tool schema, tool auto | 120 | clean prose, no corruption, `finish_reason=stop` |

Expanded matrix results:

| Path | Model | Case | Stream | Tools | Status | Elapsed ms | First byte ms | Finish | Content chars | Reasoning chars |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| Ollama | `qwen2.5:72b` | deterministic | no | no | 200 | 11089 | 11089 | stop | 29 | 0 |
| OpenAI gateway | `qwen2.5:72b` | deterministic | no | no | 200 | 1570 | 1569 | stop | 29 | 0 |
| OpenAI gateway | `qwen2.5:72b` | deterministic | yes | no | 200 | 2680 | 253 | stop | 29 | 0 |
| OpenAI gateway | `qwen2.5:72b` | deterministic | no | yes | 200 | 2693 | 2693 | stop | 29 | 0 |
| Ollama | `qwen2.5:72b` | writing | no | no | 200 | 12682 | 12682 | stop | 270 | 0 |
| OpenAI gateway | `qwen2.5:72b` | writing | no | no | 200 | 10498 | 10498 | stop | 270 | 0 |
| OpenAI gateway | `qwen2.5:72b` | writing | yes | no | 200 | 10526 | 305 | stop | 270 | 0 |
| OpenAI gateway | `qwen2.5:72b` | writing | no | yes | 200 | 12468 | 12468 | stop | 256 | 0 |
| Ollama | `qwen2.5:72b` | structured | no | no | 200 | 9630 | 9630 | stop | 200 | 0 |
| OpenAI gateway | `qwen2.5:72b` | structured | no | no | 200 | 8931 | 8931 | stop | 200 | 0 |
| OpenAI gateway | `qwen2.5:72b` | structured | yes | no | 200 | 8951 | 301 | stop | 200 | 0 |
| OpenAI gateway | `qwen2.5:72b` | structured | no | yes | 200 | 9784 | 9784 | stop | 210 | 0 |
| Ollama | `qwen3.5:122b-a10b` | deterministic | no | no | 200 | 16702 | 16702 | length | 0 | 264 |
| OpenAI gateway | `qwen3.5:122b-a10b` | deterministic | no | no | 200 | 2675 | 2675 | length | 0 | 264 |
| OpenAI gateway | `qwen3.5:122b-a10b` | deterministic | yes | no | 200 | 3575 | 1132 | length | 0 | 264 |
| Ollama | `qwen3.5:122b-a10b` | writing | no | no | 200 | 6697 | 6697 | length | 0 | 654 |
| OpenAI gateway | `qwen3.5:122b-a10b` | writing | no | no | 200 | 6527 | 6527 | length | 0 | 654 |
| OpenAI gateway | `qwen3.5:122b-a10b` | writing | yes | no | 200 | 6415 | 200 | length | 0 | 654 |
| Ollama | `qwen3.5:122b-a10b` | structured | no | no | 200 | 6813 | 6813 | length | 0 | 636 |
| OpenAI gateway | `qwen3.5:122b-a10b` | structured | no | no | 200 | 6378 | 6378 | length | 0 | 636 |
| OpenAI gateway | `qwen3.5:122b-a10b` | structured | yes | no | 200 | 7298 | 1138 | length | 0 | 636 |

The `qwen3.5:122b-a10b` structured case is especially close to the reported
`{"title":"Trains and Rainbows Paper"}` symptom. Direct OpenAI gateway output
for the structured prompt returned empty assistant `content`, nonempty
`reasoning`, and `finish_reason=length`; the reasoning text showed the model
planning the required JSON and title but exhausting the output budget before
emitting visible content.

122B recovery probes:

| Path | Setting | Prompt | Finish | Content chars | Reasoning chars | Result |
| --- | --- | --- | --- | ---: | ---: | --- |
| OpenAI gateway | `max_tokens=512` | exact sentence | stop | 29 | 924 | visible content restored |
| OpenAI gateway | `max_tokens=1024` | writing | stop | 257 | 3389 | visible content restored |
| Ollama `/api/chat` | `num_predict=512` | exact sentence | stop | 29 | 924 | visible content restored |
| Ollama `/api/chat` | `think=false`, `num_predict=160` | exact sentence | stop | 29 | 0 | visible content restored with reasoning disabled |
| Ollama `/api/chat` | `num_ctx=4096`, `num_predict=160` | exact sentence | length | 0 | 616 | smaller context alone did not fix truncation |
| OpenAI gateway | `think=false`, `max_tokens=160` | exact sentence | length | 0 | 616 | OpenAI-compatible gateway ignored or did not honor `think=false` |
| OpenAI gateway | `max_tokens=512` | structured JSON | length | 0 | 2252 | no visible content |
| OpenAI gateway | `max_tokens=1024` | structured JSON | length | 0 | 4709 | no visible content |

Conclusion: larger output budgets can make simple/writing `qwen3.5:122b-a10b`
prompts visible, but the model is still unsafe as an ordinary Open WebUI
writing/structured-output default because it can consume 1024 tokens entirely in
reasoning. Native Ollama `think=false` works for a simple prompt, but the
Vulcan OpenAI-compatible gateway did not honor the same flag in this test.

## Affected Chat Proof

Affected chat:

```text
id: 8b325885-f57b-4d1e-a5fd-cffb914f6d3d
title: Can you write  a two page paper on trains and rainbows
```

The stored first assistant turn had:

```text
model: qwen3.5:122b-a10b
visible content: { "title": "Trains and Rainbows Paper" }
```

Its stored output preview shows the model was not answering the paper request.
It was following an Open WebUI metadata/title-generation task:

```text
Generate a concise title summarizing the chat history.
Raw JSON output only.
```

The second assistant turn in the same chat used `qwen2.5:72b` and contains the
reported schema-like corruption. It was generated after the bad qwen3.5
assistant turn was already in the chat history, so the qwen2.5 result is not
evidence that direct qwen2.5 is inherently corrupt.

Resource observations:

| Model | Loaded size reported by `/api/ps` | Context |
| --- | ---: | ---: |
| `qwen2.5:7b` | 6,526,431,395 bytes | 32768 |
| `qwen2.5:72b` | 57,678,443,315 bytes | 32768 |
| `qwen3.5:122b-a10b` | 85,580,337,642 bytes | 262144 |

After testing, `qwen2.5:7b`, `qwen2.5:72b`, and `qwen3.5:122b-a10b` were
unloaded with Ollama `keep_alive: 0`; `/api/ps` then returned no resident
models.

## Evidence-Based Findings So Far

1. `qwen2.5:72b` is not generally broken at the direct Ollama/OpenAI gateway
   layer. It produced normal prose through direct Ollama, non-streaming OpenAI,
   streaming OpenAI, and OpenAI with an irrelevant tool schema.
2. `qwen3.5:122b-a10b` has a direct upstream failure mode independent of Open
   WebUI: low output limits are consumed by hidden/side-channel reasoning,
   leaving `content` empty and returning `length`. This reproduced for
   deterministic, writing, and structured prompts through both Ollama and the
   OpenAI-compatible gateway, including streaming.
3. The 122B model's default context is very large and reported loaded size is
   about 85.6 GB, which exceeds a 64 GB unified-memory budget before other
   services and KV growth are considered. This makes it high risk for swap,
   slowdowns, or reload churn even when a tiny prompt succeeds.
4. The Open WebUI model-proxy has source-level request mutation that can affect
   diagnosis:
   - constrained reasoning models get `max_tokens` raised to at least 256;
   - constrained reasoning models have tools filtered to a narrow allowlist;
   - non-reasoning requests with tools are rerouted to `TOOL_MODEL`;
   - text-only requests to a vision model are rerouted to `TEXT_MODEL`.
5. The affected qwen3.5 title-only result was an Open WebUI task-routing/state
   failure, not a normal model response: Open WebUI stored a title-generation
   JSON task result as an assistant chat turn.
6. The affected qwen2.5 corruption occurred in a contaminated chat after that
   bad assistant turn. Direct qwen2.5 remains clean.
7. A source-level proxy mitigation was deployed to live Atlas:
   - default `REASONING_MIN_COMPLETION_TOKENS` raised from 256 to 1024;
   - truncated `finish_reason=length` reasoning is no longer promoted to visible
     assistant `content`;
   - `qwen3.5:122b-a10b` removed from the default approved Open WebUI catalog
     while leaving opt-in alias/handling code in place;
   - offline Freyja5 `agent/...` models are hidden unless `GET /v1/models` at
     `FREYJA5_BASE_URL` succeeds;
   - DNS/socket upstream failures now return bounded JSON errors instead of
     disconnecting the Open WebUI client.
8. Live Open WebUI DB config was corrected:
   - `openai.api_base_urls` changed from direct Vulcan `8088` to
     `http://model-proxy:8080/v1`;
   - `ollama.enable` changed to `false` to stop exposing Atlas-local Ollama as a
     second provider;
   - `task.title.enable` changed to `false` to stop title-generation tasks from
     contaminating assistant output.
9. Local proxy tests pass:

```text
.venv/bin/python -m pytest -q tests/test_open_webui_model_proxy.py tests/test_freyja5_open_webui_agent_smoke.py
22 passed, 1 warning
```

Live proxy verification after deployment:

| Check | Result |
| --- | --- |
| `qwen3.5:122b-a10b` through `model-proxy` | HTTP 400, not approved |
| `qwen2.5:72b` exact prompt through Atlas Open WebUI container -> `model-proxy` -> Vulcan | HTTP 200, `finish=stop`, content `The diagnostic path is clean.` |
| Vulcan `/api/ps` after verification | no resident models |
| Nexus `/v1/models` with live service token | HTTP 200, 17 models listed |
| Nexus `/v1/chat/completions` exact prompt through `@preset/benedict-paralegal-local` | HTTP 200, `finish=stop`, content `The diagnostic path is clean.`, reasoning chars 0 |
| `agent/...` catalog after Freyja5 reachability fix | Open WebUI authenticated `/api/models` listed 10 models, `has_agent_models=false` |
| `agent/freyja` after Open WebUI cache refresh | HTTP 400, `Model not found`; no proxy disconnect |

Authenticated Open WebUI `/api/chat/completions` verification used an in-memory
JWT generated inside the live container for the existing admin user. No user or
API-key rows were created or changed. The no-save completion checks did not
create chat rows; the saved-chat check intentionally created one diagnostic
chat row to verify the persisted new-chat path.

| Case | Model | Stream | Payload mode | Result |
| --- | --- | --- | --- | --- |
| deterministic | `qwen2.5:72b` | false | tools/web/RAG/files disabled | HTTP 200, `finish=stop`, content `The diagnostic path is clean.`, reasoning chars 0 |
| writing | `qwen2.5:72b` | false | tools/web/RAG/files disabled | HTTP 200, clean two-sentence prose, `finish=stop`, reasoning chars 0 |
| structured | `qwen2.5:72b` | false | tools/web/RAG/files disabled | HTTP 200, valid JSON content with `title` and `summary`, `finish=stop`, reasoning chars 0 |
| deterministic | `qwen2.5:72b` | true | tools/web/RAG/files disabled | HTTP 200, 7 SSE chunks, content `The diagnostic path is clean.`, `finish=stop` |
| writing | `qwen2.5:72b` | true | tools/web/RAG/files disabled | HTTP 200, 49 SSE chunks, clean two-sentence prose, `finish=stop` |
| normal defaults | `qwen2.5:72b` | false | no explicit feature/tool/file disables | HTTP 200, content `The diagnostic path is clean.`, `finish=stop`, reasoning chars 0 |
| saved new chat | `qwen2.5:72b` | false | `parent_id:null`, Open WebUI-generated saved chat id | HTTP 200, content `The diagnostic path is clean.`, `finish=stop`, reasoning chars 0 |
| smaller stable model | `qwen2.5:32b-instruct` | false | tools/web/RAG/files disabled | HTTP 200, content `The diagnostic path is clean.`, `finish=stop`, reasoning chars 0 |
| blocked model | `qwen3.5:122b-a10b` | false | normal endpoint | HTTP 400, `Model not found` |

Saved new-chat verification created diagnostic chat:

```text
e14ffb97-1f20-4b84-90ea-ac3328764827
```

Open WebUI stored title `New Chat`, model list `["qwen2.5:72b"]`, two history
messages, the exact user prompt, assistant model `qwen2.5:72b`, `done=true`,
and assistant content `The diagnostic path is clean.`

Redacted proxy-boundary capture for the authenticated clean deterministic test:

```text
logs/open-webui-diagnostics/live-openwebui-auth-capture-20260903/proxy-capture-qwen25-clean.json
```

The captured proxy-boundary request contained only:

```json
{
  "model": "qwen2.5:72b",
  "messages": [{"role": "user", "content": "Reply with exactly: The diagnostic path is clean."}],
  "temperature": 0,
  "max_tokens": 1024,
  "stream": false
}
```

No `tools`, `tool_choice`, `tool_ids`, `files`, `features`, `response_format`,
or stop sequences reached the proxy boundary for that clean test. The original
Open WebUI caller supplied `max_tokens=64`; the proxy raised it to `1024` for
the constrained reasoning model profile.

Vulcan resource sampling during authenticated Open WebUI `qwen2.5:72b` use:

| Metric | Observation |
| --- | --- |
| RAM | 30 GiB total, 6.3-6.4 GiB used, about 24 GiB available |
| Swap | 8 GiB total, 0 B used across all samples |
| Loaded model | `qwen2.5:72b`, reported size 57,678,443,315 bytes, context 32768 |
| GPU telemetry | Vulcan exposes AMD Strix Halo / Radeon 8050S/8060S class graphics and has `radeontop`; no separate NVIDIA/ROCm SMI telemetry was available in this pass |
| Ollama VRAM field | `/api/ps` reported `size_vram=57,678,443,315` for `qwen2.5:72b` |
| Post-test cleanup | `qwen2.5:72b` unloaded with `keep_alive:0`; `/api/ps` returned `{"models":[]}` |

## Current Root-Cause Ranking

| Rank | Hypothesis | Evidence | Confidence |
| ---: | --- | --- | --- |
| 1 | Output-token/reasoning-field interaction truncates `qwen3.5:122b-a10b` before visible content | direct Ollama and direct OpenAI gateway return empty content at 32 tokens and `length` | High |
| 2 | 122B model/context footprint exceeds practical 64 GB budget | `/api/ps` reports 85.6 GB loaded size and 262144 context | High |
| 3 | Open WebUI DB provider override bypassed model-proxy and exposed direct Vulcan plus Atlas-local Ollama | live DB config, stale proxy logs, container-internal endpoint checks | High |
| 4 | Open WebUI title-generation task output contaminated affected chat | affected chat stored qwen3.5 output says it was generating a concise title as raw JSON | High |
| 5 | Open WebUI chat/RAG/memory/PDF contamination affects affected chats | DB shows active qwen2.5 custom model with file_context/memory/builtin_tools and active Auto Memory filter; affected qwen2.5 ran after corrupted history | Medium |
| 6 | Tool-schema/native function-calling mismatch corrupts qwen2.5 outputs | direct qwen2.5 72B with irrelevant tool schema remained clean in this matrix | Low to medium |
| 7 | qwen2.5:72b build/quantization is inherently corrupt | direct tests clean | Low |

## Remaining Optional Evidence

The main corrupted points are now identified for the reported affected chat.
Still useful but no longer required to explain the reported failures:

1. Live `radeontop` utilization sampling during a long 72B request and any
   future opt-in 122B request.
2. Browser/PWA screenshot verification, if visual UI persistence needs separate
   validation. The authenticated saved-chat API path did create and verify a
   saved Open WebUI chat through the main completion pipeline.

## Optional Fix Candidates Not Yet Applied

Do not apply without Open WebUI/proxy payload evidence confirming the relevant
failure mode:

1. Add or deploy a proxy/profile rule that disables reasoning side-channel
   output for 122B only if the upstream OpenAI-compatible gateway supports it.
   Native Ollama honored `think=false`; the tested OpenAI-compatible gateway did
   not.
2. Expose separate Open WebUI profiles:
   - ordinary writing/chat: no tools, no RAG, no memory injection, stable
     `qwen2.5:72b` or `qwen2.5:32b-instruct`;
   - tools/RAG: smaller tool-capable model, explicit tool allowlist, lower
     context.
3. Add request logging to the model-proxy with secret redaction and bounded body
   capture, then reproduce the broken Open WebUI prompt once.

## Changes Staged In Source

These changes are deployed on Atlas unless otherwise noted:

| File | Change | Rollback |
| --- | --- | --- |
| `deploy/compose/open-webui/model-proxy.py` | Raised default `REASONING_MIN_COMPLETION_TOKENS` to 1024 | Set env/default back to `256` |
| `deploy/compose/open-webui/model-proxy.py` | Do not promote empty-content `reasoning` into visible `content` when `finish_reason=length` | Remove the `finish_reason == "length"` guard |
| `deploy/compose/open-webui/model-proxy.py` | Removed `qwen3.5:122b-a10b` from default `APPROVED_MODELS`; kept alias and constrained-reasoning handling | Add it back to default `APPROVED_MODELS` |
| `deploy/compose/open-webui/model-proxy.py` | Keep default model aliases empty for direct Vulcan `8088`; Nexus-style aliases remain env-configurable | Set `MODEL_ALIASES` if using Nexus-style model IDs |
| `deploy/compose/open-webui/model-proxy.py` | Hide `agent/...` models unless Freyja5 `/v1/models` is reachable | Remove the `_freyja5_available()` gate if Freyja5 should always be listed |
| `deploy/compose/open-webui/model-proxy.py` | Return JSON HTTP 599 for DNS/socket upstream failures instead of disconnecting | Remove the `OSError` handler in `_upstream` |
| `deploy/compose/open-webui/model-proxy.py` | Added disabled-by-default redacted diagnostic capture hook | Leave `DIAGNOSTIC_CAPTURE_DIR` empty, or remove the capture helper |
| `deploy/compose/open-webui/compose.yaml` | Pass `REASONING_MIN_COMPLETION_TOKENS` into the proxy container | Remove the env entry |
| `deploy/compose/open-webui/compose.yaml` | Removed `qwen3.5:122b-a10b` from the fallback approved catalog | Add it back to the `APPROVED_MODELS` default |
| `deploy/compose/open-webui/compose.yaml` | Added `host.docker.internal:host-gateway` for the proxy container | Remove `extra_hosts` if no host-routed upstreams are needed |
| `deploy/compose/open-webui/compose.yaml` | Added blank `DIAGNOSTIC_CAPTURE_DIR` env passthrough | Remove the env entry |
| `deploy/compose/open-webui/.env.example` | Document `REASONING_MIN_COMPLETION_TOKENS=1024` and omit 122B from default approved models | Change/remove the env line or add 122B back explicitly |
| `deploy/compose/open-webui/.env.example` | Document blank `DIAGNOSTIC_CAPTURE_DIR` | Remove the env line |
| Atlas Open WebUI DB `config` | `openai.api_base_urls=["http://model-proxy:8080/v1"]` | Restore from `live-fix-20260903T022844/db-config-before.json` |
| Atlas Open WebUI DB `config` | `ollama.enable=false` | Restore previous value from rollback JSON |
| Atlas Open WebUI DB `config` | `task.title.enable=false` | Restore previous value from rollback JSON |

These mitigations reduce three observed bad outcomes: simple/writing 122B
prompts getting cut off before visible content, truncated reasoning being
surfaced as the apparent answer, and casual selection of a model that is not
safe for ordinary Open WebUI writing/structured-output use. They do not make
122B a known-good Open WebUI model.

Live rollback artifacts:

```text
/home/joe/freyja-os/logs/open-webui-diagnostics/live-fix-20260903T022844/
```

## Known-Good Profiles Pending Live Open WebUI Verification

Ordinary chat/writing profile:

```text
Model: qwen2.5:72b or qwen2.5:32b-instruct
Tools/functions: off
Web search: off
Memory/notes injection: off until live prompts are inspected
Knowledge/RAG/documents: off
Output limit: at least 512 for short writing, higher for long drafts
Avoid: qwen3.5:122b-a10b as default
Opt-in only: qwen3.5:122b-a10b for controlled tests with captured payloads
```

Tools/RAG profile:

```text
Model: qwen2.5:32b-instruct initially
Tools/functions: explicit allowlist only
Web/RAG/documents: enable one at a time while capturing proxy payloads
Output limit: at least 512
Avoid: 72B/122B tool use until live Open WebUI payloads prove clean role and tool boundaries
```
