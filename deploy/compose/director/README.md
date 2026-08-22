# Freyja Director on Atlas

This Compose project runs the Freyja Director service on Atlas. Vulcan is the
primary private heavy-inference node over Tailscale, while Iris remains in the
architecture for Apple integration, MacAgent work, and lightweight routing when
that tier is useful. OpenRouter fallback requires a configured API key,
approved models, and routing budget headroom.

## Private access

The published port binds to `FREYJA_DIRECTOR_BIND_IP`. On Atlas, set this to
the Atlas Tailscale address or `0.0.0.0` only when the host firewall already
limits access to the private tailnet. Set the same strong
`FREYJA_CONNECTOR_TOKEN` in the Director and any connector `.env` files. The
health endpoint remains public within the tailnet; other Director endpoints
require the bearer token when it is configured.

Set `VULCAN_BASE_URL` and `VULCAN_CODER_BASE_URL` to Vulcan's private
Tailscale OpenAI-compatible endpoints in the untracked `.env`. Keep
`LMSTUDIO_ENABLED=false` unless you deliberately want the wake-on-query LM
Studio lane exposed through the Director endpoint inventory. Do not commit
private IP addresses, tokens, or API keys.

## Start and verify

```bash
cp deploy/compose/director/.env.example deploy/compose/director/.env
chmod 600 deploy/compose/director/.env
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml config
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml up -d --build
curl --fail http://<atlas-tailscale-host>:8000/health
curl --fail http://<atlas-tailscale-host>:8000/endpoints
```

Keep the populated `.env` and runtime `data/` directory untracked.
