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

## Benchmark And Compare

Run identical suites across model names:

```bash
freyja-certify benchmark --benchmark-suite smoke --models qwen2.5:7b,gpt-oss:20b
```

Compare two JSON reports:

```bash
freyja-certify compare --reports certification/reports/old.json certification/reports/new.json
```

Comparison output highlights score deltas, latency deltas, regressions, and
improvements.
