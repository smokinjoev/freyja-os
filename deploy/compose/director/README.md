# Freyja Director on Atlas — Rev 2 Shadow Routing

This Compose project runs the Freyja Director/control plane on Atlas. Signal
remains a separate Atlas service under `deploy/compose/signal`. Iris is the
always-hot Apple/MacAgent and fast-routing node; its resident 7B model observes
Director traffic in shadow mode. The shadow classifier cannot select providers,
authorize tools, mutate responses, or block requests.

The existing Director routing path remains authoritative during the shadow
period. `OLLAMA_BASE_URL` continues to identify the currently configured
routine execution provider while `OLLAMA_REASONING_BASE_URL` identifies Odin's
heavy local reasoning endpoint once available. `IRIS_OLLAMA_BASE_URL` points
specifically to Iris's private Ollama endpoint.

## Private access

Bind the published Director port to Atlas's private Tailscale address with
`FREYJA_DIRECTOR_BIND_IP`. If another service already owns host port `8000`,
set `FREYJA_DIRECTOR_HOST_PORT` to an unused private port; the container still
listens on `8000`. Use the same strong `FREYJA_CONNECTOR_TOKEN` for trusted
connectors. Do not commit private IP addresses, tokens, or API keys.

Set `IRIS_OLLAMA_BASE_URL` to Iris's private Tailscale Ollama endpoint. Shadow
mode defaults on in the Rev 2 Compose file:

```text
IRIS_ROUTER_ENABLED=true
IRIS_ROUTER_SHADOW_ENABLED=true
IRIS_ROUTER_MODEL=qwen2.5:7b
IRIS_ROUTER_KEEP_ALIVE=-1
```

`IRIS_ROUTER_KEEP_ALIVE=-1` requests indefinite model residency so the routing
model remains hot between requests. Ollama expects that value as a numeric JSON
payload field; the Director keeps the env value string-friendly and converts
numeric values before calling Iris.

The Iris client uses Ollama JSON mode plus strict Director-side schema
validation. Full JSON-schema generation was too slow for the 4 second shadow
budget on the resident 7B model; compact JSON mode keeps the recommendation
non-authoritative while preserving malformed-output rejection.

Set `OLLAMA_REASONING_BASE_URL` to Odin's private Tailscale Ollama endpoint
when the Linux heavy inference node is online. Leave it blank or equal to
`OLLAMA_BASE_URL` until then. Atlas routes `local_reasoning` requests to this
endpoint and keeps routine local chat on `OLLAMA_BASE_URL`.

## Start and verify

```bash
cp deploy/compose/director/.env.example deploy/compose/director/.env
chmod 600 deploy/compose/director/.env
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml config
docker compose --env-file deploy/compose/director/.env \
  -f deploy/compose/director/compose.yaml up -d --build
curl --fail http://<atlas-tailscale-host>:8000/health
curl --fail http://<atlas-tailscale-host>:8000/local-reasoning/health
curl --fail -X POST http://<atlas-tailscale-host>:8000/local-reasoning/warm
curl --fail http://<atlas-tailscale-host>:8000/iris-router/health
curl --fail -X POST http://<atlas-tailscale-host>:8000/iris-router/warm
```

Replace `8000` with `FREYJA_DIRECTOR_HOST_PORT` when Atlas publishes Director
on an alternate private host port.

The Atlas app logs an `iris_shadow_route` event for each shadowed `/route`
request after the normal Director response has already been sent. Each event
contains the final Director provider/model, Iris tier/target/confidence and
latency, and whether the recommendation agreed with the provider that actually
served the request.

## Run the certification gauntlet through Iris

Run this on Atlas after Director can reach Iris:

```bash
IRIS_ROUTER_ENABLED=true \
IRIS_OLLAMA_BASE_URL=http://<iris-tailscale-host>:11434 \
IRIS_ROUTER_MODEL=qwen2.5:7b \
python -m certification.iris_shadow --difficulty smoke
```

The runner warms Iris first, then records for every case:

1. the Director's initial routing decision;
2. Iris's 7B shadow recommendation;
3. the final provider after execution/fallback;
4. Iris latency and confidence;
5. agreement/disagreement with both Director and final provider;
6. confidence distribution and under-routing cases.

JSON and Markdown reports are written under `certification/reports/`. Move from
`smoke` to `standard`, `stress`, then `chaos` only after the preceding tier is
stable.

Keep the populated `.env`, generated reports that contain sensitive prompts, and
runtime `data/` directory untracked as appropriate.
