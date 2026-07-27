# Freyja control plane on Mars

This Compose project runs the lightweight Freyja control plane together on
Mars:

- `director`: routing, policy, memory, tool orchestration, and provider choice.
- `signal-api`: `bbernhard/signal-cli-rest-api` in `native` mode.
- `signal-connector`: the Freyja Signal transport adapter and policy gateway.

The Director prefers Ollama on Iris and uses OpenRouter only under the existing
routing and budget policy. Atlas infrastructure services are not part of this
project and must not be moved here.

## Network and data isolation

The Signal REST API has no published host port and is reachable only by the
connector on `signal-private`. The connector reaches the Director at
`http://director:8000` on `freyja-backend`. The Director is published only on
Mars loopback at `127.0.0.1:8000` for local administration and health checks.

Director memory is stored in the repository's ignored `data/` directory.
Signal account keys and registration state are stored in the
`signal-cli-data` Docker volume. Neither belongs in Git.

## Configuration

Copy `.env.example` to `.env`, set `OLLAMA_BASE_URL` to Iris's private Ollama
endpoint, and add `OPENROUTER_API_KEY` locally when cloud fallback is wanted.
The populated `.env` must remain mode `0600` and uncommitted.

Keep `SIGNAL_ENABLED=false` and leave `SIGNAL_ACCOUNT_NUMBER` and
`SIGNAL_ALLOWED_SENDERS` blank until an existing Signal account is deliberately
registered or linked and the sender allowlist has been reviewed. This
deployment never performs account registration or device linking.

Validate and start the control plane:

```bash
cp deploy/compose/signal/.env.example deploy/compose/signal/.env
chmod 600 deploy/compose/signal/.env
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml config
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml up -d --build
```

Verify:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ollama/health
curl --fail http://127.0.0.1:8000/openrouter/health
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml ps
```

All services use `restart: unless-stopped`, and Docker is enabled at boot, so
the control plane returns automatically after a Mars restart.
