# Freyja Director on Atlas

This Compose project runs the Freyja Director/control plane on Atlas. Signal
remains a separate Atlas service under `deploy/compose/signal`. Vulcan is the
inference layer. Iris is the Apple bridge and MacAgent host; its optional
resident router can observe Director traffic in shadow mode, but it is not a
conversational brain and must not authorize tools, mutate responses, or grant
permissions.

Atlas should be configured with Vulcan's stable private endpoint and logical
model profiles:

```text
VULCAN_BASE_URL=http://<vulcan-tailscale-host>:11434
MODEL_FAST=<fast-profile-model>
MODEL_REASON=<reason-profile-model>
MODEL_CODE=<code-profile-model>
MODEL_VISION=<vision-profile-model>
```

The `OLLAMA_*` variables remain compatibility defaults for existing `/route`
callers and current provider IDs. New deployment work should treat model
selection as profile configuration, not connector architecture.

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
IRIS_ROUTER_ADVISORY_ENABLED=false
IRIS_ROUTER_SHADOW_ENABLED=true
IRIS_ROUTER_MODEL=qwen2.5:7b
IRIS_ROUTER_CONFIDENCE_THRESHOLD=0.80
IRIS_ROUTER_KEEP_ALIVE=-1
```

`IRIS_ROUTER_KEEP_ALIVE=-1` requests indefinite model residency so the routing
model remains hot between requests. Ollama expects that value as a numeric JSON
payload field; the Director keeps the env value string-friendly and converts
numeric values before calling Iris.

The Iris client uses Ollama JSON mode plus strict Director-side schema
validation. Full JSON-schema generation was too slow for the 4 second shadow
budget on the resident 7B model; compact JSON mode keeps the recommendation
bounded while preserving malformed-output rejection. If active advisory mode is
enabled, low-confidence, malformed, unavailable, or policy-disallowed
recommendations fall back to deterministic Director routing.

Set `VULCAN_BASE_URL` to Vulcan's private Tailscale Ollama endpoint when the
inference node is online. Atlas maps the logical `fast`, `reason`, `code`, and
`vision` profiles to the configured physical models. `OLLAMA_REASONING_BASE_URL`
should match `VULCAN_BASE_URL` until all compatibility provider IDs are retired.

Set `MACAGENT_BASE_URL` to Iris's private MacAgent endpoint only after the
MacAgent service is installed on Iris. `MACAGENT_TOKEN` must be a strong shared
internal token. Private-network source address is not authorization; MacAgent
reports capability health, while Atlas Director still decides identity,
permissions, approval policy, memory policy, and final dispatch.

On Iris, start the authenticated MacAgent boundary with the same token:

```bash
MACAGENT_TOKEN=<strong-shared-token> \
MACAGENT_HOST=0.0.0.0 \
MACAGENT_PORT=8765 \
python scripts/run-macagent.py
```

For unattended operation on Iris, install it as the `freyja` user LaunchAgent:

```bash
scripts/install-macagent.sh
scripts/status-macagent.sh
```

The status command reads `MACAGENT_TOKEN`, `MACAGENT_HOST`, and `MACAGENT_PORT`
from the runtime environment or `.env` and performs an authenticated health
check without printing the token.

The current service exposes authenticated health and native operation handlers
for recent iMessage reads, approved iMessage replies, Apple Calendar reads and
approved writes, Apple Contacts reads, and approved Shortcuts runs.

MacAgent operation calls use an authenticated envelope containing the requested
Apple capability, operation name, request ID, actor, principal/person metadata,
required permission, approval state, and `director_authorized=true`. Iris
normalizes Apple-native output and errors; it must not infer authorization from
the caller's network location or from model/tool text.

### iMessage live smoke

Use the operator smoke command before relying on iMessage for daily use. It is a
dry-run unless `--yes` is present:

```bash
python scripts/imessage-operator.py live-smoke \
  --text "Freyja 2.0 live smoke test." \
  --dry-run \
  --output certification/reports/imessage-live-smoke-dry-run.json
```

Inspect the JSON plan and verify the recipient is expected and allowlisted. Only
then send the single smoke message:

```bash
python scripts/imessage-operator.py live-smoke \
  --text "Freyja 2.0 live smoke test." \
  --yes \
  --output certification/reports/imessage-live-smoke-sent.json
