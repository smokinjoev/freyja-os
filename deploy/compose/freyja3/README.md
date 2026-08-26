# Freyja 3 Agent Gateway Compose

This compose target runs the Freyja 3 agent gateway/runtime surface separately
from the legacy Director containers.

It exposes:

- `GET /health`
- `POST /canonical/route`
- `GET /freyja3/inference/health`
- `POST /events/semantic`
- `GET /events/semantic`

Default behavior is conservative:

- binds to `127.0.0.1:8300`
- leaves live model calls disabled with `FREYJA3_INFERENCE_ENABLED=false`
- uses Vulcan's Tailscale Ollama endpoint for readiness and future inference
- stores semantic events in `/app/data/freyja3_events.db`

This target is intended for Atlas or Mars side-by-side validation before any
existing Director-compatible service is replaced.
