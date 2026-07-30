# Freyja Signal connector on Atlas

This Compose project runs the always-on Signal transport stack on Atlas:

- `signal-api`: `bbernhard/signal-cli-rest-api` in `native` mode.
- `signal-connector`: the Freyja Signal transport adapter and policy gateway.

The Freyja Director is not part of this stack. Rev 1 places the Director and
control plane on Mars. The connector forwards authorized requests to Mars using
`FREYJA_DIRECTOR_URL`. Iris remains the preferred local Ollama inference host.
Hera is the development and benchmark machine, not core Freyja infrastructure.

## Network and data isolation

The Signal REST API has no published host port and is reachable only by the
connector on `signal-private`. The connector also joins `atlas-egress` so it
can reach the Director on Mars at `FREYJA_DIRECTOR_URL`.

Signal account keys and registration state are stored in the
`signal-cli-data` Docker volume. Neither belongs in Git.

## Configuration

Copy `.env.example` to `.env` and set `FREYJA_DIRECTOR_URL` to the private
Mars Director endpoint reachable from Atlas. Set `FREYJA_CONNECTOR_TOKEN` to
the same strong value configured on Mars. The populated `.env` must remain mode
`0600` and uncommitted.

Keep `SIGNAL_ENABLED=false` and leave `SIGNAL_ACCOUNT_NUMBER` and
`SIGNAL_ALLOWED_SENDERS` blank until an existing Signal account is deliberately
registered or linked and the sender allowlist has been reviewed. This
deployment never performs account registration or device linking.

Validate and start the Signal connector stack:

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
curl --fail http://100.78.54.102:8000/health
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml ps
```

All services use `restart: unless-stopped`, and Docker is enabled at boot, so
the Signal connector returns automatically after an Atlas restart.
