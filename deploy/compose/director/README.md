# Freyja Director on Mars

This Compose project runs only the Freyja Director and control plane on Mars.
Signal remains a separate Atlas deployment under `deploy/compose/signal`.
The Director uses Hera's Tailscale-reachable Ollama service for the primary
complex `local_reasoning` model (`gpt-oss:20b`). Iris remains the fast local
inference tier for lower-latency local work. Hera is not a core always-on host,
so routing must tolerate Hera being unavailable and return a clear provider
failure or use configured fallback. OpenRouter fallback requires a configured
API key, approved models, and routing budget headroom.

## Private access

The published port binds to `FREYJA_DIRECTOR_BIND_IP`. Rev 1 uses Mars's
Tailscale address so Atlas can connect over the private tailnet. Set the same
strong `FREYJA_CONNECTOR_TOKEN` in the Mars Director and Atlas Signal `.env`
files. The health endpoint remains public within the tailnet; other Director
endpoints require the bearer token when it is configured.

Set `OLLAMA_BASE_URL` to Hera's private Tailscale Ollama endpoint in the
untracked `.env`. Do not commit private IP addresses, tokens, or API keys.

## Start and verify

```bash
cp deploy/compose/director/.env.example deploy/compose/director/.env
chmod 600 deploy/compose/director/.env
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml config
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml up -d --build
curl --fail http://<mars-tailscale-host>:8000/health
```

Keep the populated `.env` and runtime `data/` directory untracked.
