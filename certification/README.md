# Certification Framework

The Certification Framework validates Freyja's planner, tools, memory, connectors, honesty, and future Chaos Mode.

Suites live under behavior categories:

```text
certification/suites/
  core/
  routing/
  tools/
  memory/
  vision/
  connectors/
  planning/
  calendar/
```

Each YAML file declares `name`, `category`, `difficulty`, `description`, and
`cases`. Cases can override `difficulty`, so adding a new suite normally requires
only adding another YAML file under the right category directory.

Cases may also declare behavioral assertions under `expects`. These assertions
are checked by verifier plugins against runtime evidence collected during the
Director request path:

```yaml
expects:
  provider: ollama
  provider_not: openrouter
  privacy_local: true
  tool_called: [memory]
  tool_not_called: [web]
  memory_lookup: true
  connector_called: signal
  vision_used: true
  response_contains: [cannot verify]
  response_not_contains: [guaranteed]
```

Supported verifier interfaces are `Verifier`, `RouterVerifier`, `ToolVerifier`,
`CapabilityVerifier`, `MemoryVerifier`, `VisionVerifier`, `ConnectorVerifier`,
`ResponseVerifier`, `ClassifierVerifier`, `WorkerVerifier`,
`MacAgentVerifier`, and `TimingVerifier`. Built-in verifier classes are
discovered automatically from `certification.verifiers`.

Every expectation key used by the Rev 2 routing suite must be declared in
`SUPPORTED_EXPECTATION_KEYS` in `certification.verifiers`. This prevents a YAML
case from adding an assertion that no verifier actually checks.

## Rev 2 Certification Fixtures

Rev 2 routing cases may include certification-only route request keys. The
runner strips these keys before constructing the production `RouteRequest`, then
uses them to configure the certification execution environment or to add
explicit boundary evidence:

- `certification_memory_principal` sets the authenticated memory principal.
- `certification_person` sets person context for identity and authorization.
- `certification_iris_health` simulates Iris classifier availability.
- `certification_iris_response` simulates malformed Iris classifier output.
- `certification_iris_recommendation` installs a temporary Iris advisory result.
- `certification_provider_health` can mark `heavy_local` unavailable for a case.
- `certification_cloud_enabled` temporarily overrides cloud routing policy.
- `certification_capability_checks` records explicit capability boundary
  evidence, including MacAgent Director authorization state.
- `worker_observation` validates proposed worker capabilities through
  `WorkerPolicy` and records whether an untrusted worker action was allowed.

These fixtures are scoped to one certification case and are restored afterward.
They are not accepted production route fields.

Run the default smoke gauntlet with the default Ollama provider:

```bash
freyja-certify
```

Useful options:

```bash
freyja-certify --list-suites
freyja-certify core/honesty --model qwen2.5:7b
freyja-certify honesty
freyja-certify standard
freyja-certify chaos --router-mode local --output-dir certification/reports
freyja-certify all
```

Difficulty levels:

- `smoke` - fast baseline checks across categories
- `standard` - normal regression coverage
- `stress` - edge cases, partial evidence, failures, and ambiguity
- `chaos` - adversarial prompts that try to induce hallucination, fake
  certainty, fabricated tool output, invented memories, routing mistakes,
  privacy leaks, and incorrect image descriptions

Reports are written to `certification/reports/` by default as both Markdown and
JSON with timestamped filenames. Each report records the timestamp, git SHA,
branch, working-tree state, hostname, provider, model, router mode, suite name,
overall score, per-category scores, execution time, and certification CLI
version. Markdown reports show failed cases before the full case listing.

## Runtime Evidence

Certification runs use the Director router execution path for Ollama/local
requests. Each case stores a `runtime_context` object in JSON reports with:

- selected provider and model
- routing decision and reason
- fallback events
- tool calls, sanitized tool arguments, success/failure, and timing
- memory lookup evidence slots
- connector operation evidence slots
- vision execution evidence slots
- timing, token counts when available, and cost when available

The JSON report has a `schema_version` field so future dashboard code can
version migrations deliberately.

## Benchmark Workflow

Run identical certification suites across provider/model targets:

```bash
freyja-certify benchmark \
  --benchmark-suite smoke \
  --provider ollama --model qwen3:27b \
  --provider ollama --model hermes3:8b \
  --provider openrouter --model openai/gpt-5.5
```

`--benchmark-suite` may be repeated to run multiple suites for every target.
The older Ollama-only shortcut is still supported:

```bash
freyja-certify benchmark --benchmark-suite smoke --models qwen2.5:7b,gpt-oss-freyja:20b-analysis-prefill
```

Benchmark history is stored under `certification/benchmarks/` by default. Each
benchmark run writes:

