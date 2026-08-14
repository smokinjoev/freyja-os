# Freyja Inference Gateway on Mars

This Compose project runs the Mars inference gateway as a separate service from
the Freyja Director. Freyja should ask for semantic tiers, while this gateway
maps tiers to concrete providers and models.

Initial tier map:

```text
LOCAL        -> Hera primary Ollama; Iris fallback through Director policy
FREE         -> configured OpenRouter free endpoint, opportunistic only
FAST         -> OpenRouter Qwen 3.5 Flash
REASONING    -> OpenRouter Kimi K2.5
DEEP         -> OpenRouter GLM-5
FRONTIER     -> premium OpenRouter model, explicit approval required
OLLAMA_CLOUD -> disabled until telemetry proves the subscription wins
```

When the new high-capacity local PC exists, add it as a private Layer 1
heavy-inference provider behind the same semantic tier boundary. Do not move the
Director, Signal, iMessage, memory, or Home Assistant authority to that machine
by default.

The default monthly hard limit is `$20`. `FRONTIER` calls require
`frontier_approved=true` on the request. Sensitive prompts are rerouted to
`LOCAL` instead of cloud tiers.

## Start

```bash
cp deploy/compose/inference-gateway/.env.example deploy/compose/inference-gateway/.env
chmod 600 deploy/compose/inference-gateway/.env
docker compose --env-file deploy/compose/inference-gateway/.env \
  -f deploy/compose/inference-gateway/compose.yaml config
docker compose --env-file deploy/compose/inference-gateway/.env \
  -f deploy/compose/inference-gateway/compose.yaml up -d --build
curl --fail http://127.0.0.1:8010/health
```

Bind to Mars's Tailscale address only after `FREYJA_CONNECTOR_TOKEN` is
configured and callers send the bearer token.
