# Freyja Signal connector on Atlas

This Compose project runs the always-on Signal transport stack on Atlas:

- `signal-api`: `bbernhard/signal-cli-rest-api` in `native` mode.
- `signal-connector`: the Freyja Signal transport adapter and policy gateway.
- `signal-operator`: a one-shot operator profile for registration, linking,
  readiness, and live-smoke actions on the private Compose network.

The Freyja Director is not part of this stack. Atlas is the authoritative
Director/control-plane host, and the connector forwards authorized requests to
the Atlas Director using `FREYJA_DIRECTOR_URL`. Iris remains the Apple/MacAgent
and fast local inference tier. Heavy inference nodes are optional providers
behind Director policy and are not part of this Signal deployment.

## Network and data isolation

The Signal REST API has no published host port and is reachable only by the
connector on `signal-private`. It also joins `atlas-egress` because linking,
registration, send, and receive operations must reach Signal's servers.

The connector joins both `signal-private` and `atlas-egress` so it can reach the
local Signal REST API and the Atlas Director at `FREYJA_DIRECTOR_URL`.

Signal account keys and registration state are stored in the
`signal-cli-data` Docker volume. Neither belongs in Git.

## Configuration

Copy `.env.example` to `.env` and set `FREYJA_DIRECTOR_URL` to the private
Atlas Director endpoint reachable from the connector container. Set
`FREYJA_CONNECTOR_TOKEN` to the same strong value configured on Director. The
populated `.env` must remain mode `0600` and uncommitted.

Keep `SIGNAL_ENABLED=false` and leave `SIGNAL_ACCOUNT_NUMBER` and
`SIGNAL_ALLOWED_SENDERS` blank until an existing Signal account is deliberately
registered or linked and the sender allowlist has been reviewed. Registration
and linking are explicit one-shot operator commands; they are not performed by
the always-on connector.

Validate and start the Signal connector stack:

```bash
cp deploy/compose/signal/.env.example deploy/compose/signal/.env
chmod 600 deploy/compose/signal/.env
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml config
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml up -d --build
```

## Account registration or linking

Run operator commands inside the Compose network so `SIGNAL_REST_API_URL` stays
private as `http://signal-api:8080`.

Request and verify a dedicated Signal number:

```bash
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  register --number +15555550100
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  register --number +15555550100 --yes
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  verify --number +15555550100 --code 123-456
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  verify --number +15555550100 --code 123-456 --yes
```

Use `--voice` on `register` when SMS is unavailable. Use `--captcha` only when
Signal requires a captcha token. For an existing mobile Signal account, link
the REST wrapper as a secondary device:

```bash
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  link-device --device-name freyja-atlas
```

The dry-run output redacts phone numbers and does not include codes, PINs,
captcha tokens, or link URIs. If a link URI must be written for manual use,
write it to a temporary path inside the container and copy it through an
operator-approved mechanism, then delete it after scanning.

Verify:

```bash
curl --fail http://<atlas-director-private-host>:8000/health
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml ps
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  readiness --check-registered \
  | tee certification/reports/signal-readiness.json
python scripts/messaging-production-check.py --connector signal \
  --env-file deploy/compose/signal/.env \
  --check-director --check-signal-rest \
  --output certification/reports/signal-production-check.json
```

`signal-operator.py readiness` is read-only. It reports whether Signal is ready
for an approved live smoke and lists the exact missing configuration or REST
state without printing raw phone numbers.

## Signal live smoke

Use the operator smoke command before relying on Signal for daily use. It
dry-runs by default and redacts phone numbers in the report:

```bash
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  live-smoke \
  --text "Freyja 2.0 Signal live smoke test." \
  | tee certification/reports/signal-live-smoke-dry-run.json
```

Review the dry-run plan, confirm it targets one allowlisted recipient, then send
the single approved smoke message:

```bash
docker compose --env-file deploy/compose/signal/.env \
  -f deploy/compose/signal/compose.yaml run --rm signal-operator \
  live-smoke \
  --text "Freyja 2.0 Signal live smoke test." \
  --yes \
  | tee certification/reports/signal-live-smoke-sent.json
```

All services use `restart: unless-stopped`, and Docker is enabled at boot, so
the Signal connector returns automatically after an Atlas restart.

Attach the sent report to final Rev 2 readiness with
`--signal-smoke-report certification/reports/signal-live-smoke-sent.json` and
`--require-signal-smoke-report`.
