# Freyja 3 Agent Gateway Compose

This compose target runs the Freyja 3 agent gateway/runtime surface separately
from the legacy Director containers.

It exposes:

- `GET /health`
- `POST /canonical/route`
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

- binds to `127.0.0.1:8300`
- leaves live model calls disabled with `FREYJA3_INFERENCE_ENABLED=false`
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

## Machine Heartbeat Timer

`deploy/systemd/user/freyja3-machine-heartbeat.{service,timer}` installs a
user-level timer for hosts that should publish role/health observations to the
Atlas Freyja 3 sidecar. The timer expects:

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
