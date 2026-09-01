# Freyja 5 Gateway Compose

This compose target runs a side-by-side Freyja 5 Gateway/OpenAI-compatible
skeleton on Atlas without replacing Freyja 4.1, Freyja 3, or Open WebUI.

It exposes:

- `GET /health`
- `GET /freyja5/readiness`
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
curl http://${HOST}:8500/freyja5/readiness -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN"
curl http://${HOST}:8500/v1/models -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN"
```

For local test sessions where Docker Compose is not being used, the
non-secret wrapper keeps the WebGUI-compatible Freyja 5 endpoint reproducible
without enabling live inference or cloud fallback:

```bash
scripts/freyja5-local-gateway.py start
scripts/freyja5-local-gateway.py status
scripts/freyja5-local-gateway.py smoke --token test-connector-token \
  --output certification/reports/freyja5-smoke-local.json
```

`stop` only terminates the pid-file-owned process by default. Use `--force`
only when deliberately clearing a matching local test listener on port `8500`.

`/freyja5/readiness` reports source-controlled route, agent, MCP, per-agent MCP
grant, Vulcan, and A-G certification posture. It intentionally reports live
blockers for Vulcan/Nexus, Iris, and Hera until those host-local sessions are
validated.

To test the Freyja 5 OpenAI-compatible skeleton:

```bash
curl http://${HOST}:8500/v1/chat/completions \
  -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"freyja-5","messages":[{"role":"user","content":"Joe asks Freyja to summarize the architecture status."}]}'
```

To test WebGUI-style inline image routing without live inference:

```bash
curl http://${HOST}:8500/v1/chat/completions \
  -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"freyja-5","user":"joe","messages":[{"role":"user","content":[{"type":"text","text":"What useful text or objects are visible?"},{"type":"image_url","image_url":{"url":"data:image/png;base64,ZmFrZQ=="}}]}]}'
```

To test WebGUI-style inline PDF/file routing without live inference:

```bash
curl http://${HOST}:8500/v1/chat/completions \
  -H "Authorization: Bearer $FREYJA_CONNECTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"freyja-5","user":"joe","messages":[{"role":"user","content":[{"type":"text","text":"Summarize this PDF."},{"type":"file","file":{"filename":"brief.pdf","file_data":"data:application/pdf;base64,JVBERi0xLjQK"}}]}]}'
```

Both media checks should return `freyja.route=vision`,
`freyja.endpoint=vulcan-nexus-vision-docs`, `freyja.attachment_count=1`, and
`freyja.egress_state=local-only`.

The same health/readiness/models/chat/media checks can be captured as a
sanitized report:

```bash
scripts/freyja5-smoke.py \
  --base-url http://${HOST}:8500 \
  --token "$FREYJA_CONNECTOR_TOKEN" \
  --output certification/reports/freyja5-smoke.json
```

The smoke report's readiness check must include the MCP hosts, concrete MCP
server IDs, persistent logical-agent IDs, per-agent MCP grant counts, WebGUI
default/opt-in posture, and A-G certification target IDs. The readiness bundle
rejects stale smoke artifacts that omit those architecture fields.

Export canonical Freyja 5 agent definitions for Atlas/Msty Go validation:

```bash
scripts/freyja5-export-agent-definitions.py \
  --output certification/reports/freyja5-agent-definitions.json
```

The export is derived from source-controlled agent, route, Gateway policy, and
MCP topology definitions. It contains no tokens or host-local credentials and
can be compared against any Msty Go import/export without making Msty Go the
source of truth.

To assemble the current Freyja 5 certification and smoke evidence into one
readiness bundle:

```bash
scripts/freyja5-readiness-bundle.py \
  --run-certification \
  --run-smoke \
  --base-url http://${HOST}:8500 \
  --token "$FREYJA_CONNECTOR_TOKEN" \
  --output certification/reports/freyja5-readiness-bundle.json
```

Exit code `2` means source certification and smoke evidence passed but
Joe-required live validation remains in `FREYJA-5.0-BLOCKERS.md`.

To run the full Freyja 5 evidence flow in order:

```bash
scripts/freyja5-certification-gauntlet.py \
  --base-url http://${HOST}:8500 \
  --token "$FREYJA_CONNECTOR_TOKEN"
```

The gauntlet exports source agent definitions, runs direct Freyja 5
architecture certification, runs the side-by-side smoke checks, builds the
readiness bundle, and runs preflight with the export attached. Exit code `2`
has the same meaning: source-ready with Joe-required live blockers remaining.

Generate a requirement-by-requirement completion audit from the current
evidence:

```bash
scripts/freyja5-completion-audit.py \
  --readiness-bundle certification/reports/freyja5-readiness-bundle.json \
  --agent-export certification/reports/freyja5-agent-definitions.json \
  --output certification/reports/freyja5-completion-audit.json
```

Summarize the latest readiness bundle without reading raw JSON:

```bash
scripts/freyja5-preflight-status.py \
  --report certification/reports/freyja5-readiness-bundle.json \
  --agent-export certification/reports/freyja5-agent-definitions.json
```

The preflight summary prints each remaining blocker, its required evidence, and
the next operator actions to run on Atlas, Vulcan, Iris, or Hera. When
`--agent-export` is supplied, it also verifies that the Freyja 5 agent-definition
export is source-controlled, secret-free, and still aligned with the runtime
seed.

To allow live local Nexus inference, configure `NEXUS_BASE_URL` and
`NEXUS_API_KEY` in the untracked `.env`, then set:

```text
FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED=true
```

Do not point production Open WebUI at this target until live Nexus/Vulcan
readiness has been validated. The current Open WebUI deployment remains on
`deploy/compose/open-webui/model-proxy.py` by default.