```

The command refuses recipients outside `IMESSAGE_ALLOWED_SENDERS`. Attach the
sent report to the final readiness bundle with `--smoke-report`.

For final Rev 2 cutover, prefer the guarded one-command path in
`scripts/rev2-readiness-bundle.py --imessage-live-smoke`. It dry-runs by
default and stops before readiness; adding `--yes` sends one allowlisted smoke,
attaches the generated sent report, and runs the strict readiness gate.

External-content workers, such as web research, arbitrary email parsing,
document ingestion, or scraping, must return structured observations to Atlas.
By default, untrusted-content workers cannot invoke authoritative memory writes,
message sends, home control, administrative configuration, or privileged
execution capabilities. Atlas Director interprets observations and applies the
normal Capability Broker before any action.

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
curl --fail http://<atlas-tailscale-host>:8000/providers/health
curl --fail http://<atlas-tailscale-host>:8000/iris-router/health
curl --fail -X POST http://<atlas-tailscale-host>:8000/iris-router/warm
curl --fail http://<atlas-tailscale-host>:8000/macagent/health
```

Replace `8000` with `FREYJA_DIRECTOR_HOST_PORT` when Atlas publishes Director
on an alternate private host port.

The Atlas app logs an `iris_shadow_route` event for each shadowed `/route`
request after the normal Director response has already been sent. Each event
contains the final Director provider/model, Iris tier/target/confidence and
latency, and whether the recommendation agreed with the provider that actually
served the request.

When `include_trace=true`, `/route` responses include provider profile ID,
locality, tier, classifier metadata, and provider readiness evidence. Use
`/providers/health` to inspect configured Rev 2 provider profiles, readiness,
and Iris model residency before enabling advisory mode.

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

After the `rev2-vertical-spine` certification report is generated, record the
live readiness evidence:

```bash
scripts/rev2-readiness-bundle.py \
  --director-url http://<atlas-tailscale-host>:8000 \
  --certification-report certification/reports/<rev2-vertical-spine>.json \
  --benchmark-probe \
  --connector-report certification/reports/<messaging-production-check>.json \
  --memory-report certification/reports/<rev2-memory-provenance>.json \
  --approval-report certification/reports/<rev2-approval-exercise>.json \
  --latency-winner-target <expected-fastest-target-id>
```

The helper runs the same strict readiness gate as:

```bash
freyja-certify rev2-readiness \
  --director-url http://<atlas-tailscale-host>:8000 \
  --certification-report certification/reports/<rev2-vertical-spine>.json \
  --benchmark-report certification/benchmarks/<rev2-latency-benchmark>.json \
  --connector-report certification/reports/<messaging-production-check>.json \
  --memory-report certification/reports/<rev2-memory-provenance>.json \
  --approval-report certification/reports/<rev2-approval-exercise>.json \
  --latency-winner-target <expected-fastest-target-id>
```

This writes a timestamped readiness report for provider profiles,
Atlas-to-Iris classifier health, MacAgent authentication/capabilities, and the
passing Rev 2 certification artifact. Include the benchmark arguments before
enabling Stage 3 default routing so latency improvement is part of the cutover
evidence. The command fails if any final cutover artifact is omitted:
certification report, benchmark report, connector report, memory report,
approval report, or expected latency winner.
Heavy local reasoning is optional by default because Vulcan or another heavy
inference node may not be part of every always-on deployment. Add
`--required-provider-profile heavy_local` when that tier is required for the
target deployment.

Generate latency evidence separately when you want to inspect it before running
the full bundle:

```bash
freyja-certify rev2-latency-probe \
  --director-url http://<atlas-tailscale-host>:8000 \
  --output-dir certification/benchmarks
```

Generate connector reports with `scripts/messaging-production-check.py`, keeping
the raw output alongside other private certification artifacts:

```bash
scripts/messaging-production-check.py \
  --connector all \
  --check-director \
  --output certification/reports/messaging-production-check.json
```

The readiness probe verifies that included connector reports are ready for live
smoke, have a connector token configured, and point at the same Atlas Director
URL.

Generate the memory provenance report from Atlas's target memory database:

```bash
freyja-certify rev2-memory-audit \
  --memory-db data/freyja.db \
  --output-dir certification/reports
```

The memory audit is read-only and checks that existing shared-memory rows can be
normalized under Rev 2 provenance rules.

Attach an approval exercise report after live consequential-action checks. The
readiness probe verifies that at least one consequential action was denied
without approval and at least one was allowed only after Director authorization
and explicit approval.

Generate that report from the registered controlled-write tools and Director
authorization policy:

```bash
freyja-certify rev2-approval-exercise \
  --output-dir certification/reports
```

Keep the populated `.env`, generated reports that contain sensitive prompts, and
runtime `data/` directory untracked as appropriate.
