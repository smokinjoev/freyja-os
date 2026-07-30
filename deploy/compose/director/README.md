# Freyja Director on Mars

This Compose project runs only the Freyja Director and control plane on Mars.
Signal remains a separate Atlas deployment under `deploy/compose/signal`.
The Director uses Iris for local inference and may use OpenRouter under the
existing routing and budget policy. Hera remains the development and benchmark
machine.

## Private access

The published port binds to `FREYJA_DIRECTOR_BIND_IP`. Rev 1 uses Mars's
Tailscale address so Atlas can connect over the private tailnet. Set the same
strong `FREYJA_CONNECTOR_TOKEN` in the Mars Director and Atlas Signal `.env`
files. The health endpoint remains public within the tailnet; other Director
endpoints require the bearer token when it is configured.

## Start and verify

```bash
cp deploy/compose/director/.env.example deploy/compose/director/.env
chmod 600 deploy/compose/director/.env
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml config
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml up -d --build
curl --fail http://100.78.54.102:8000/health
```

Keep the populated `.env` and runtime `data/` directory untracked.