- individual certification Markdown and JSON reports for each target/suite run
- one benchmark Markdown comparison table
- one benchmark JSON report with stable target IDs and router-ready metrics

Benchmark metrics include overall score, category scores, execution time,
average latency, token usage, tool success rate, verifier correctness for
routing/memory/connectors/vision, failures, and cost when available.

Calendar suites validate the Family Calendar Personal Intelligence Service:
schedule reasoning, conflict detection, memory-informed preference handling,
and provider abstraction.

## Benchmark Report Format

Benchmark JSON reports use this top-level shape:

```json
{
  "schema_version": "1.0",
  "timestamp": "2026-08-03T12:00:00+00:00",
  "git_sha": "abc123",
  "suite_names": ["smoke"],
  "entries": [
    {
      "target": {
        "provider": "ollama",
        "model": "qwen3:27b",
        "target_id": "ollama:qwen3:27b"
      },
      "metrics": {
        "overall_score": 0.92,
        "category_scores": {"routing": 1.0},
        "average_latency_ms": 840.0,
        "token_usage": 1200
      }
    }
  ],
  "rankings": {
    "overall_score": ["ollama:qwen3:27b"],
    "latency": ["ollama:qwen3:27b"]
  },
  "router_data": {
    "selection_inputs": {}
  }
}
```

`router_data.selection_inputs` is intentionally compact and stable so the
Freyja Router can later consume measured provider/model behavior without
depending on Markdown report layout or per-case certification internals.

## Comparison Workflow

Compare two certification reports or two benchmark reports:

```bash
freyja-certify compare --reports certification/reports/old.json certification/reports/new.json
freyja-certify compare --reports certification/benchmarks/old.json certification/benchmarks/new.json
```

Compare benchmark history by commit prefix or by two models contained in the
latest matching benchmark report:

```bash
freyja-certify compare --commits 51295e5 abc1234
freyja-certify compare --models qwen3:27b,hermes3:8b
```

Comparison output is written to `certification/benchmarks/` by default and
highlights score deltas, latency deltas, regressions, improvements, and ranking
changes for benchmark reports.

## Rev 2 Readiness Probe

After running `rev2-vertical-spine` against the target Atlas deployment, record
the live operational checks that are outside unit-test evidence:

```bash
scripts/rev2-readiness-bundle.py \
  --director-url http://<atlas-tailscale-host>:8000 \
  --certification-report certification/reports/<rev2-vertical-spine>.json \
  --benchmark-probe \
  --connector-report certification/reports/<messaging-production-check>.json \
  --memory-report certification/reports/<rev2-memory-provenance>.json \
  --approval-report certification/reports/<rev2-approval-exercise>.json \
  --vulcan-report certification/reports/<vulcan-readiness>.json \
  --smoke-report certification/reports/<imessage-live-smoke-sent>.json \
  --signal-smoke-report certification/reports/<signal-live-smoke-sent>.json \
  --require-smoke-report \
  --require-signal-smoke-report \
  --require-vulcan-report \
  --latency-winner-target <expected-fastest-target-id>
```

The helper assembles the required bundle and runs:

```bash
freyja-certify rev2-readiness \
  --director-url http://<atlas-tailscale-host>:8000 \
  --certification-report certification/reports/<rev2-vertical-spine>.json \
  --benchmark-report certification/benchmarks/<rev2-latency-benchmark>.json \
  --connector-report certification/reports/<messaging-production-check>.json \
  --memory-report certification/reports/<rev2-memory-provenance>.json \
  --approval-report certification/reports/<rev2-approval-exercise>.json \
  --vulcan-report certification/reports/<vulcan-readiness>.json \
  --smoke-report certification/reports/<imessage-live-smoke-sent>.json \
  --signal-smoke-report certification/reports/<signal-live-smoke-sent>.json \
  --require-smoke-report \
  --require-signal-smoke-report \
  --require-vulcan-report \
  --latency-winner-target <expected-fastest-target-id>
```

The readiness probe checks `/providers/health`, `/iris-router/health`, and
`/macagent/health`, then writes timestamped JSON and Markdown reports under
`certification/reports/`. The report fails unless required Rev 2 provider
profiles are present, Iris is enabled and available, MacAgent is reachable and
authenticated, the Rev 2 Apple capability families are advertised, and the
supplied `rev2-vertical-spine` report has no failed cases. The final readiness
command also requires a benchmark report and `--latency-winner-target`; the
benchmark must contain at least two targets with no failures and the expected
fastest target must lead the latency ranking. The command fails if any final
cutover artifact is omitted: certification report, benchmark report, connector
report, memory report, approval report, Vulcan readiness report, or expected
latency winner. Add `--require-vulcan-report` for final profile cutover;
the report must prove `fast`, `reason`, `code`, and `vision` are ready. Add
`--require-smoke-report` for final iMessage cutover and
`--require-signal-smoke-report` for final Signal cutover; each requires a
non-dry-run live-smoke report with one successful sent message.

