# Signal connector deployment for Atlas

This Compose project runs two separate services:

- `signal-api`: `bbernhard/signal-cli-rest-api` in `native` mode.
- `signal-connector`: the Freyja transport adapter and policy gateway.

The connector polls `GET /v1/receive/{number}` and sends replies through
`POST /v2/send`. Do not configure `AUTO_RECEIVE_SCHEDULE`; another receiver
could consume messages before Freyja polls them.

## Network and data isolation

`signal-api` has no published host port. It is attached only to the internal
`signal-private` network and is reachable by the connector at
`http://signal-api:8080`. The connector also joins `freyja-backend` so it can
reach the Director. The default Director URL uses Docker's Linux host gateway;
set `FREYJA_DIRECTOR_URL` to a private service URL if the Director runs
elsewhere.

Signal account keys and registration state are stored in the named
`signal-cli-data` volume. They are not copied into the connector image or
included in this repository.

## Configuration

Copy `.env.example` to `.env` in this directory and set:

- `SIGNAL_ACCOUNT_NUMBER`: the dedicated Signal account in E.164 format.
- `SIGNAL_ALLOWED_SENDERS`: a comma-separated E.164 allowlist.
- `FREYJA_DIRECTOR_URL`: the Director's private `/route` service base URL.
- Polling and request timeouts appropriate for Atlas.

Keep `SIGNAL_ENABLED=false` until the account state has been provisioned and
the allowlist has been reviewed. Account registration or device linking is an
explicit operator task and is intentionally outside this deployment.

Validate the resolved configuration without starting containers:

```bash
docker compose -f deploy/compose/signal/compose.yaml config
```

The REST wrapper image is pinned by default. Review upstream release notes and
change `SIGNAL_REST_API_IMAGE` deliberately when upgrading.
