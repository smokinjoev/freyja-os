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
`MemoryVerifier`, `VisionVerifier`, and `ConnectorVerifier`. Built-in verifier
classes are discovered automatically from `certification.verifiers`.

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
freyja-certify benchmark --benchmark-suite smoke --models qwen2.5:7b,gpt-oss:20b
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
