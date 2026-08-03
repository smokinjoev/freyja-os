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
