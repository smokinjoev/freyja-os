# Freyja 5 Gateway Compose

This compose target runs a side-by-side Freyja 5 Gateway/OpenAI-compatible
skeleton on Atlas without replacing Freyja 4.1, Freyja 3, or Open WebUI.

It exposes:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions` with model `freyja-5`
- existing authenticated Freyja compatibility endpoints from `freyja.main`

Default behavior is conservative:

- binds to `0.0.0.0:8500`
- advertises the opt-in `freyja-5` model
- runs Gateway plus `AgentRuntimeV3` route/trace selection
- leaves live local Nexus calls disabled with
  `FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED=false`
- disables cloud fallback with `CLOUD_ENABLED=false`
- leaves Apple Calendar, MacAgent, Home Assistant, and weather integrations off
  until host-local credentials are configured outside source control

Start it from the repository root:

```bash
cp deploy/compose/freyja5/.env.example deploy/compose/freyja5/.env
chmod 600 deploy/compose/freyja5/.env
docker compose --env-file deploy/compose/freyja5/.env \
  -f deploy/compose/freyja5/compose.yaml up -d --build
curl http://${HOST}:8500/health
curl http://${HOST}:8500/v1/models -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN"
```

To test the Freyja 5 OpenAI-compatible skeleton:

```bash
curl http://${HOST}:8500/v1/chat/completions \
  -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"freyja-5","messages":[{"role":"user","content":"Joe asks Freyja to summarize the architecture status."}]}'
```

To allow live local Nexus inference, configure `NEXUS_BASE_URL` and
`NEXUS_API_KEY` in the untracked `.env`, then set:

```text
FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED=true
```

Do not point production Open WebUI at this target until live Nexus/Vulcan
readiness has been validated. The current Open WebUI deployment remains on
`deploy/compose/open-webui/model-proxy.py` by default.
