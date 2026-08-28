# Freyja Agent Gateway Compose

This compose target runs the Freyja agent gateway/runtime surface separately
from the legacy Director containers.

It exposes:

- LiteLLM OpenAI-compatible proxy on `${HOST}:4000`
- `GET /health`
- `POST /canonical/route`
- `POST /shortcuts/message`
- `GET /freyja3/inference/health`
- `POST /freyja3/memory`
- `GET /freyja3/memory`
- `POST /freyja3/memory/candidates`
- `GET /freyja3/memory/candidates`
- `POST /freyja3/memory/candidates/{candidate_id}/review`
- `POST /freyja3/machines/heartbeat`
- `GET /freyja3/machines`
- `GET /freyja3/audit`
- `POST /freyja3/workers/jobs`
- `GET /freyja3/workers/jobs`
- `POST /freyja3/workers/jobs/claim`
- `POST /freyja3/workers/jobs/{job_id}/complete`
- `POST /freyja3/schedules`
- `GET /freyja3/schedules`
- `POST /freyja3/schedules/dispatch-due`
- `POST /events/semantic`
- `GET /events/semantic`

Default behavior is conservative:

- binds to `0.0.0.0:8300` by default for LAN/Tailscale clients
- leaves live model calls disabled with `FREYJA3_INFERENCE_ENABLED=false`
- leaves live Apple Calendar disabled until `CALENDAR_DEFAULT_PROVIDER=apple`,
  `APPLE_CALENDAR_ENABLED=true`, and MacAgent credentials are configured
- starts a config-file LiteLLM proxy that exposes hardware-role model aliases
- uses Vulcan's Tailscale Ollama endpoint for readiness and future inference
- stores semantic events in `/app/data/freyja3_events.db`
- stores scoped memory and reviewable memory candidates in `/app/data/freyja3_memory.db`
- stores scheduler envelopes in `/app/data/freyja3_scheduler.db`
- stores machine role heartbeats in `/app/data/freyja3_machines.db`
- stores Mars/worker job envelopes in `/app/data/freyja3_workers.db`
- stores gateway/runtime audit events in `/app/data/freyja3_audit.db`
- points local read-only diagnostics at `/app`; it does not bind-mount the host
  Git checkout into the container by default

This target is intended for Atlas or Mars side-by-side validation before any
existing Director-compatible service is replaced.

## LiteLLM Proxy

The `litellm` service fronts Iris, Vulcan, and approved cloud providers behind
role-named aliases:

- `iris-fast`: Iris 7B-class local response/fallback model
- `vulcan-general`: Vulcan always-on 32B general Qwen model (`qwen2.5:32b-instruct`)
- `vulcan-coder`: Vulcan coding specialist
- `vulcan-vision`: Vulcan big multimodal visual/document model (`qwen2.5vl:72b`)
- `vulcan-embeddings`: Vulcan retrieval/memory embedding model
- `cloud-frontier`: policy-gated cloud escape hatch
- `vulcan`: backwards-compatible alias for `vulcan-general`
- `vulcan-deep`: explicit sleep-on-it reasoning alias for `qwen2.5vl:72b`
- `vulcan-lmstudio`: LM Studio path once a chat model is loaded there

```bash
docker compose --env-file deploy/compose/freyja3/.env -f deploy/compose/freyja3/compose.yaml up -d litellm
curl http://${HOST}:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"
curl http://${HOST}:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"vulcan-general","messages":[{"role":"user","content":"Say ready."}]}'
```

Set `IRIS_OLLAMA_BASE_URL` to Iris's Ollama server. Set
`VULCAN_OLLAMA_BASE_URL` to the Vulcan Ollama server. Set `VULCAN_OPENAI_BASE_URL`
to the Vulcan OpenAI-compatible server, including the `/v1` suffix. LM Studio
commonly uses `http://100.94.80.21:1234/v1`.

To let Freyja 3 select the LiteLLM gateway as an inference endpoint, set
`FREYJA3_INFERENCE_ENDPOINTS` to the LiteLLM example in `.env.example` and then
enable live calls with `FREYJA3_INFERENCE_ENABLED=true`.

## Machine Heartbeat Timer

`deploy/systemd/user/freyja3-machine-heartbeat.{service,timer}` installs a
user-level timer for hosts that should publish role/health observations to the
Atlas Freyja sidecar. The timer expects:

- checkout at `%h/freyja-os-freyja3`
- CLI installed at `%h/freyja-os-freyja3/.heartbeat-venv/bin/freyja3-machine-heartbeat`
- env file at `%h/.config/freyja/freyja3-machine-heartbeat.env`

Required env keys:

```text
FREYJA3_MACHINE_HEARTBEAT_URL=http://100.119.235.114:8300/freyja3/machines/heartbeat
FREYJA_CONNECTOR_TOKEN=...
FREYJA3_MACHINE_ID=mars
FREYJA3_MACHINE_ROLE=worker-ingestion-monitoring
```

## Worker Runner Timer

`deploy/systemd/user/freyja3-worker-runner.{service,timer}` installs a
user-level timer for Mars-style worker hosts. Each run claims at most one
Atlas-owned job envelope and completes implemented worker classes. Implemented
classes are:

- `monitoring`: lightweight host/job proof output
- `document_ingestion`: bounded text/path ingestion that returns a structured
  untrusted external-content observation, not direct memory or tool actions

Required env keys:

```text
FREYJA3_WORKER_BASE_URL=http://100.119.235.114:8300
FREYJA_CONNECTOR_TOKEN=...
FREYJA3_MACHINE_ID=mars
FREYJA3_WORKER_CLASS=monitoring
FREYJA3_WORKER_ALLOWED_ROOTS=/home/joe/freyja-os-freyja3/data/ingestion
```