To consolidate the final operator handoff, the same readiness helper can run
the iMessage smoke step first. It previews the smoke by default and stops before readiness:

```bash
scripts/rev2-readiness-bundle.py \
  --director-url http://<atlas-tailscale-host>:8000 \
  --certification-report certification/reports/<rev2-vertical-spine>.json \
  --benchmark-report certification/benchmarks/<rev2-latency-benchmark>.json \
  --connector-report certification/reports/<messaging-production-check>.json \
  --memory-report certification/reports/<rev2-memory-provenance>.json \
  --approval-report certification/reports/<rev2-approval-exercise>.json \
  --imessage-live-smoke \
  --require-smoke-report \
  --latency-winner-target <expected-fastest-target-id>
```

Only after reviewing that dry-run, add `--yes`. With `--yes`, the helper sends
one allowlisted smoke message, writes
`certification/reports/imessage-live-smoke-sent.json`, attaches it as
`--smoke-report`, and then runs final readiness.

The helper can do the same guarded flow for Signal with `--signal-live-smoke`.
It dry-runs by default and stops before readiness; adding `--signal-yes` sends
one allowlisted Signal smoke message, writes
`certification/reports/signal-live-smoke-sent.json`, attaches it as
`--signal-smoke-report`, and then runs final readiness.

Summarize the latest readiness artifact with the installed preflight command:

```bash
freyja-rev2-preflight-status
```

When running directly from a source checkout before installation, use the
equivalent repository wrapper:

```bash
scripts/rev2-preflight-status.py
```

Use `--json` with either command when an automation or monitor needs a stable
machine-readable status, failed-check list, remaining-work list,
`dry_run_command` for the safe review step, `final_command` for the approved
cutover action when available, and intended exit code.

Exit code `0` means the latest readiness report passed, `2` means every
non-smoke check passed and only approved live iMessage and/or Signal smoke
proof remains, and `1` means at least one other readiness check still needs
work.

Heavy local reasoning is optional by default because Vulcan or another heavy
inference node may not be part of every always-on deployment. Add
`--required-provider-profile heavy_local` when a target deployment requires that
model tier to be live before cutover.

Run the live Freyja 2.0 evidence bundle from the source checkout when validating
iMessage equivalence, Vulcan model availability, the 100-question accuracy gate,
iterative coding, and token/sec baselines:

```bash
scripts/freyja-live-evidence-bundle.py --sync-imessage-runtime
```

The bundle writes `certification/reports/freyja-live-evidence-summary.json`.
Completion requires synced iMessage runtime source, live iMessage route smoke,
terminal/iMessage prompt equivalence, Vulcan preflight, the 100-question suite at
95% or better, measured generation tokens/sec, and the iterative coding suite.

Run the 100-question inference gate directly against Vulcan's heavy local model
when validating model accuracy in isolation:

```bash
PYTHONPATH=src freyja-certify inference/freyja_qa_100 \
  --provider local_reasoning \
  --model gpt-oss-freyja:20b-analysis-prefill \
  --router-mode vulcan-direct-local-reasoning
```

Run the iterative coding gate directly when validating the Smith/Qwen coding lane
in isolation:

```bash
PYTHONPATH=src freyja-certify inference/freyja_iterative_coding \
  --provider local_reasoning \
  --model gpt-oss-freyja:20b-analysis-prefill \
  --router-mode vulcan-direct-local-reasoning
```

Generate latency evidence separately when you want to inspect it before running
the full bundle:

```bash
freyja-certify rev2-latency-probe \
  --director-url http://<atlas-tailscale-host>:8000 \
  --output-dir certification/benchmarks
```
When `--connector-report` is supplied, each connector in the production-check
JSON must be ready for live smoke, have a connector token configured, and point
to the same Atlas Director URL being certified.

Generate connector evidence with:

```bash
scripts/messaging-production-check.py \
  --connector all \
  --check-director \
  --output certification/reports/messaging-production-check.json
```
When `--approval-report` is supplied, the report must show at least one
consequential action denied without approval and at least one consequential
action allowed only with Director authorization and explicit approval.

Generate the approval exercise report from the registered controlled-write
tools and Director authorization policy:

```bash
freyja-certify rev2-approval-exercise \
  --output-dir certification/reports
```

Generate the memory provenance report from the target Atlas memory database:

```bash
freyja-certify rev2-memory-audit \
  --memory-db data/freyja.db \
  --output-dir certification/reports
```

The memory audit is read-only. It fails on malformed shared-memory metadata,
malformed provenance records, or untrusted external observations that are still
marked authoritative. Legacy rows without explicit provenance are counted as
normalized default rows so rollout can be inspected without rewriting history.
